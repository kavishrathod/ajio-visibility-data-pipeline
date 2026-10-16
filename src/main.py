"""CLI entry point: one-off runs, backfills, reload from raw, hourly scheduling, health checks, demo."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from src.config import load_config
from src.logger import get_logger
from src.monitoring.alerts import check_hour
from src.pipeline.completeness import format_hour
from src.pipeline.orchestrator import reload_raw, run_pipeline
from src.storage.database import Database

logger = get_logger(__name__)


def _hour_arg(value: str | None) -> str:
    return format_hour(value) if value else format_hour()


def _check_completeness(config, hour: str | None) -> dict:
    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)
    selected_hour = format_hour(hour) if hour else format_hour(datetime.now(timezone.utc) - timedelta(hours=1))
    result = check_hour(db, config, selected_hour)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def _run_one(config, hour: str | None, trigger: str, keywords: list[str] | None = None) -> dict:
    summary = run_pipeline(config, scheduled_hour=hour, trigger=trigger, keywords=keywords)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def _demo(config) -> None:
    """Reproduce the 'missing slot, then late backfill' story for the evidence pack.

    Uses three recent completed hours: H-3 and H-1 are collected, H-2 is deliberately skipped.
    The completeness check flags H-2 and sends one alert; the backfill then fills it and the
    next check resolves the incident with exactly one recovery email.
    """
    now_floor = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    h3, h2, h1 = (format_hour(now_floor - timedelta(hours=n)) for n in (3, 2, 1))
    print(f"== Demo: collect {h3} and {h1}; skip {h2} on purpose ==")
    for hour in (h3, h1):
        _run_one(config, hour, "backfill")
    print(f"== Completeness check for the skipped hour {h2} (expect: missing slots + one alert) ==")
    _check_completeness(config, h2)
    print(f"== Same check again (expect: aggregated, no second email) ==")
    _check_completeness(config, h2)
    print(f"== Late backfill of {h2} ==")
    _run_one(config, h2, "backfill")
    print("== Check again (expect: resolved + one recovery email) ==")
    _check_completeness(config, h2)
    print(f"Alert emails are in the outbox folder (data/outbox by default). Dashboard: python -m streamlit run src/dashboard/app.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="AJIO visibility pipeline (mock data by default)")
    parser.add_argument("--run-once", action="store_true", help="run every configured target for one hour")
    parser.add_argument("--schedule", action="store_true", help="run immediately, then at the top of every UTC hour")
    parser.add_argument("--check-completeness", action="store_true", help="materialize missing slots, evaluate triggers, process the incident/alert")
    parser.add_argument("--reload-raw", action="store_true", help="re-parse and load an hour from stored raw snapshots (no fetching); needs --hour")
    parser.add_argument("--demo", action="store_true", help="demonstrate a missing slot, its alert, a late backfill and the recovery email")
    parser.add_argument("--hour", help="target hour in UTC, e.g. 2026-10-16T14:00:00Z")
    parser.add_argument("--trigger", choices=["scheduled", "manual", "backfill"], help="override the recorded trigger (cron uses 'scheduled')")
    parser.add_argument("--backfill-hours", type=int, default=0, help="run the last N completed hourly slots")
    parser.add_argument("--keyword", action="append", help="limit a run to a configured keyword; may be repeated")
    parser.add_argument("--root", help="project root (defaults to this repository)")
    args = parser.parse_args()
    config = load_config(args.root)

    if config.settings.get("adapter", "mock") == "live":
        parser.error("Live collection is deliberately disabled; set adapter: mock in config/settings.yaml")

    if args.demo:
        _demo(config)
        return

    if args.reload_raw:
        if not args.hour:
            parser.error("--reload-raw needs --hour")
        print(json.dumps(reload_raw(config, args.hour), indent=2, ensure_ascii=False))
        return

    if args.check_completeness:
        _check_completeness(config, args.hour)
        return

    if args.backfill_hours:
        if args.backfill_hours < 1 or args.backfill_hours > 168:
            parser.error("--backfill-hours must be between 1 and 168")
        now_floor = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for offset in range(args.backfill_hours, 0, -1):
            _run_one(config, format_hour(now_floor - timedelta(hours=offset)), "backfill", args.keyword)
        return

    if args.schedule:
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
        except ImportError:
            parser.error("Hourly scheduling requires APScheduler. Install dependencies with: pip install -r requirements.txt")

        def scheduled_job() -> None:
            # The slot is decided once, at fire time. The run keeps this hour even if it ends after the boundary.
            now_utc = datetime.now(timezone.utc)
            hour = format_hour(now_utc)
            previous_hour = format_hour(now_utc - timedelta(hours=1))
            try:
                _run_one(config, hour, "scheduled")
            except Exception:
                logger.exception("Scheduled pipeline run failed")
            # The previous slot's grace period has elapsed by now: evaluate it (alerts and recovery).
            for check in (previous_hour, hour):
                try:
                    _check_completeness(config, check)
                except Exception:
                    logger.exception("Scheduled completeness check failed for %s", check)

        scheduler = BlockingScheduler(timezone="UTC")
        # max_instances=1 stops APScheduler overlapping itself; the database lock also protects separate processes.
        scheduler.add_job(scheduled_job, "cron", minute=0, id="hourly-ajio-pipeline", max_instances=1, coalesce=True, misfire_grace_time=600)
        scheduled_job()
        logger.info("Hourly scheduler running in foreground; press Ctrl+C to stop")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown(wait=False)
        return

    if args.run_once:
        trigger = args.trigger or ("backfill" if args.hour else "manual")
        _run_one(config, _hour_arg(args.hour), trigger, args.keyword)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
