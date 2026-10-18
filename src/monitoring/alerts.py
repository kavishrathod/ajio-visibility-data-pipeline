"""Alert detection and incident lifecycle.

One *incident* exists per platform-hour. Every trigger that is active for that
hour is listed in the same email, so 40 failing targets produce one message, not
forty. The lifecycle is: open + send -> (aggregate while nothing changes) ->
reminder after the cooldown, or immediately when the set of triggers changes ->
resolve + send exactly one recovery email.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.logger import get_logger
from src.monitoring.duplicates import DEFAULTS as DUPLICATE_DEFAULTS, detect_duplicate_spike
from src.monitoring.mailer import Mailer
from src.pipeline.completeness import evaluate_completeness, parse_hour
from src.storage.database import Database
from src.timeutil import slot_label

logger = get_logger(__name__)

# Highest priority first; the first active condition names the incident.
CONDITION_ORDER = ["run_failed", "blocked", "parser_errors", "missing_slots", "completeness", "row_drop", "duplicate_spike", "stale_data"]
SEVERITY = {
    "run_failed": "CRITICAL", "blocked": "CRITICAL", "completeness": "CRITICAL", "stale_data": "CRITICAL",
    "parser_errors": "WARNING", "missing_slots": "WARNING", "row_drop": "WARNING", "duplicate_spike": "WARNING",
}
TITLES = {
    "run_failed": "Run failed", "blocked": "Target blocked", "parser_errors": "Parser/schema errors",
    "missing_slots": "Missing data", "completeness": "Completeness below threshold",
    "row_drop": "Row-count drop", "duplicate_spike": "Duplicate spike", "stale_data": "Stale data",
}
NEXT_STEPS = {
    "run_failed": "Open the dashboard Run history and read error_summary. Fix the cause, then backfill: python -m src.main --run-once --hour <HOUR_UTC>",
    "blocked": "Do not retry or work around the block. Check robots.txt/terms and the access method, and wait or ask for permission. The target stays marked blocked.",
    "parser_errors": "Open the saved raw snapshot (raw_payload_ref) for an affected target and compare it with the parser contract. The page layout probably changed; update the parser and backfill.",
    "missing_slots": "Check whether the scheduler ran and whether an overlapping run was skipped. Backfill the hour: python -m src.main --run-once --hour <HOUR_UTC>",
    "completeness": "See the affected targets below. Rerun the hour once the cause is fixed; the incident resolves and a recovery email is sent when completeness is back above the threshold.",
    "row_drop": "Compare this run's row_count with recent runs. A genuine drop in results is possible, but also check for partial pages or layout changes.",
    "duplicate_spike": "Open the dashboard Quarantine tab (reasons duplicate_placement and cross_page_duplicate) for the affected targets and compare the raw pages (raw_payload_ref). A sudden rise usually means pagination drift or a page that repeats placements; confirm the parser did not change, then rerun the hour.",
    "stale_data": "No successful run finished within the freshness SLA. Check that the scheduler is running (python -m src.main --schedule) and the database is reachable.",
}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _alert_settings(settings: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(settings.get("alerts") or {})
    cfg.setdefault("cooldown_minutes", 60)
    cfg.setdefault("parser_error_threshold", 1)
    cfg.setdefault("row_drop_fraction", 0.5)
    cfg.setdefault("row_baseline_runs", 6)
    cfg.setdefault("stale_sla_minutes", 120)
    for key, default in DUPLICATE_DEFAULTS.items():
        cfg.setdefault(key, default)
    cfg.setdefault("dashboard_url", "http://localhost:8501")
    return cfg


def detect_conditions(db: Database, settings: dict[str, Any], result: dict[str, Any], now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return (active conditions, latest run for the hour). Pure reads; no side effects."""
    cfg = _alert_settings(settings)
    platform, hour = result["platform"], result["scheduled_hour"]
    rows = db.query(
        "SELECT t.target_value AS keyword, s.status, s.missing_reason AS reason, s.parse_error_count "
        "FROM target_hour_status s JOIN scrape_target t ON t.target_id=s.target_id "
        "WHERE s.platform=? AND s.scheduled_hour=? AND t.enabled=1 ORDER BY t.target_value",
        (platform, hour),
    )
    runs = db.query(
        "SELECT * FROM scrape_run WHERE platform=? AND scheduled_hour=? AND status NOT IN ('skipped_overlap','running') "
        "ORDER BY started_at DESC, finished_at DESC LIMIT 1",
        (platform, hour),
    )
    run = runs[0] if runs else None

    def pick(*statuses: str) -> list[dict[str, Any]]:
        return [{"keyword": r["keyword"], "status": r["status"], "reason": r["reason"]} for r in rows if r["status"] in statuses]

    conditions: list[dict[str, Any]] = []
    if run and run["status"] == "failed":
        conditions.append({"type": "run_failed", "targets": pick("failed", "blocked", "parse_failed", "partial"),
                           "reason": f"Run {run['run_id']} finished as failed after retries. {run.get('error_summary') or ''}".strip()[:400]})
    blocked = pick("blocked")
    if blocked:
        conditions.append({"type": "blocked", "targets": blocked, "reason": f"{len(blocked)} target(s) were blocked by the source (HTTP 401/403/429 or a challenge page)."})
    parser_bad = pick("parse_failed", "partial")
    if len(parser_bad) >= int(cfg["parser_error_threshold"]):
        conditions.append({"type": "parser_errors", "targets": parser_bad, "reason": f"{len(parser_bad)} target(s) returned a page the parser could not read (layout/schema drift). Raw payloads were kept; no rows were written as zero results."})
    if result["due"]:
        missing = pick("missing")
        if missing:
            conditions.append({"type": "missing_slots", "targets": missing, "reason": f"{len(missing)} target slot(s) have no terminal status after the {result.get('grace_period_minutes', 15)}-minute grace period."})
        if not result["meets_threshold"]:
            conditions.append({"type": "completeness", "targets": result["incomplete_targets"],
                               "reason": f"Completeness {result['completeness_percent']}% is below the {result['threshold'] * 100:.0f}% threshold ({result['completed_targets']}/{result['expected_targets']} targets complete)."})
    if run and run["status"] in {"success", "partial"}:
        history = db.query(
            "SELECT row_count FROM scrape_run WHERE platform=? AND status='success' AND run_id<>? AND scheduled_hour<>? "
            "AND expected_target_count=? AND row_count>0 ORDER BY started_at DESC LIMIT ?",
            (platform, run["run_id"], hour, run["expected_target_count"], int(cfg["row_baseline_runs"])),
        )
        if len(history) >= 3:
            baseline = statistics.median(r["row_count"] for r in history)
            if run["row_count"] < baseline * (1 - float(cfg["row_drop_fraction"])):
                conditions.append({"type": "row_drop", "targets": [], "reason": f"Run {run['run_id']} wrote {run['row_count']} rows; the rolling median of the last {len(history)} comparable runs is {baseline:g}."})
    spike = detect_duplicate_spike(db, cfg, platform, hour)
    if spike:
        baseline_text = (f"{spike['threshold_rate'] * 100:.1f}% ({float(cfg['duplicate_spike_multiplier']):g}x the rolling median {spike['baseline_rate'] * 100:.2f}% of the previous {spike['baseline_hours']} complete hours)"
                         if spike["baseline_rate"] is not None and spike["threshold_rate"] > float(cfg["duplicate_spike_min_rate"])
                         else f"{spike['threshold_rate'] * 100:.1f}%")
        conditions.append({
            "type": "duplicate_spike",
            "targets": [{"keyword": a["keyword"], "status": a["status"], "reason": f"{a['duplicates']} duplicate placement(s) dropped"} for a in spike["affected"]],
            "reason": (f"{spike['duplicates']} repeated placements were dropped across {len(spike['affected'])} target(s): "
                       f"{spike['rate'] * 100:.1f}% of {spike['duplicates'] + spike['kept']} units seen, at or above the spike threshold of {baseline_text} "
                       f"(and at least {spike['min_count']} duplicates)."),
        })
    sla = int(cfg["stale_sla_minutes"] or 0)
    if sla and parse_hour(hour) >= parse_hour(now) - timedelta(hours=1):
        last = db.query("SELECT MAX(finished_at) AS f FROM scrape_run WHERE platform=? AND status='success'", (platform,))[0]["f"]
        if last is None:
            conditions.append({"type": "stale_data", "targets": [], "reason": "No successful run has been recorded."})
        else:
            age = now - datetime.fromisoformat(last.replace("Z", "+00:00"))
            if age > timedelta(minutes=sla):
                conditions.append({"type": "stale_data", "targets": [], "reason": f"Last successful run finished {int(age.total_seconds() // 60)} minutes ago (SLA {sla} minutes)."})
    conditions.sort(key=lambda c: CONDITION_ORDER.index(c["type"]))
    return conditions, run


