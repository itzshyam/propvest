# Propvest — TODO

> Session state. Update at the end of every session.
> AI tools: read this after PROJECT.md to understand current state before acting.

---

## Current Status

**Phase:** 1 — Foundation (Session 5 Complete)
**Focus:** All Phase 1 scrapers built and import-tested. Domain scraper live-tested end-to-end. Geography Trinity generated (8,639 suburbs). Scrape tiers bootstrapped. Postcode enrichment is the only remaining blocker before SQM and Domain scraper can run in production.

---

## Completed

- [x] Whiteboard sessions 1-5 complete
- [x] Switched to Windmill for workflow orchestration
- [x] Plugin architecture defined
- [x] GitHub repo created (main + dev branches)
- [x] Python venv set up (.venv, Python 3.11.8)
- [x] requirements.txt defined (added curl-cffi)
- [x] `/core/schemas`: `suburb.py` (updated: sa2_code, sal_code, scrape_tier, domain_slug, data_thin), `signals.py`, `scorecard.py`
- [x] `plugins/scrapers/base_scraper.py` — abstract base with file-based scrape_log
- [x] `plugins/scrapers/abs_ingestor.py` — Growth Funnel cold filter ✓ COMPLETE
  - 193 qualifying LGAs → 8,639 Tier 1 suburbs
- [x] Domain `__NEXT_DATA__` confirmed accessible without auth (verified April 2026)
- [x] Data source map finalised by state (see DECISIONS.md Session 4)
- [x] Scraping strategy locked: curl-cffi + TLS impersonation for Domain
- [x] **Session 5: Geography Trinity built** (`plugins/scrapers/geography_builder.py`)
  - SAL→LGA joined, SA2+POA attempted (ABS URLs 404 — manual download needed)
  - Output: `data/raw/geography_trinity.json` (8,639 suburbs)
  - Supabase migration: `supabase/migrations/001_create_core_tables.sql`
  - Domain slug format confirmed: `{suburb}-{state}-{postcode}` (e.g. paddington-qld-4064)
- [x] **Session 5: Valuer General ingestors** (all three import-clean, awaiting data files)
  - `plugins/scrapers/nsw_valuer_general.py` — NSW .DAT weekly
  - `plugins/scrapers/vic_valuer_general.py` — VIC Data.Vic quarterly CSV
  - `plugins/scrapers/sa_valuer_general.py` — SA VG quarterly Excel
- [x] **Session 5: Domain scraper** (`plugins/scrapers/domain_next_data.py`)
  - curl-cffi, Apollo GraphQL **NEXT_DATA** extraction
  - Per-bedroom aggregation implemented (no aggregate entry in API)
  - Live tested: paddington-qld-4064 → all signals extracted ✓
- [x] **Session 5: Scrape Tier Classifier** (`plugins/scoring/tier_classifier.py`)
  - Bootstrap complete: Hot=1,240 / Warm=2,259 / Cold=0 (Domain states)
  - Reclassify mode ready (runs after first DOM data arrives)
- [x] **Session 5: SQM scraper** (`plugins/scrapers/sqm_scraper.py`)
  - curl-cffi, vacancy rate + stock on market by postcode
  - Queue loads from geography_trinity.json ordered by scrape tier
- [x] `config.yaml` updated to v1.1 scoring, correct plugin list, correct cadences

---

## Up Next (Session 6 — Priority Order)

### 1. Postcode Enrichment (BLOCKER for SQM + Domain production runs)

- ABS POA concordance not found at expected URLs (all return 404)
- Manual download needed from ABS ASGS correspondences page:
  https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/correspondences
- Find "CG_SAL_2021_POA_2021.zip" (or similar) and extract to `data/raw/abs/sal_to_poa_manual.csv`
- Re-run: `python -m plugins.scrapers.geography_builder` → postcodes populate
- Re-run: `python -m plugins.scoring.tier_classifier --mode bootstrap` → slugs update
- Similarly for SA2: find "CG_SAL_2021_SA2_2021.zip" → `data/raw/abs/sal_to_sa2_manual.csv`

### 2. Supabase Setup

- Create Supabase project (free tier)
- Run `supabase/migrations/001_create_core_tables.sql` in SQL Editor
- Add Supabase URL + anon key to `.env`
- Update `base_scraper.log_run()` to write to `scrape_log` table
- Write `geography_trinity.json` → `suburbs` table (bulk upsert)

### 3. First Domain Scrape Run (after postcodes populated)

- Run: `python -m plugins.scrapers.domain_next_data --state QLD --batch 50`
- Verify signals extracted correctly, block rate < 20%
- Run reclassify: `python -m plugins.scoring.tier_classifier --mode reclassify`

### 4. First SQM Scrape Run (after postcodes populated)

- Run: `python -m plugins.scrapers.sqm_scraper --batch 50`
- Verify vacancy + stock signals extracted

### 5. Valuer General Data Downloads

- NSW: https://valuation.property.nsw.gov.au/embed/propertySalesInformation
  → Download last 12 months → save to `data/raw/nsw/`
- VIC: https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics
  → Download latest CSV → save to `data/raw/vic/`
- SA: https://www.sa.gov.au/topics/planning-and-property/land-and-property-information/property-information
  → Download latest Excel → save to `data/raw/sa/`

### 6. Windmill Local Workspace Setup

- Install Windmill locally
- Define first workflow: Domain scraper orchestration
- Schedule Hot tier (weekly), Warm tier (monthly), Cold tier (quarterly)

---

## Backlog (Phase 1 — Later)

- [ ] Deterministic scoring engine `plugins/scoring/deterministic.py`
- [ ] Infrastructure pipeline scraper (ScrapeGraphAI)
- [ ] Hermes workspace configuration
- [ ] First 30-suburb eval set against v1.1 scoring model
- [ ] Populate `signals` table in Supabase from scraped data

---

## Known Data Files (gitignored, regeneratable)

| File                              | Purpose                             | Regenerate with                                                     |
| --------------------------------- | ----------------------------------- | ------------------------------------------------------------------- |
| `data/raw/abs/erp_lga.csv`        | Cached ABS ERP parse (546 LGAs)     | Delete + re-run abs_ingestor.py                                     |
| `data/raw/abs/ssc_to_lga.csv`     | SAL→LGA concordance (16,630 rows)   | Delete + re-run abs_ingestor.py                                     |
| `data/raw/tier1_candidates.json`  | 8,639 Tier 1 suburbs (abs_ingestor) | `python -m plugins.scrapers.abs_ingestor`                           |
| `data/raw/geography_trinity.json` | 8,639 suburbs with tiers + slugs    | `python -m plugins.scrapers.geography_builder` then tier_classifier |
| `data/raw/scrape_log.json`        | Run log (all scraper runs)          | Append-only, do not delete                                          |

## Manual Source Files (not regeneratable)

| File                                 | Source                                   |
| ------------------------------------ | ---------------------------------------- |
| `data/raw/abs/erp_lga_manual.xlsx`   | ABS Regional Population 2024-25 datacube |
| `data/raw/abs/sal_to_lga_manual.csv` | ABS ASGS SAL→LGA concordance 2021        |
