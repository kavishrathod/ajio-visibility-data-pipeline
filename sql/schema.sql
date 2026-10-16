PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scrape_target (
  target_id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  platform_code TEXT NOT NULL,
  target_type TEXT NOT NULL DEFAULT 'keyword',
  target_value TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  expected_frequency_minutes INTEGER NOT NULL DEFAULT 60,
  max_pages INTEGER NOT NULL DEFAULT 2,
  priority INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE (platform, target_type, target_value)
);

CREATE TABLE IF NOT EXISTS scrape_run (
  run_id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  scheduled_hour TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  trigger TEXT NOT NULL,
  expected_target_count INTEGER NOT NULL DEFAULT 0,
  completed_target_count INTEGER NOT NULL DEFAULT 0,
  row_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  retry_count INTEGER NOT NULL DEFAULT 0,
  scraper_version TEXT NOT NULL DEFAULT '1.0.0',
  adapter_mode TEXT NOT NULL DEFAULT 'mock',
  error_summary TEXT
);
CREATE INDEX IF NOT EXISTS ix_run_hour ON scrape_run(platform, scheduled_hour);
CREATE INDEX IF NOT EXISTS ix_run_started ON scrape_run(started_at);

CREATE TABLE IF NOT EXISTS raw_snapshot (
  raw_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES scrape_run(run_id),
  target_id INTEGER NOT NULL REFERENCES scrape_target(target_id),
  keyword TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  fetched_at TEXT NOT NULL,
  http_status INTEGER NOT NULL,
  body_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  headers_json TEXT NOT NULL DEFAULT '{}',
  is_mock INTEGER NOT NULL DEFAULT 1 CHECK (is_mock IN (0,1)),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_raw_run ON raw_snapshot(run_id, target_id, page_number);

CREATE TABLE IF NOT EXISTS visibility_product (
  visibility_product_id INTEGER PRIMARY KEY AUTOINCREMENT,
  time_stamp TEXT NOT NULL,
  platform TEXT NOT NULL,
  platform_code TEXT NOT NULL,
  keyword TEXT NOT NULL,
  product_name TEXT,
  sp NUMERIC,
  mrp NUMERIC,
  rating REAL,
  num_of_rating INTEGER,
  tag TEXT NOT NULL DEFAULT '',
  deal TEXT NOT NULL DEFAULT '',
  product_image_u TEXT,
  absolute_rank INTEGER NOT NULL,
  relative_rank INTEGER NOT NULL,
  product_type TEXT NOT NULL CHECK (product_type IN ('Organic','SP','SB')),
  campaign_id TEXT,
  product_id TEXT,
  product_url TEXT,
  run_id TEXT NOT NULL REFERENCES scrape_run(run_id),
  target_id INTEGER NOT NULL REFERENCES scrape_target(target_id),
  scheduled_hour TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  raw_payload_ref TEXT NOT NULL,
  parse_status TEXT NOT NULL DEFAULT 'ok',
  is_mock INTEGER NOT NULL DEFAULT 1 CHECK (is_mock IN (0,1)),
  UNIQUE (platform, target_id, scheduled_hour, absolute_rank)
);
CREATE INDEX IF NOT EXISTS ix_vis_kw_hour ON visibility_product(platform, target_id, scheduled_hour);
CREATE INDEX IF NOT EXISTS ix_vis_product_id ON visibility_product(product_id);
CREATE INDEX IF NOT EXISTS ix_vis_run ON visibility_product(run_id);

CREATE TABLE IF NOT EXISTS target_hour_status (
  platform TEXT NOT NULL,
  target_id INTEGER NOT NULL REFERENCES scrape_target(target_id),
  scheduled_hour TEXT NOT NULL,
  status TEXT NOT NULL,
  expected INTEGER,
  observed INTEGER,
  row_count INTEGER NOT NULL DEFAULT 0,
  first_seen_at TEXT,
  checked_at TEXT NOT NULL,
  missing_reason TEXT,
  incident_id TEXT,
  last_run_id TEXT REFERENCES scrape_run(run_id),
  parse_error_count INTEGER NOT NULL DEFAULT 0,
  anomalies TEXT,
  is_mock INTEGER NOT NULL DEFAULT 1 CHECK (is_mock IN (0,1)),
  PRIMARY KEY (platform, target_id, scheduled_hour)
);
CREATE INDEX IF NOT EXISTS ix_status_hour ON target_hour_status(platform, scheduled_hour, status);

CREATE TABLE IF NOT EXISTS alert_incident (
  incident_id TEXT PRIMARY KEY,
  alert_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  affected_targets TEXT NOT NULL DEFAULT '[]',
  scheduled_hour TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  last_sent_at TEXT,
  send_count INTEGER NOT NULL DEFAULT 0,
  resolved_at TEXT,
  recovery_sent_at TEXT,
  details TEXT,
  run_id TEXT,
  fingerprint TEXT,
  conditions TEXT,
  last_error TEXT
);
CREATE INDEX IF NOT EXISTS ix_alert_open ON alert_incident(alert_type, scheduled_hour, resolved_at);

CREATE TABLE IF NOT EXISTS pipeline_lock (
  lock_name TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  acquired_at TEXT NOT NULL
);
