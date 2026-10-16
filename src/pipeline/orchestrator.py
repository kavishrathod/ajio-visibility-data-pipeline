"""End-to-end collection, raw preservation, parsing, idempotent storage, and run state."""
from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import __version__
from src.collectors.ajio_adapter import AjioAdapter
from src.collectors.base import Adapter, RawResponse
from src.collectors.fetcher import FetchExhausted, fetch_with_retry
from src.collectors.mock_adapter import MockAdapter
from src.collectors.ratelimit import NullRateLimiter, RateLimiter
from src.collectors.replay_adapter import ReplayAdapter
from src.config import AppConfig
from src.logger import get_logger
from src.parsers.product_parser import ProductUnit, parse_products
from src.pipeline.completeness import format_hour
from src.pipeline.ranking import assign_ranks
from src.pipeline.validator import find_cross_page_duplicates, validate_units
from src.storage.database import Database, utc_now_iso

logger = get_logger(__name__)


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")[:70] or "target"


def _adapter(config: AppConfig) -> Adapter:
    mode = config.settings.get("adapter", "mock")
    if mode == "live":
        return AjioAdapter()
    return MockAdapter(
        config.root / "tests" / "fixtures",
        mapping=config.settings.get("mock_fixtures", {}),
        generate=bool(config.settings.get("mock_generator", False)),
    )


def _rate_limiter(config: AppConfig, adapter: Adapter, sleeper):
    """Rate-limit real network adapters; the mock does no I/O so it is exempt unless asked."""
    rate = config.settings.get("rate_limit", {}) or {}
    if not rate.get("enabled", True):
        return NullRateLimiter()
    is_mock = isinstance(adapter, (MockAdapter, ReplayAdapter))
    if is_mock and not rate.get("apply_to_mock", False):
        return NullRateLimiter()
    return RateLimiter(float(rate.get("requests_per_second", 0.5)), sleeper=sleeper)


def _raw_dir(scheduled_hour: str, platform: str, run_id: str) -> Path:
    """data/raw/platform=<p>/date=<YYYY-MM-DD>/hour=<HH>/<run_id>/ (UTC)."""
    day, clock = scheduled_hour.split("T")
    return Path("data") / "raw" / f"platform={platform}" / f"date={day}" / f"hour={clock[:2]}" / run_id


def _write_raw_file(config: AppConfig, run_id: str, keyword: str, response: RawResponse, scheduled_hour: str) -> tuple[str, str]:
    """Write the raw body and a metadata sidecar to disk. Never touches the database."""
    relative_dir = _raw_dir(scheduled_hour, config.platform, run_id)
    (config.root / relative_dir).mkdir(parents=True, exist_ok=True)
    relative_path = relative_dir / f"{_slug(keyword)}__p{response.page}.html"
    body_bytes = response.body.encode("utf-8")
    (config.root / relative_path).write_bytes(body_bytes)
    sha256 = hashlib.sha256(body_bytes).hexdigest()
    meta = {
        "run_id": run_id, "scheduled_hour": scheduled_hour, "keyword": keyword, "page": response.page,
        "http_status": response.http_status, "fetched_at": response.fetched_at, "is_mock": response.is_mock,
        "headers": response.headers, "sha256": sha256,
    }
    meta_path = relative_path.with_name(relative_path.stem + ".meta.json")
    (config.root / meta_path).write_text(json.dumps(meta, sort_keys=True, indent=1), encoding="utf-8")
    return relative_path.as_posix(), sha256


