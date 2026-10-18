
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

from src.config import load_config
from src.monitoring.alerts import check_hour
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from tests.helpers import FakeMailer, ScriptedAdapter, fixture_text, no_sleep, resp

PROJECT = Path(__file__).resolve().parents[1]
DEMO = PROJECT / "demo_duplicate_spike_data" / "project"
HOURS = [
    "2026-10-16T10:30:00Z",
    "2026-10-16T11:30:00Z",
    "2026-10-16T12:30:00Z",
    "2026-10-16T13:30:00Z",
]
KEYWORDS = [f"men shirt {n}" for n in range(1, 6)]

if DEMO.exists():
    print(f"Demo folder already exists: {DEMO}")
    print("Stop here; inspect it before rerunning this script.")
    raise SystemExit(1)

(DEMO / "config").mkdir(parents=True)
(DEMO / "sql").mkdir()
shutil.copy2(PROJECT / "config" / "settings.yaml", DEMO / "config" / "settings.yaml")
shutil.copy2(PROJECT / "sql" / "schema.sql", DEMO / "sql" / "schema.sql")

targets = json.loads((PROJECT / "config" / "targets.json").read_text(encoding="utf-8"))
targets["keywords"] = KEYWORDS
targets["expected_zero_result_keywords"] = []
(DEMO / "config" / "targets.json").write_text(
    json.dumps(targets, indent=2), encoding="utf-8"
)

config = load_config(DEMO)
config.settings["fixtures_dir"] = str(PROJECT / "tests" / "fixtures")
config.settings.setdefault("alerts", {})["stale_sla_minutes"] = 0
config.settings.setdefault("rate_limit", {})["enabled"] = False

def run_hour(hour, html):
    def fetch(keyword, page, call_number):
        if page == 1:
            return resp(html, keyword=keyword)
        return resp(fixture_text("zero_results.html"), keyword=keyword, page=2)

    return run_pipeline(
        config, hour,
        adapter_override=ScriptedAdapter(fetch),
        sleeper=no_sleep,
    )

try:
    for hour in HOURS[:3]:
        run_hour(hour, fixture_text("small_page.html"))

    spike_hour = HOURS[3]
    run_hour(spike_hour, fixture_text("duplicate_spike.html"))

    db = Database(config.db_path, config.root)
    db.initialize()
    db.ensure_targets(config.targets)

    mailer = FakeMailer()
    result = check_hour(
        db, config, spike_hour,
        now=datetime(2026, 10, 16, 14, 20, tzinfo=timezone.utc),
        mailer=mailer,
    )

    print("Demo database:", config.db_path)
    print("Alert conditions:", result.get("conditions"))
    print("Alert state:", result.get("alert_state"))
    print("Fake alert emails:", len(mailer.sent))
    if mailer.sent:
        print("Subject:", mailer.sent[0][0])
    print("Mock data only; no real email was sent.")
except Exception:
    shutil.rmtree(DEMO.parent, ignore_errors=True)
    raise