def build_alert_email(result: dict[str, Any], conditions: list[dict[str, Any]], run: dict[str, Any] | None, opened_at: str, dashboard_url: str) -> tuple[str, str]:
    top = conditions[0]["type"]
    severity = "CRITICAL" if any(SEVERITY[c["type"]] == "CRITICAL" for c in conditions) else "WARNING"
    hour = result["scheduled_hour"]
    subject = f"[AJIO VISIBILITY][{severity}] {TITLES[top]} — {slot_label(hour)}"
    affected: dict[str, dict[str, Any]] = {}
    for c in conditions:
        for t in c["targets"]:
            affected.setdefault(t["keyword"], t)
    lines = [
        "AJIO visibility pipeline alert",
        "Data mode: MOCK ONLY (synthetic data; no live AJIO collection)",
        "",
        "Platform:             AJIO",
        f"Scheduled hour:       {slot_label(hour)}",
        f"Run ID:               {run['run_id'] if run else 'no run recorded for this hour'}",
        f"Expected vs observed: {result['expected_targets']} expected target-hours, {result['completed_targets']} observed complete ({result['completeness_percent']}%)",
        f"First detected:       {opened_at}",
        f"Dashboard / logs:     {dashboard_url}  (structured JSON logs on the pipeline console)",
        "",
        "What was detected:",
    ]
    for n, c in enumerate(conditions, 1):
        lines += [f"  {n}. [{SEVERITY[c['type']]}] {TITLES[c['type']]}", f"     Reason: {c['reason']}", f"     Next step: {NEXT_STEPS[c['type']].replace('<HOUR_UTC>', hour)}"]
    lines += ["", f"Affected targets ({len(affected)}):"]
    for t in list(affected.values())[:25]:
        lines.append(f"  - {t['keyword']}: {t['status']}" + (f" — {t['reason']}" if t.get("reason") else ""))
    if len(affected) > 25:
        lines.append(f"  ... and {len(affected) - 25} more (see the dashboard Target-hour status tab)")
    return subject, "\n".join(lines) + "\n"


