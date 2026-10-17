"""SQLite persistence; ``sql/schema.sql`` is the single DDL source of truth."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Database:
    def __init__(self, path: str | Path, project_root: str | Path) -> None:
        self.path = Path(path)
        self.project_root = Path(project_root)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        return conn

    def initialize(self) -> None:
        schema_path = self.project_root / "sql" / "schema.sql"
        if not schema_path.is_file():
            raise FileNotFoundError(f"Schema not found: {schema_path}")
        with self.connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            self._migrate(conn)

    # Columns added after the first schema version. ``CREATE TABLE IF NOT EXISTS``
    # never alters an existing table, so older local databases are upgraded here.
    _ADDED_COLUMNS = (
        ("target_hour_status", "anomalies", "TEXT"),
        ("alert_incident", "run_id", "TEXT"),
        ("alert_incident", "fingerprint", "TEXT"),
        ("alert_incident", "conditions", "TEXT"),
        ("alert_incident", "last_error", "TEXT"),
    )

    def _migrate(self, conn: sqlite3.Connection) -> None:
        for table, column, ddl in self._ADDED_COLUMNS:
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def ensure_targets(self, targets: dict[str, Any]) -> list[dict[str, Any]]:
        now = utc_now_iso()
        platform = targets.get("platform", "AJIO")
        platform_code = targets.get("platform_code", platform)
        frequency = int(targets.get("expected_frequency_minutes", 60))
        max_pages = int(targets.get("max_pages", 2))
        keywords = targets.get("keywords", [])
        with self.connect() as conn:
            for keyword in keywords:
                conn.execute(
                    """INSERT INTO scrape_target
                    (platform, platform_code, target_type, target_value, enabled,
                     expected_frequency_minutes, max_pages, priority, created_at)
                    VALUES (?, ?, 'keyword', ?, 1, ?, ?, 0, ?)
                    ON CONFLICT(platform, target_type, target_value) DO UPDATE SET
                      platform_code=excluded.platform_code,
                      enabled=1,
                      expected_frequency_minutes=excluded.expected_frequency_minutes,
                      max_pages=excluded.max_pages""",
                    (platform, platform_code, str(keyword), frequency, max_pages, now),
                )
            rows = conn.execute(
                "SELECT * FROM scrape_target WHERE platform=? AND enabled=1 ORDER BY target_id",
                (platform,),
            ).fetchall()
        return [dict(r) for r in rows]

    def acquire_lock(self, lock_name: str, run_id: str, stale_after_hours: int = 4) -> None:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=stale_after_hours)).isoformat(timespec="seconds").replace("+00:00", "Z")
        with self.connect() as conn:
            conn.execute("DELETE FROM pipeline_lock WHERE lock_name=? AND acquired_at < ?", (lock_name, cutoff))
            # A lock whose run has already finished is a leftover (for example the
            # release failed while the database was unavailable): clear it at once.
            conn.execute(
                "DELETE FROM pipeline_lock WHERE lock_name=? AND run_id IN "
                "(SELECT run_id FROM scrape_run WHERE finished_at IS NOT NULL)",
                (lock_name,),
            )
            try:
                conn.execute(
                    "INSERT INTO pipeline_lock(lock_name, run_id, acquired_at) VALUES (?, ?, ?)",
                    (lock_name, run_id, utc_now_iso()),
                )
            except sqlite3.IntegrityError as exc:
                raise RuntimeError("Another pipeline run is active; overlapping execution was blocked") from exc

    def lock_holder(self, lock_name: str) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM pipeline_lock WHERE lock_name=?", (lock_name,))
        return rows[0] if rows else None

    def release_lock(self, lock_name: str, run_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pipeline_lock WHERE lock_name=? AND run_id=?", (lock_name, run_id))

    def create_run(self, record: dict[str, Any]) -> None:
        fields = (
            "run_id", "platform", "scheduled_hour", "started_at", "finished_at", "status", "trigger",
            "expected_target_count", "completed_target_count", "row_count", "error_count", "retry_count",
            "scraper_version", "adapter_mode", "error_summary",
        )
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO scrape_run ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                tuple(record.get(f) for f in fields),
            )

    def update_run(self, run_id: str, **updates: Any) -> None:
        allowed = {
            "finished_at", "status", "completed_target_count", "row_count", "error_count", "retry_count", "error_summary"
        }
        updates = {key: value for key, value in updates.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key}=?" for key in updates)
        with self.connect() as conn:
            conn.execute(f"UPDATE scrape_run SET {assignments} WHERE run_id=?", (*updates.values(), run_id))

    def save_raw_snapshot(self, record: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO raw_snapshot
                (run_id,target_id,keyword,page_number,fetched_at,http_status,body_path,sha256,headers_json,is_mock,created_at)
                VALUES (:run_id,:target_id,:keyword,:page_number,:fetched_at,:http_status,:body_path,:sha256,:headers_json,:is_mock,:created_at)""",
                record,
            )

    def upsert_status(self, record: dict[str, Any]) -> None:
        record = {"anomalies": None, **record}
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO target_hour_status
                (platform,target_id,scheduled_hour,status,expected,observed,row_count,first_seen_at,checked_at,
                 missing_reason,incident_id,last_run_id,parse_error_count,anomalies,is_mock)
                VALUES (:platform,:target_id,:scheduled_hour,:status,:expected,:observed,:row_count,:first_seen_at,
                 :checked_at,:missing_reason,:incident_id,:last_run_id,:parse_error_count,:anomalies,:is_mock)
                ON CONFLICT(platform,target_id,scheduled_hour) DO UPDATE SET
                  status=excluded.status, expected=excluded.expected, observed=excluded.observed,
                  row_count=excluded.row_count, checked_at=excluded.checked_at,
                  missing_reason=excluded.missing_reason, incident_id=excluded.incident_id,
                  last_run_id=excluded.last_run_id, parse_error_count=excluded.parse_error_count,
                  anomalies=excluded.anomalies, is_mock=excluded.is_mock""",
                record,
            )

    def sync_products(self, records: Iterable[dict[str, Any]], target_id: int, platform: str, scheduled_hour: str, replace_complete: bool = True) -> None:
        records = list(records)
        fields = (
            "time_stamp", "platform", "platform_code", "keyword", "product_name", "sp", "mrp", "rating",
            "num_of_rating", "tag", "deal", "product_image_u", "absolute_rank", "relative_rank", "product_type",
            "campaign_id", "product_id", "product_url", "run_id", "target_id", "scheduled_hour", "page_number",
            "raw_payload_ref", "parse_status", "is_mock",
        )
        update_fields = [f for f in fields if f not in {"platform", "target_id", "scheduled_hour", "absolute_rank"}]
        sql = (
            f"INSERT INTO visibility_product ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)}) "
            f"ON CONFLICT(platform,target_id,scheduled_hour,absolute_rank) DO UPDATE SET "
            + ",".join(f"{field}=excluded.{field}" for field in update_fields)
        )
        with self.connect() as conn:
            for record in records:
                conn.execute(sql, tuple(record.get(field) for field in fields))
            # A complete successful parse may replace the slot. Partial/failed runs
            # upsert good observations but never erase rows from the last valid run.
            if replace_complete:
                if records:
                    conn.execute(
                        "DELETE FROM visibility_product WHERE platform=? AND target_id=? AND scheduled_hour=? AND absolute_rank>?",
                        (platform, target_id, scheduled_hour, max(int(r["absolute_rank"]) for r in records)),
                    )
                else:
                    conn.execute(
                        "DELETE FROM visibility_product WHERE platform=? AND target_id=? AND scheduled_hour=?",
                        (platform, target_id, scheduled_hour),
                    )

    def save_quarantine(self, records: Iterable[dict[str, Any]]) -> int:
        """Store quarantined records. Idempotent within a run (INSERT OR IGNORE on the unique key)."""
        rows = list(records)
        if not rows:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO quarantine_record
                (run_id,platform,target_id,keyword,scheduled_hour,page_number,record_type,record_index,stage,
                 reason_code,reason_detail,payload_json,raw_payload_ref,is_mock,created_at)
                VALUES (:run_id,:platform,:target_id,:keyword,:scheduled_hour,:page_number,:record_type,:record_index,
                 :stage,:reason_code,:reason_detail,:payload_json,:raw_payload_ref,:is_mock,:created_at)""",
                rows,
            )
        return len(rows)

    def count_products(self, platform: str, target_id: int, scheduled_hour: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM visibility_product WHERE platform=? AND target_id=? AND scheduled_hour=?",
                (platform, target_id, scheduled_hour),
            ).fetchone()
        return int(row["n"])

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def execute(self, sql: str, params: tuple | list = ()) -> int:
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            return int(cur.rowcount)
