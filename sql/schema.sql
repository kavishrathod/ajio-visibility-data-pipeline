-- SQLite DDL skeleton. Complete the TODOs and justify keys in DECISIONS.md.
CREATE TABLE IF NOT EXISTS scrape_target (
  target_id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL,
  target_type TEXT NOT NULL DEFAULT 'keyword',
  target_value TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  expected_frequency_minutes INTEGER NOT NULL DEFAULT 60,
  max_pages INTEGER NOT NULL DEFAULT 2,
  priority INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE (platform, target_type, target_value)
);

CREATE TABLE IF NOT EXISTS scrape_run (
  run_id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  scheduled_hour TEXT NOT NULL,          -- UTC ISO hour start, e.g. 2026-10-16T04:30:00Z (= 10:00 IST)
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,                  -- running/success/partial/failed
  trigger TEXT NOT NULL,                 -- scheduled/manual/backfill
  expected_target_count INTEGER,
  completed_target_count INTEGER,
  row_count INTEGER,
  error_count INTEGER,
  retry_count INTEGER,
  scraper_version TEXT,
  error_summary TEXT
);
CREATE INDEX IF NOT EXISTS ix_run_hour ON scrape_run (platform, scheduled_hour);

CREATE TABLE IF NOT EXISTS visibility_product (
  -- 16 required output fields
  time_stamp TEXT NOT NULL,
  platform TEXT NOT NULL,
  platform_code TEXT NOT NULL,
  keyword TEXT NOT NULL,
  product_name TEXT,
  sp NUMERIC, mrp NUMERIC, rating REAL, num_of_rating INTEGER,
  tag TEXT NOT NULL DEFAULT '', deal TEXT NOT NULL DEFAULT '',
  product_image_url TEXT,
  absolute_rank INTEGER NOT NULL,
  relative_rank INTEGER NOT NULL,
  product_type TEXT NOT NULL,            -- Organic / SP / SB
  campaign_id TEXT,
  -- pipeline fields
  product_id TEXT,                       -- NULL allowed for SB banners with no product
  product_url TEXT,
  run_id TEXT NOT NULL REFERENCES scrape_run(run_id),
  target_id INTEGER NOT NULL REFERENCES scrape_target(target_id),
  scheduled_hour TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  raw_payload_ref TEXT NOT NULL,
  parse_status TEXT NOT NULL,
  -- idempotency key: same hour twice = same rows (upsert, not insert)
  UNIQUE (platform, target_id, scheduled_hour, absolute_rank)
);
CREATE INDEX IF NOT EXISTS ix_vis_kw_hour ON visibility_product (target_id, scheduled_hour);

CREATE TABLE IF NOT EXISTS target_hour_status (
  platform TEXT NOT NULL,
  target_id INTEGER NOT NULL,
  scheduled_hour TEXT NOT NULL,
  status TEXT NOT NULL,   -- success/partial/failed/blocked/missing/zero_result/running/not_yet_due/parse_failed
  expected INTEGER, observed INTEGER, row_count INTEGER,
  first_seen_at TEXT, checked_at TEXT, missing_reason TEXT, incident_id TEXT,
  PRIMARY KEY (platform, target_id, scheduled_hour)
);

CREATE TABLE IF NOT EXISTS alert_incident (
  incident_id TEXT PRIMARY KEY,
  alert_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  affected_targets TEXT,
  scheduled_hour TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  last_sent_at TEXT,
  send_count INTEGER NOT NULL DEFAULT 0,
  resolved_at TEXT,
  recovery_sent_at TEXT
);
-- TODO: raw_snapshot table (path, sha256, http_status, fetched_at) linked via raw_payload_ref
