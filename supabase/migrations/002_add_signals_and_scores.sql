-- Propvest — Migration 002
-- Session 7 | Run in Supabase SQL Editor after 001_create_core_tables.sql.
--
-- Changes:
--   1. signals       — Normalised signal store (one row per signal per suburb)
--   2. ALTER suburbs — Add score, score_version, scored_at columns

-- ============================================================
-- 1. signals
-- ============================================================
-- One row per (suburb, signal_type, source).
-- Upsert key: (suburb_name, state, signal_name, source) — latest value wins.
--
-- Scoring signals stored here:
--   vacancy_rate        (SQM — % vacancy)
--   stock_on_market     (SQM — raw listing count)
--   median_sold_price   (DOMAIN — house median price)
--   number_sold         (DOMAIN — house sales count, trailing 12m)
--   days_on_market      (DOMAIN — median DOM)
--   sales_volume_momentum (DOMAIN — YoY % change in number_sold)
--   auction_clearance_rate (DOMAIN — %)
--   owner_occupier_pct  (DOMAIN — %)
--   renter_pct          (DOMAIN — %)
--   population_growth   (ABS — annual % ERP growth at LGA level)
--   infra_pipeline      (future — LLM confidence 0-1)

CREATE TABLE IF NOT EXISTS signals (
    id                  BIGSERIAL PRIMARY KEY,

    -- Suburb identification
    suburb_name         TEXT        NOT NULL,
    state               TEXT        NOT NULL,
    postcode            TEXT,                           -- 4-digit; SQM lookup key

    -- Signal
    signal_name         TEXT        NOT NULL,           -- e.g. 'vacancy_rate'
    value               NUMERIC(14, 4),                 -- raw numeric value
    source              TEXT        NOT NULL,           -- 'DOMAIN', 'SQM', 'ABS'
    unit                TEXT,                           -- e.g. 'percent', 'dollars', 'count'

    -- Metadata
    scraped_at          TIMESTAMPTZ NOT NULL,
    raw_json            JSONB,                          -- full scraper record (auditing)

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    -- Upsert key: latest scrape for each (suburb, signal, source) wins
    UNIQUE (suburb_name, state, signal_name, source)
);

CREATE INDEX IF NOT EXISTS idx_signals_suburb  ON signals (suburb_name, state);
CREATE INDEX IF NOT EXISTS idx_signals_type    ON signals (signal_name);
CREATE INDEX IF NOT EXISTS idx_signals_source  ON signals (source);
CREATE INDEX IF NOT EXISTS idx_signals_postcode ON signals (postcode);
CREATE INDEX IF NOT EXISTS idx_signals_scraped ON signals (scraped_at DESC);

-- Auto-update updated_at
DROP TRIGGER IF EXISTS signals_updated_at ON signals;
CREATE TRIGGER signals_updated_at
    BEFORE UPDATE ON signals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================================
-- 2. ALTER suburbs — add score columns
-- ============================================================
-- Required by deterministic.py to write scores back to Supabase.

ALTER TABLE suburbs
    ADD COLUMN IF NOT EXISTS score          NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS score_version  TEXT,
    ADD COLUMN IF NOT EXISTS scored_at      TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_suburbs_score ON suburbs (score DESC NULLS LAST);