def build_recovery_email(result: dict[str, Any], incident: dict[str, Any], run: dict[str, Any] | None, dashboard_url: str) -> tuple[str, str]:
    hour = result["scheduled_hour"]
    subject = f"[AJIO VISIBILITY][RECOVERED] {TITLES.get(incident['alert_type'], 'Issue')} — {slot_label(hour)}"
    body = (
        "AJIO visibility pipeline recovery\nData mode: MOCK ONLY\n\n"
        f"Platform:        AJIO\nScheduled hour:  {slot_label(hour)}\n"
        f"Run ID:          {run['run_id'] if run else 'n/a'}\n"
        f"Coverage now:    {result['completed_targets']}/{result['expected_targets']} target-hours complete ({result['completeness_percent']}%)\n"
        f"Opened:          {incident['opened_at']}\nAlerts sent:     {incident['send_count']}\n"
        f"Dashboard:       {dashboard_url}\n\nAll triggers for this hour have cleared. No further action is needed.\n"
    )
    return subject, body


def apply_incident(db: Database, settings: dict[str, Any], result: dict[str, Any], conditions: list[dict[str, Any]], run: dict[str, Any] | None, now: datetime, mailer: Mailer) -> str:
    cfg = _alert_settings(settings)
    hour, now_text = result["scheduled_hour"], _iso(now)
    existing = db.query("SELECT * FROM alert_incident WHERE scheduled_hour=? AND resolved_at IS NULL ORDER BY opened_at DESC LIMIT 1", (hour,))
    incident = existing[0] if existing else None

    if not conditions:
        if incident is None:
            return "healthy" if result["due"] else "not_due"
        subject, body = build_recovery_email(result, incident, run, cfg["dashboard_url"])
        if mailer.send(subject, body):
            db.execute("UPDATE alert_incident SET resolved_at=?, recovery_sent_at=?, last_error=NULL WHERE incident_id=?", (now_text, now_text, incident["incident_id"]))
            return "resolved"
        db.execute("UPDATE alert_incident SET last_error=? WHERE incident_id=?", ("recovery email delivery failed; will retry", incident["incident_id"]))
        return "recovery_send_failed"

    fingerprint = hashlib.sha256(",".join(sorted(c["type"] for c in conditions)).encode()).hexdigest()[:16]
    affected = sorted({t["keyword"] for c in conditions for t in c["targets"]})
    severity = "CRITICAL" if any(SEVERITY[c["type"]] == "CRITICAL" for c in conditions) else "WARNING"
    details = json.dumps([{"type": c["type"], "reason": c["reason"]} for c in conditions])
    should_send, state = False, "aggregated"
    if incident is None:
        incident_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO alert_incident (incident_id,alert_type,severity,affected_targets,scheduled_hour,opened_at,send_count,details,run_id,fingerprint,conditions) VALUES (?,?,?,?,?,?,0,?,?,?,?)",
            (incident_id, conditions[0]["type"], severity.lower(), json.dumps(affected), hour, now_text, details, run["run_id"] if run else None, fingerprint, json.dumps([c["type"] for c in conditions])),
        )
        incident = db.query("SELECT * FROM alert_incident WHERE incident_id=?", (incident_id,))[0]
        should_send, state = True, "sent"
    else:
        last_sent = incident.get("last_sent_at")
        cooldown_over = bool(last_sent) and now - datetime.fromisoformat(last_sent.replace("Z", "+00:00")) >= timedelta(minutes=int(cfg["cooldown_minutes"]))
        if incident.get("fingerprint") != fingerprint:
            should_send, state = True, "sent"  # status change: the set of active triggers is different
        elif not last_sent:
            should_send, state = True, "sent"  # an earlier delivery failed; retry
        elif cooldown_over:
            should_send, state = True, "reminder_sent"
        db.execute(
            "UPDATE alert_incident SET alert_type=?, severity=?, affected_targets=?, details=?, run_id=?, fingerprint=?, conditions=? WHERE incident_id=?",
            (conditions[0]["type"], severity.lower(), json.dumps(affected), details, run["run_id"] if run else None, fingerprint, json.dumps([c["type"] for c in conditions]), incident["incident_id"]),
        )
    if not should_send:
        return "aggregated"
    subject, body = build_alert_email(result, conditions, run, incident["opened_at"], cfg["dashboard_url"])
    if mailer.send(subject, body):
        db.execute("UPDATE alert_incident SET last_sent_at=?, send_count=send_count+1, last_error=NULL WHERE incident_id=?", (now_text, incident["incident_id"]))
        return state
    db.execute("UPDATE alert_incident SET last_error=? WHERE incident_id=?", ("alert email delivery failed; incident kept, will retry at next check", incident["incident_id"]))
    return "send_failed"


def check_hour(db: Database, config, hour: str | datetime | None = None, now: datetime | None = None, mailer: Mailer | None = None) -> dict[str, Any]:
    """Evaluate one hour end to end: completeness, triggers, and the incident lifecycle."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    grace = int(config.settings.get("grace_period_minutes", 15))
    result = evaluate_completeness(db, config.platform, hour, grace_period_minutes=grace,
                                   threshold=float(config.settings.get("completeness_threshold", 0.98)), now=now)
    result["grace_period_minutes"] = grace
    conditions, run = detect_conditions(db, config.settings, result, now)
    result["conditions"] = [c["type"] for c in conditions]
    result["alert_state"] = apply_incident(db, config.settings, result, conditions, run, now, mailer or Mailer(config.root))
    return result
