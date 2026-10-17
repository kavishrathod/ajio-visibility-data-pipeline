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

-- ---------------------------------------------------------------------------
-- QUARANTINE: records (or whole pages) that were rejected on the way to Silver, kept with the
-- reason and enough payload to diagnose them. Append-only per run: the same run never stores a
-- record twice (UNIQUE key), and earlier attempts stay as history. gold_quarantine_summary below
-- counts only the latest attempt per target and slot.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quarantine_record (
  quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES scrape_run(run_id),
  platform TEXT NOT NULL,
  target_id INTEGER NOT NULL REFERENCES scrape_target(target_id),
  keyword TEXT NOT NULL,
  scheduled_hour TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  record_type TEXT NOT NULL CHECK (record_type IN ('card', 'unit', 'page')),
  record_index INTEGER NOT NULL DEFAULT 0,      -- card position on the page / entry order in the target; 0 for a whole page
  stage TEXT NOT NULL CHECK (stage IN ('parse', 'validate', 'dedupe')),
  reason_code TEXT NOT NULL,
  reason_detail TEXT,
  payload_json TEXT,
  raw_payload_ref TEXT,
  is_mock INTEGER NOT NULL DEFAULT 1 CHECK (is_mock IN (0,1)),
  created_at TEXT NOT NULL,
  UNIQUE (run_id, target_id, page_number, record_type, record_index, reason_code)
);
CREATE INDEX IF NOT EXISTS ix_quarantine_slot ON quarantine_record(platform, scheduled_hour, target_id);
CREATE INDEX IF NOT EXISTS ix_quarantine_reason ON quarantine_record(reason_code);

-- ---------------------------------------------------------------------------
-- GOLD layer: read-only views over Silver (visibility_product) and the status
-- ledger (target_hour_status). Views, not tables: they are always consistent
-- with the data, rerunning an hour or a backfill needs no refresh job, and
-- they cannot hold duplicates. DROP + CREATE keeps older local databases current.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS gold_keyword_hour;
CREATE VIEW gold_keyword_hour AS
SELECT
  s.platform,
  s.target_id,
  t.target_value                                              AS keyword,
  s.scheduled_hour,
  s.status,
  COUNT(p.absolute_rank)                                      AS total_units,
  COALESCE(SUM(p.product_type = 'Organic'), 0)                AS organic_units,
  COALESCE(SUM(p.product_type = 'SP'), 0)                     AS sp_units,
  COALESCE(SUM(p.product_type = 'SB'), 0)                     AS sb_units,
  ROUND(100.0 * COALESCE(SUM(p.product_type IN ('SP', 'SB')), 0)
        / NULLIF(COUNT(p.absolute_rank), 0), 1)               AS paid_share_pct,
  COUNT(DISTINCT p.product_id)                                AS distinct_products,
  MIN(p.sp)                                                   AS min_sp,
  ROUND(AVG(p.sp), 2)                                         AS avg_sp,
  MAX(p.sp)                                                   AS max_sp,
  ROUND(AVG(p.rating), 2)                                     AS avg_rating
FROM target_hour_status s
JOIN scrape_target t ON t.target_id = s.target_id
LEFT JOIN visibility_product p
       ON p.platform = s.platform AND p.target_id = s.target_id AND p.scheduled_hour = s.scheduled_hour
GROUP BY s.platform, s.target_id, s.scheduled_hour;

-- Organic rank vs sponsored placements for the same product, per keyword and hour.
-- A product with both ranks set was shown as organic and as a paid unit on one page (I-6).
DROP VIEW IF EXISTS gold_product_placement;
CREATE VIEW gold_product_placement AS
SELECT
  platform,
  target_id,
  keyword,
  scheduled_hour,
  product_id,
  MIN(CASE WHEN product_type = 'Organic' THEN relative_rank END) AS best_organic_rank,
  MIN(CASE WHEN product_type = 'SP'      THEN relative_rank END) AS best_sp_rank,
  SUM(product_type = 'Organic')                                   AS organic_placements,
  SUM(product_type = 'SP')                                        AS sp_placements
FROM visibility_product
WHERE product_id IS NOT NULL
GROUP BY platform, target_id, scheduled_hour, product_id;

-- One row per platform-hour: coverage and volume. Reflects materialised statuses,
-- so run --check-completeness for an hour to turn never-run targets into 'missing'.
DROP VIEW IF EXISTS gold_hour_summary;
CREATE VIEW gold_hour_summary AS
SELECT
  platform,
  scheduled_hour,
  COUNT(*)                                                        AS targets,
  SUM(status IN ('success', 'zero_result'))                       AS complete,
  SUM(status = 'zero_result')                                     AS zero_result,
  SUM(status = 'missing')                                         AS missing,
  SUM(status IN ('failed', 'parse_failed', 'blocked', 'partial')) AS problem,
  SUM(status IN ('running', 'not_yet_due'))                       AS pending,
  SUM(row_count)                                                  AS rows,
  ROUND(100.0 * SUM(status IN ('success', 'zero_result')) / COUNT(*), 1) AS completeness_pct
FROM target_hour_status
GROUP BY platform, scheduled_hour;

-- Latest attempt only: a quarantine row counts when its run is the one that last wrote the
-- target-hour status, so a rerun or reload of an hour never doubles the totals.
DROP VIEW IF EXISTS gold_quarantine_summary;
CREATE VIEW gold_quarantine_summary AS
SELECT
  q.platform,
  q.scheduled_hour,
  q.record_type,
  q.stage,
  q.reason_code,
  COUNT(*)                    AS records,
  COUNT(DISTINCT q.target_id) AS targets_affected
FROM quarantine_record q
JOIN target_hour_status s
  ON s.platform = q.platform AND s.target_id = q.target_id
 AND s.scheduled_hour = q.scheduled_hour AND s.last_run_id = q.run_id
GROUP BY q.platform, q.scheduled_hour, q.record_type, q.stage, q.reason_code;
