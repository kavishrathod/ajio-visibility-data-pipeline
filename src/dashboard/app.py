"""Streamlit dashboard. Every number comes from the same SQLite database the pipeline writes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

# `streamlit run src/dashboard/app.py` may not put the project root on sys.path.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from src.config import load_config
from src.monitoring.alerts import check_hour
from src.pipeline.completeness import format_hour
from src.pipeline.orchestrator import run_pipeline
from src.storage.database import Database
from src.timeutil import ist_label, parse_utc

COMPLETE = {"success", "zero_result"}
COLOURS = {
    "success": "#1b5e20", "zero_result": "#0d47a1", "partial": "#e65100", "parse_failed": "#b71c1c",
    "blocked": "#880e4f", "failed": "#b71c1c", "missing": "#ff1744", "running": "#6a1b9a", "not_yet_due": "#455a64",
}

st.set_page_config(page_title="AJIO Visibility Pipeline", layout="wide")
config = load_config()
db = Database(config.db_path, config.root)
db.initialize()
db.ensure_targets(config.targets)

st.title("AJIO Visibility Data Pipeline")
st.caption("Local-first assessment demo. All collection is synthetic mock data; live AJIO search collection is disabled.")
st.warning("MOCK DATA ONLY — product placements, prices, ratings and campaigns in this dashboard are simulated, not live AJIO observations.")

latest_run = db.query("SELECT * FROM scrape_run WHERE platform=? ORDER BY started_at DESC LIMIT 1", (config.platform,))
last_ok = db.query("SELECT scheduled_hour, finished_at FROM scrape_run WHERE platform=? AND status='success' ORDER BY finished_at DESC LIMIT 1", (config.platform,))
latest_hour = latest_run[0]["scheduled_hour"] if latest_run else format_hour(datetime.now(timezone.utc) - timedelta(hours=1))

left, right = st.columns([1, 3])
with left:
    if st.button("Run mock pipeline now", type="primary", use_container_width=True):
        with st.spinner("Running the local mock pipeline..."):
            st.session_state["last_run_summary"] = run_pipeline(config, trigger="manual")
        st.rerun()
with right:
    st.write(f"**Database:** `{config.db_path.relative_to(config.root) if config.db_path.is_relative_to(config.root) else config.db_path}`")
    st.write(f"**Latest scheduled hour (UTC):** `{latest_hour}`  ·  {ist_label(latest_hour)}")
if "last_run_summary" in st.session_state:
    st.json(st.session_state["last_run_summary"])

# --- headline metrics for the latest hour -------------------------------------------------
hour_counts = db.query(
    "SELECT status, COUNT(*) AS n FROM target_hour_status WHERE platform=? AND scheduled_hour=? GROUP BY status",
    (config.platform, latest_hour),
)
by_status = {r["status"]: int(r["n"]) for r in hour_counts}
expected = len(config.keywords)
complete = sum(by_status.get(s, 0) for s in COMPLETE)
missing = by_status.get("missing", 0)
open_incidents = db.query("SELECT COUNT(*) AS n FROM alert_incident WHERE resolved_at IS NULL")[0]["n"]

duration = "—"
if latest_run and latest_run[0]["finished_at"]:
    seconds = (parse_utc(latest_run[0]["finished_at"]) - parse_utc(latest_run[0]["started_at"])).total_seconds()
    duration = f"{seconds:.1f}s"

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Latest run status", latest_run[0]["status"] if latest_run else "Not run")
m2.metric("Last successful hour (UTC)", last_ok[0]["scheduled_hour"][:16].replace("T", " ") if last_ok else "none")
m3.metric("Latest run duration / rows", f"{duration} / {latest_run[0]['row_count']}" if latest_run else "—")
m4.metric("Expected / complete / missing", f"{expected} / {complete} / {missing}")
m5.metric("Open alert incidents", int(open_incidents), delta="ALERTING" if open_incidents else "clear", delta_color="inverse")

if latest_run and latest_run[0]["error_summary"]:
    with st.expander(f"Error summary for the latest run ({latest_run[0]['error_count']} error(s))"):
        st.code(latest_run[0]["error_summary"])

hour_choice = st.text_input("Check completeness for UTC hour", value=latest_hour)
if st.button("Evaluate completeness and process alert"):
    st.session_state["completeness_result"] = check_hour(db, config, hour_choice)
if "completeness_result" in st.session_state:
    st.json(st.session_state["completeness_result"])

run_tab, product_tab, status_tab, alert_tab, grid_tab = st.tabs(["Run history", "Visibility products", "Target-hour status", "Alert incidents", "Coverage grid"])

with run_tab:
    runs = db.query(
        "SELECT run_id, scheduled_hour, started_at, finished_at, status, trigger, expected_target_count, completed_target_count, "
        "row_count, error_count, retry_count, adapter_mode, error_summary FROM scrape_run WHERE platform=? ORDER BY started_at DESC LIMIT 40",
        (config.platform,),
    )
    df = pd.DataFrame(runs)
    if not df.empty:
        df["duration_s"] = [
            round((parse_utc(f) - parse_utc(s)).total_seconds(), 1) if f else None for s, f in zip(df["started_at"], df["finished_at"])
        ]
    st.caption("`skipped_overlap` rows are runs that fired while another run still held the lock; they fetched nothing.")
    st.dataframe(df, use_container_width=True, hide_index=True)

with product_tab:
    keywords = ["(all)"] + config.keywords
    pick = st.selectbox("Keyword", keywords)
    hours = [r["scheduled_hour"] for r in db.query("SELECT DISTINCT scheduled_hour FROM visibility_product WHERE platform=? ORDER BY scheduled_hour DESC LIMIT 48", (config.platform,))]
    hour_pick = st.selectbox("Scheduled hour", ["(latest 500 rows)"] + hours)
    where, params = ["platform=?"], [config.platform]
    if pick != "(all)":
        where.append("keyword=?"); params.append(pick)
    if hour_pick != "(latest 500 rows)":
        where.append("scheduled_hour=?"); params.append(hour_pick)
    products = db.query(
        "SELECT time_stamp, keyword, product_name, sp, mrp, rating, num_of_rating, tag, deal, product_type, campaign_id, absolute_rank, relative_rank, "
        f"scheduled_hour, run_id, page_number, raw_payload_ref, is_mock FROM visibility_product WHERE {' AND '.join(where)} "
        "ORDER BY scheduled_hour DESC, keyword, absolute_rank LIMIT 500", params,
    )
    if products:
        st.dataframe(pd.DataFrame(products), use_container_width=True, hide_index=True)
    else:
        st.info("No normalized product rows yet. Run the mock pipeline to populate the dashboard.")

with status_tab:
    status_rows = db.query(
        "SELECT t.target_value AS keyword, s.scheduled_hour, s.status, s.row_count, s.checked_at, s.missing_reason, s.anomalies "
        "FROM target_hour_status s JOIN scrape_target t ON s.target_id=t.target_id WHERE s.platform=? "
        "ORDER BY s.scheduled_hour DESC, t.target_value LIMIT 300", (config.platform,),
    )
    st.dataframe(pd.DataFrame(status_rows), use_container_width=True, hide_index=True)

with alert_tab:
    alerts = db.query(
        "SELECT incident_id, alert_type, severity, scheduled_hour, run_id, opened_at, last_sent_at, send_count, resolved_at, recovery_sent_at, "
        "conditions, last_error, affected_targets FROM alert_incident ORDER BY opened_at DESC LIMIT 30"
    )
    st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)

with grid_tab:
    st.subheader("Target × scheduled-hour coverage")
    st.caption("Read from target_hour_status. success and zero_result count as complete. missing (red) means no terminal status after the grace period.")
    grid_rows = db.query(
        "SELECT t.target_value AS keyword, s.scheduled_hour, s.status FROM target_hour_status s "
        "JOIN scrape_target t ON s.target_id=t.target_id WHERE s.platform=? AND t.enabled=1 ORDER BY s.scheduled_hour DESC, t.target_value",
        (config.platform,),
    )
    if grid_rows:
        grid_df = pd.DataFrame(grid_rows)
        latest_hours = sorted(grid_df["scheduled_hour"].dropna().unique(), reverse=True)[:24]
        grid_df = grid_df[grid_df["scheduled_hour"].isin(latest_hours)]
        coverage = grid_df.pivot_table(index="keyword", columns="scheduled_hour", values="status", aggfunc="last", dropna=False)
        coverage = coverage.reindex(columns=sorted(latest_hours)).fillna("missing")
        coverage.columns = [c[5:16].replace("T", " ") for c in coverage.columns]  # MM-DD HH (UTC)
        paint = lambda v: f"background-color: {COLOURS.get(v, '#333')}; color: white"
        styled = coverage.style.map(paint) if hasattr(coverage.style, "map") else coverage.style.applymap(paint)
        st.dataframe(styled, use_container_width=True, height=620)
        st.write("**Status totals:**", grid_df["status"].value_counts().to_dict())
        st.caption("Column labels are UTC hours (MM-DD HH).")
    else:
        st.info("No target-hour status records yet. Run the mock pipeline or evaluate completeness to populate the grid.")
