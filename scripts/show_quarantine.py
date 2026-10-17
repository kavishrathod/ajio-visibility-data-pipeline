"""Print what was quarantined, from the SQLite database (no project imports, works from any folder).

    python scripts/show_quarantine.py                 # summary for the latest slots
    python scripts/show_quarantine.py --details       # also list the records
    python scripts/show_quarantine.py --db data/pipeline.db --limit 10
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def ist(slot: str) -> str:
    return datetime.fromisoformat(slot.replace("Z", "+00:00")).astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


parser = argparse.ArgumentParser()
parser.add_argument("--db", default="data/pipeline.db")
parser.add_argument("--limit", type=int, default=5, help="number of most recent slots to show")
parser.add_argument("--details", action="store_true", help="list individual records")
args = parser.parse_args()

conn = sqlite3.connect(args.db)
conn.row_factory = sqlite3.Row
slots = [r[0] for r in conn.execute(
    "SELECT DISTINCT scheduled_hour FROM quarantine_record ORDER BY scheduled_hour DESC LIMIT ?", (args.limit,))]
if not slots:
    print("Nothing has been quarantined.")
for slot in slots:
    print(f"\n{ist(slot)}  ({slot})  latest attempt per target")
    for r in conn.execute(
        "SELECT record_type, stage, reason_code, records, targets_affected FROM gold_quarantine_summary "
        "WHERE scheduled_hour=? ORDER BY records DESC, reason_code", (slot,)):
        print(f"  {r['records']:>4}  {r['record_type']:<5} {r['stage']:<8} {r['reason_code']:<24} targets: {r['targets_affected']}")
    if args.details:
        for r in conn.execute(
            "SELECT q.keyword, q.page_number, q.record_index, q.reason_code, q.reason_detail, q.raw_payload_ref "
            "FROM quarantine_record q JOIN target_hour_status s ON s.platform=q.platform AND s.target_id=q.target_id "
            "AND s.scheduled_hour=q.scheduled_hour AND s.last_run_id=q.run_id "
            "WHERE q.scheduled_hour=? ORDER BY q.keyword, q.page_number, q.record_index", (slot,)):
            print(f"    - {r['keyword']} p{r['page_number']} #{r['record_index']}: {r['reason_code']} ({r['reason_detail']})")
            print(f"      raw: {r['raw_payload_ref']}")
