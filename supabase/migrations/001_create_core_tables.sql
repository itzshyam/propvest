-- Propvest — Core Tables Migration
-- Session 5 | Run this in Supabase SQL Editor once, then manage via Supabase dashboard.
--
-- Tables:
--   suburbs      — Geography Trinity: master suburb lookup (SAL ↔ postcode ↔ SA2 ↔ LGA)
--   scrape_log   — Audit trail for all scraper runs
--   api_cost_log — Token/cost tracking for all LLM calls

-- ============================================================
-- suburbs
-- ============================================================
CREATE TABLE IF NOT EXISTS suburbs (
    id                  BIGSERIAL PRIMARY KEY,

    -- Geography Trinity identifiers
    suburb_name         TEXT        NOT NULL,
    state               TEXT        NOT NULL,
    postcode            TEXT,                           -- 4-digit, from ABS POA concordance
    sal_code            TEXT,                           -- ABS SAL code (suburb ID)
    sa2_code            TEXT,                           -- ABS SA2 code (for signal joins)
    sa2_name            TEXT,
    lga_code            TEXT,                           -- ABS LGA code (for infra joins)
    lga_name            TEXT,

    -- Growth Funnel metadata
    population          INTEGER,                        -- LGA-level ERP from ABS
    abs_growth_rate     NUMERIC(5, 2),                  -- Annual % growth at LGA level
    is_tier1            BOOLEAN     DEFAULT FALSE,      -- Passed Growth Funnel cold filter

    -- Scraping
    scrape_tier         TEXT        CHECK (scrape_tier IN ('Hot', 'Warm', 'Cold')),
    domain_slug         TEXT,                           -- e.g. "paddington-qld-4064"

    -- Signal outputs (populated by scrapers, updated on each run)
    median_house_price  NUMERIC(12, 2),
    data_thin           BOOLEAN     DEFAULT FALSE,      -- TRUE if numberSold < 12

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    -- Natural key: suburb_name + state (postcode excluded — 10 suburbs have NULL postcode)
    UNIQUE (suburb_name, state)
);

CREATE INDEX IF NOT EXISTS idx_suburbs_state        ON suburbs (state);
CREATE INDEX IF NOT EXISTS idx_suburbs_is_tier1     ON suburbs (is_tier1);
CREATE INDEX IF NOT EXISTS idx_suburbs_scrape_tier  ON suburbs (scrape_tier);
CREATE INDEX IF NOT EXISTS idx_suburbs_postcode     ON suburbs (postcode);
CREATE INDEX IF NOT EXISTS idx_suburbs_sa2_code     ON suburbs (sa2_code);
CREATE INDEX IF NOT EXISTS idx_suburbs_lga_code     ON suburbs (lga_code);
CREATE INDEX IF NOT EXISTS idx_suburbs_domain_slug  ON suburbs (domain_slug);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS suburbs_updated_at ON suburbs;
CREATE TRIGGER suburbs_updated_at
    BEFORE UPDATE ON suburbs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================================
-- scrape_log
-- ============================================================
-- Mirror of base_scraper.log_run() — swap in the Supabase insert
-- once this table exists.
CREATE TABLE IF NOT EXISTS scrape_log (
    id                  BIGSERIAL PRIMARY KEY,
    source              TEXT        NOT NULL,           -- e.g. "ABS", "DOMAIN", "SQM"
    ran_at              TIMESTAMPTZ DEFAULT NOW(),
    records_processed   INTEGER,
    error               TEXT,                           -- NULL on success
    duration_ms         INTEGER
);

CREATE INDEX IF NOT EXISTS idx_scrape_log_source    ON scrape_log (source);
CREATE INDEX IF NOT EXISTS idx_scrape_log_ran_at    ON scrape_log (ran_at DESC);


-- ============================================================
-- api_cost_log
-- ============================================================
-- Every LLM call must write a row here (agents.md rule).
CREATE TABLE IF NOT EXISTS api_cost_log (
    id                  BIGSERIAL PRIMARY KEY,
    provider            TEXT        NOT NULL,           -- "claude", "openai"
    model               TEXT,
    tokens_in           INTEGER,
    tokens_out          INTEGER,
    cost_usd            NUMERIC(8, 6),
    called_at           TIMESTAMPTZ DEFAULT NOW(),
    purpose             TEXT                            -- e.g. "infra_parse", "deep_dive"
);

CREATE INDEX IF NOT EXISTS idx_api_cost_log_provider    ON api_cost_log (provider);
CREATE INDEX IF NOT EXISTS idx_api_cost_log_called_at   ON api_cost_log (called_at DESC);