def _dedupe_entries(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    units, rejected = validate_units(entry["unit"] for entry in entries)
    by_identity = {id(entry["unit"]): entry for entry in entries}
    accepted = [by_identity[id(unit)] for unit in units if id(unit) in by_identity]
    dup_count = sum(1 for item in rejected if "duplicate_placement_dropped" in item.get("errors", []))
    return accepted, dup_count


def _record_skipped_run(db: Database, config: AppConfig, run_id: str, hour_text: str, trigger: str, expected: int, lock_name: str) -> dict[str, Any]:
    """The lock is held by another run: record that fact as a run row instead of crashing (I-9)."""
    holder = db.lock_holder(lock_name) or {}
    now = utc_now_iso()
    reason = (
        f"Skipped: run {holder.get('run_id', 'unknown')} has held the platform lock since "
        f"{holder.get('acquired_at', 'unknown')}. No target was fetched by this run."
    )
    db.create_run({
        "run_id": run_id, "platform": config.platform, "scheduled_hour": hour_text, "started_at": now,
        "finished_at": now, "status": "skipped_overlap", "trigger": trigger,
        "expected_target_count": expected, "completed_target_count": 0, "row_count": 0, "error_count": 1,
        "retry_count": 0, "scraper_version": __version__,
        "adapter_mode": "mock" if config.settings.get("adapter", "mock") == "mock" else "live-disabled",
        "error_summary": reason,
    })
    logger.warning("Overlapping run blocked for %s: %s", hour_text, reason)
    return {
        "run_id": run_id, "platform": config.platform, "scheduled_hour": hour_text, "trigger": trigger,
        "status": "skipped_overlap", "expected_targets": expected, "completed_targets": 0,
        "rows_written_or_upserted": 0, "retry_count": 0, "error_count": 1, "status_counts": {},
        "errors": [reason], "pagination_anomalies": 0, "db_errors": [],
    }


def run_pipeline(
    config: AppConfig,
    scheduled_hour: str | datetime | None = None,
    trigger: str = "manual",
    keywords: list[str] | None = None,
    adapter_override: Adapter | None = None,
    sleeper=None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Run one platform-hour slot for every target.

    * ``scheduled_hour`` is fixed once at the start; it is the slot every row
      belongs to, however late the run actually starts or finishes (I-8).
    * One platform-wide lock prevents two runs touching the same targets at once.
      A second run is recorded as ``skipped_overlap`` (I-9).
    * Raw bodies reach disk before any database write, and database failures are
      contained per target so fetched data is never lost (I-11).
    """
    sleeper = sleeper or time.sleep
    rng = rng or random.Random()
    db = Database(config.db_path, config.root)
    db.initialize()
    all_targets = db.ensure_targets(config.targets)
    if keywords:
        requested = set(keywords)
        unknown = requested.difference(config.keywords)
        if unknown:
            raise ValueError(f"Unknown target keyword(s): {', '.join(sorted(unknown))}")
        targets = [target for target in all_targets if target["target_value"] in requested]
    else:
        targets = all_targets
    if not targets:
        raise ValueError("No enabled targets are configured")

    hour_text = format_hour(scheduled_hour)
    run_id = str(uuid.uuid4())
    lock_name = f"pipeline:{config.platform}"
    try:
        db.acquire_lock(lock_name, run_id)
    except RuntimeError:
        return _record_skipped_run(db, config, run_id, hour_text, trigger, len(targets), lock_name)

    started = utc_now_iso()
    try:
        db.create_run({
            "run_id": run_id,
            "platform": config.platform,
            "scheduled_hour": hour_text,
            "started_at": started,
            "finished_at": None,
            "status": "running",
            "trigger": trigger,
            "expected_target_count": len(targets),
            "completed_target_count": 0,
            "row_count": 0,
            "error_count": 0,
            "retry_count": 0,
            "scraper_version": __version__,
            "adapter_mode": "mock" if config.settings.get("adapter", "mock") == "mock" else "live-disabled",
            "error_summary": None,
        })
    except sqlite3.Error:
        # Nothing has been fetched yet, so nothing can be lost: give the lock back and fail loudly.
        db.release_lock(lock_name, run_id)
        raise

    adapter = adapter_override or _adapter(config)
    adapter.set_slot(hour_text)
    limiter = _rate_limiter(config, adapter, sleeper)
    retry_settings = dict(config.settings.get("retries", {}))
    retry_settings.setdefault("retry_after_budget_seconds", 30)
    total_retries = 0
    current_run_rows = 0
    completed = 0
    pagination_anomaly_count = 0
    errors: list[str] = []
    db_errors: list[str] = []
    status_counts: dict[str, int] = {}

    def safe(label: str, fn, *args, **kwargs) -> bool:
        """Run a database write; contain sqlite errors so one outage cannot discard fetched data."""
        try:
            fn(*args, **kwargs)
            return True
        except sqlite3.Error as exc:
            message = f"{label}: {type(exc).__name__}: {exc}"
            db_errors.append(message)
            logger.error("Database write failed (%s); raw snapshots are preserved on disk", message)
            return False

    try:
        for target in targets:
            target_id = int(target["target_id"])
            keyword = str(target["target_value"])
            max_pages = min(int(target.get("max_pages") or config.max_pages), config.max_pages)
            entries: list[dict[str, Any]] = []
            valid_page_seen = False
            zero_on_first_page = False
            terminal_status: str | None = None
            reason = ""
            parse_errors = 0
            target_retries = 0
            target_db_failed = False
            mock_flag = int(config.settings.get("adapter", "mock") == "mock")

            safe("status:running", db.upsert_status, {
                "platform": config.platform, "target_id": target_id, "scheduled_hour": hour_text,
                "status": "running", "expected": 1, "observed": 0, "row_count": 0, "first_seen_at": started,
                "checked_at": utc_now_iso(), "missing_reason": None, "incident_id": None, "last_run_id": run_id,
                "parse_error_count": 0, "is_mock": mock_flag,
            })

            for page in range(1, max_pages + 1):
                try:
                    limiter.wait()
                    response, retries = fetch_with_retry(adapter, keyword, page, retry_settings, sleeper=sleeper, rng=rng)
                    target_retries += retries
                    raw_ref, sha256 = _write_raw_file(config, run_id, keyword, response, hour_text)
                    mock_flag = int(response.is_mock)
                    if not safe("raw_snapshot", db.save_raw_snapshot, {
                        "run_id": run_id, "target_id": target_id, "keyword": keyword, "page_number": response.page,
                        "fetched_at": response.fetched_at, "http_status": response.http_status, "body_path": raw_ref,
                        "sha256": sha256, "headers_json": json.dumps(response.headers, sort_keys=True),
                        "is_mock": int(response.is_mock), "created_at": utc_now_iso(),
                    }):
                        target_db_failed = True
                    parsed = parse_products(response.body, response.http_status)
                except FetchExhausted as exc:
                    target_retries += exc.retry_count
                    terminal_status = "failed"
                    reason = str(exc)
                    errors.append(f"{keyword}: {reason}")
                    break
                except PermissionError as exc:
                    terminal_status = "blocked"
                    reason = str(exc)
                    errors.append(f"{keyword}: {reason}")
                    break
                except Exception as exc:  # target-level isolation: one bad target should not stop the hour
                    terminal_status = "failed"
                    reason = f"{type(exc).__name__}: {exc}"
                    errors.append(f"{keyword}: {reason}")
                    logger.exception("Target failed: %s", keyword)
                    break

                if parsed.status == "blocked":
                    terminal_status = "blocked"
                    reason = parsed.reason
                    errors.append(f"{keyword}: {reason}")
                    break
                if parsed.status == "parse_failed":
                    parse_errors += 1
                    reason = parsed.reason
                    terminal_status = "partial" if entries else "parse_failed"
                    errors.append(f"{keyword}: {reason}")
                    break
                if parsed.status == "zero_result":
                    valid_page_seen = True
                    if page == 1 and not entries:
                        zero_on_first_page = True
                        terminal_status = "zero_result"
                    else:
                        terminal_status = "success"
                    break

                valid_page_seen = True
                for unit in parsed.units:
                    entries.append({"unit": unit, "page_number": page, "raw_payload_ref": raw_ref, "time_stamp": response.fetched_at, "is_mock": int(response.is_mock)})

            total_retries += target_retries
            if terminal_status is None:
                terminal_status = "success" if valid_page_seen and entries else ("zero_result" if zero_on_first_page else "failed")

            # I-4: the same placement on two pages means results reordered between requests.
            drift = find_cross_page_duplicates(entries)
            if drift:
                pagination_anomaly_count += len(drift)
                logger.warning(
                    "Pagination drift for keyword=%s: %d placement(s) repeated across pages %s; first occurrence kept",
                    keyword, len(drift), json.dumps(drift),
                )
            accepted_entries, duplicate_count = _dedupe_entries(entries)
            if duplicate_count and not drift:
                logger.info("Dropped %d repeated placement(s) for keyword=%s", duplicate_count, keyword)

            output_records: list[dict[str, Any]] = []
            rank_pairs, _ = assign_ranks([entry["unit"].product_type for entry in accepted_entries])
            for entry, (absolute_rank, relative_rank) in zip(accepted_entries, rank_pairs):
                unit: ProductUnit = entry["unit"]
                output_records.append({
                    "time_stamp": entry["time_stamp"],
                    "platform": config.platform,
                    "platform_code": config.platform_code,
                    "keyword": keyword,
                    "product_name": unit.product_name,
                    "sp": unit.sp,
                    "mrp": unit.mrp,
                    "rating": unit.rating,
                    "num_of_rating": unit.num_of_rating,
                    "tag": unit.tag,
                    "deal": unit.deal,
                    "product_image_u": unit.product_image_u,
                    "absolute_rank": absolute_rank,
                    "relative_rank": relative_rank,
                    "product_type": unit.product_type,
                    "campaign_id": unit.campaign_id,
                    "product_id": unit.product_id,
                    "product_url": unit.product_url,
                    "run_id": run_id,
                    "target_id": target_id,
                    "scheduled_hour": hour_text,
                    "page_number": entry["page_number"],
                    "raw_payload_ref": entry["raw_payload_ref"],
                    "parse_status": "ok",
                    "is_mock": entry["is_mock"],
                })

            complete_slot = terminal_status in {"success", "zero_result"} and valid_page_seen
            persisted_rows = False
            if complete_slot:
                persisted_rows = safe("products", db.sync_products, output_records, target_id, config.platform, hour_text, replace_complete=True)
            elif output_records:
                persisted_rows = safe("products", db.sync_products, output_records, target_id, config.platform, hour_text, replace_complete=False)
            if (complete_slot or output_records) and not persisted_rows:
                target_db_failed = True

            if target_db_failed and terminal_status in {"success", "zero_result"}:
                terminal_status = "failed"
                reason = "load_failed: database unavailable while loading; raw snapshots preserved, retry with --reload-raw"
                errors.append(f"{keyword}: {reason}")

            stored_rows = 0
            try:
                stored_rows = db.count_products(config.platform, target_id, hour_text)
            except sqlite3.Error:
                pass
            if terminal_status in {"success", "zero_result"}:
                completed += 1
            if terminal_status in {"failed", "blocked", "parse_failed", "partial"} and not any(e.startswith(keyword + ":") for e in errors):
                errors.append(f"{keyword}: {reason or terminal_status}")
            if persisted_rows:
                current_run_rows += len(output_records)
            status_counts[terminal_status] = status_counts.get(terminal_status, 0) + 1
            safe("status", db.upsert_status, {
                "platform": config.platform,
                "target_id": target_id,
                "scheduled_hour": hour_text,
                "status": terminal_status,
                "expected": 1,
                "observed": int(terminal_status in {"success", "zero_result"}),
                "row_count": stored_rows,
                "first_seen_at": started,
                "checked_at": utc_now_iso(),
                "missing_reason": reason or None,
                "incident_id": None,
                "last_run_id": run_id,
                "parse_error_count": parse_errors,
                "anomalies": json.dumps(drift) if drift else None,
                "is_mock": mock_flag,
            })

        if completed == len(targets) and not errors:
            run_status = "success"
        elif completed or current_run_rows:
            run_status = "partial"
        else:
            run_status = "failed"
        if db_errors:
            errors.append(f"database: {db_errors[0]}" + (f" (+{len(db_errors) - 1} more)" if len(db_errors) > 1 else ""))
        safe(
            "run:update", db.update_run, run_id,
            finished_at=utc_now_iso(), status=run_status, completed_target_count=completed,
            row_count=current_run_rows, error_count=len(errors), retry_count=total_retries,
            error_summary="; ".join(errors[:20]) or None,
        )
        summary = {
            "run_id": run_id,
            "platform": config.platform,
            "scheduled_hour": hour_text,
            "trigger": trigger,
            "status": run_status,
            "adapter_mode": "mock" if config.settings.get("adapter", "mock") == "mock" else "live-disabled",
            "expected_targets": len(targets),
            "completed_targets": completed,
            "rows_written_or_upserted": current_run_rows,
            "retry_count": total_retries,
            "error_count": len(errors),
            "status_counts": status_counts,
            "pagination_anomalies": pagination_anomaly_count,
            "rate_limit_wait_seconds": round(getattr(limiter, "total_wait", 0.0), 2),
            "db_errors": db_errors[:5],
            "errors": errors[:20],
        }
        logger.info("Run complete: %s", json.dumps(summary, ensure_ascii=False))
        return summary
    finally:
        try:
            db.release_lock(lock_name, run_id)
        except sqlite3.Error:
            logger.error("Could not release lock %s; it is cleared automatically once this run is marked finished or goes stale", lock_name)


def reload_raw(config: AppConfig, scheduled_hour: str | datetime) -> dict[str, Any]:
    """Re-run parse + load for an hour from stored raw snapshots, without any fetching (I-11)."""
    hour_text = format_hour(scheduled_hour)
    replay = ReplayAdapter(config.root, hour_text, config.platform)
    if not replay.keywords:
        raise FileNotFoundError(f"No stored raw snapshots found for {hour_text}")
    return run_pipeline(config, scheduled_hour=hour_text, trigger="reload", keywords=replay.keywords, adapter_override=replay)
