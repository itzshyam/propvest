# Propvest — TODO

> Session state. Update at the end of every session.
> AI tools: read this after PROJECT.md to understand current state before acting.

---

## Current Status

**Phase:** 1 — Foundation (Session 7 Complete)
**Focus:** Supabase suburbs table loaded (8,254 unique rows). Domain scrape complete for QLD/WA/NT/TAS (75 suburbs, 171 signals). Deterministic scoring engine v1.1 built and tested. Signals loader built and dry-run validated (11,964 rows ready). **Blocked on manual migration 002** before signals + scores can write to Supabase.

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
- [x] **Session 6: Postcode enrichment** (`plugins/scrapers/geography_builder.py`)
  - data.gov.au Australian Postcodes CSV used as fallback (ABS SAL→POA all 404)
  - 8,629/8,639 suburbs now have postcodes (99.9%)
  - 10 missing: national parks + territories (no postal addresses)
  - 704 multi-postcode suburbs logged to `data/raw/abs/multi_postcode_suburbs.json`
  - `_domain_slug()` fixed: strip ABS disambiguation parens before slugifying
  - `python-dotenv` added to requirements.txt
- [x] **Session 6: Domain slugs corrected**
  - "Paddington (Qld)" → slug `paddington-qld-4064` ✓ (was `paddington-qld-qld-4064`)
  - 7/8 verification tests passed (Braddon/ACT missing — 0 ACT suburbs qualify Tier 1)
  - geography_trinity.json rebuilt, tier_classifier re-run (Hot=1,240, Warm=2,259)
- [x] **Session 6: base_scraper.log_run() updated**
  - Dual-write: Supabase scrape_log table (primary) + file fallback (always)
  - Supabase write currently failing (tables not created yet) — file fallback active
- [x] **Session 6: supabase_loader.py created** (`plugins/scrapers/supabase_loader.py`)
  - Bulk upsert script ready (8,639 suburbs, 18 batches of 500)
  - Dry-run tested successfully
  - Awaiting manual SQL migration before live run
- [x] **Session 6: 001_create_core_tables.sql updated**
  - UNIQUE constraint changed from `(state, suburb_name, postcode)` to `(suburb_name, state)` — NULL postcode safe
  - domain_slug comment corrected to show correct format
- [x] **Session 6: Domain scraper first run** (QLD, batch 50)
  - 33 signals extracted, 17 legitimate no-data (rural hamlets), 0 true WAF blocks
  - All signals extracted correctly: median_sold_price, number_sold, DOM, etc.
  - Block detection fixed: distinguishes true WAF blocks from no-house-data responses
  - Tier reclassification run: Hot=1,238, Warm=2,261 (33 suburbs updated from real DOM)
- [x] **Session 6: SQM scraper fixed + first run** (batch 50)
  - `graph_listings.php` URL was 404 — updated to `/property/total-property-listings`
  - Vacancy parser updated for `var data = [{vr,...}]` JSON format
  - Stock parser updated for `{r30, r60, r90, r180, r180p}` age-bucket format
  - 50/50 postcodes succeeded: both vacancy_rate + stock_on_market present
  - Vacancy range: 0.00–4.41%, stock range: 5–1,089
- [x] **Session 7: Supabase suburbs table loaded** (`plugins/scrapers/supabase_loader.py`)
  - Fixed PostgreSQL 21000 error: deduplication added before batching
  - 385 duplicate (suburb_name, state) pairs dropped — suburbs spanning multiple LGAs
  - 8,254 unique suburbs loaded into Supabase (not 8,639 — SAL→LGA M:N join creates duplicates)
  - Dominant-LGA row kept (highest population) per duplicate pair
- [x] **Session 7: geography_trinity.json rebuilt**
  - Root cause: `australian_postcodes.csv` was missing from data/raw/abs/ (silent download fail in S6)
  - Re-run geography_builder → auto-downloaded CSV → 8,629/8,639 postcodes filled
  - Re-run tier_classifier → Hot=1,277, Warm=2,209, Cold=13 (post-reclassification from real DOM data)
- [x] **Session 7: Domain scrape — QLD/WA/NT/TAS** (75 suburbs, 0 true blocks)
  - QLD: 49 suburbs scraped, WA: 52, NT: 36, TAS: 34 (171 total; 1 overlap overwrote)
  - 0% true WAF block rate across all 4 states
  - All extracted signals stored in `data/raw/domain_signals.json`
  - Tier reclassification run after all 4 states: Hot=1,277, Warm=2,209, Cold=13
- [x] **Session 7: SQM scrape — QLD postcodes** (75 postcodes)
  - vacancy_rate + stock_on_market for 75 QLD postcodes
  - Stored in `data/raw/sqm_signals.json`
- [x] **Session 7: Deterministic scoring engine built** (`plugins/scoring/deterministic.py`)
  - v1.1 with all 6 signals + dynamic re-weighting
  - All normalisation ranges from CONTEXT.md scoring spec
  - 3 built-in test cases pass: high-vacancy=13.3 (<30 ✓), high-growth=84.8 (>65 ✓), re-weight sum=1.0000 ✓
  - `--score-all` CLI mode: reads trinity + signals → prints ranked table
  - `--write-supabase` flag: writes scores to suburbs.score column (blocked until migration 002 run)
- [x] **Session 7: Signals loader built** (`plugins/scrapers/signals_loader.py`)
  - Reads domain_signals.json + sqm_signals.json + geography_trinity.json
  - Dry-run validated: 11,964 rows (170 Domain × ~6 signals + 75 SQM × suburbs per postcode + 8,639 ABS)
  - Upsert key: (suburb_name, state, signal_name, source)
  - Blocked by missing migration 002 — `signals` table does not exist yet
- [x] **Session 7: Migration 002 SQL written** (`supabase/migrations/002_add_signals_and_scores.sql`)
  - Creates `signals` table with UNIQUE(suburb_name, state, signal_name, source)
  - ALTERs suburbs table: adds `score NUMERIC(5,2)`, `score_version TEXT`, `scored_at TIMESTAMPTZ`
  - **NOT YET RUN** — manual action required in Supabase SQL Editor before Session 8

---

## Up Next (Session 8 — Priority Order)

### MANUAL ACTIONS REQUIRED BEFORE SESSION 8 STARTS

> Shyam must do these steps manually before the next AI session:

1. **Run migration 002 in Supabase SQL Editor**
   - Go to: https://nqnvijfqnxfuwoygfnhs.supabase.co → SQL Editor
   - Open and run: `supabase/migrations/002_add_signals_and_scores.sql`
   - Verify: `signals` table created, `suburbs` table has `score` column

2. **Load signals into Supabase**
   - `cd C:\Users\itzsh\Documents\Projects\Propvest`
   - `.venv/Scripts/python -m plugins.scrapers.signals_loader`
   - Expected: ~11,964 rows upserted, 0 errors

3. **Run deterministic scorer**
   - `.venv/Scripts/python -m plugins.scoring.deterministic --score-all --write-supabase`
   - Expected: 170 suburbs scored and written to suburbs.score

### Session 8 Objectives (once manual steps done)

1. **Verify Supabase state**: signals queryable by suburb, scores visible in suburbs table
2. **Continue Domain scrape**: Next batch QLD (75 suburbs, `--state QLD --batch 75 --offset 75`)
3. **SQM for WA/NT/TAS**: Run SQM scraper for remaining states' postcodes
4. **Scoring eval**: Run scorer on all available suburbs, review top 20 for sanity

---

## Backlog (Phase 1 — Later)

- [ ] Infrastructure pipeline scraper (ScrapeGraphAI) — `infra_pipeline` signal always None until built
- [ ] Hermes workspace configuration
- [ ] First 30-suburb eval set against v1.1 scoring model (formal backtest)
- [ ] Valuer General data downloads (NSW/VIC/SA — manual download steps in prior TODO)
- [ ] Windmill local workspace setup + first Domain workflow
- [ ] v1.2 scorer: per-dwelling stock_on_market normalisation; relative_median vs neighbours not ceiling

---

## Known Data Files (gitignored, regeneratable)

| File                                       | Purpose                                             | Regenerate with                                                      |
| ------------------------------------------ | --------------------------------------------------- | -------------------------------------------------------------------- |
| `data/raw/abs/erp_lga.csv`                 | Cached ABS ERP parse (546 LGAs)                     | Delete + re-run abs_ingestor.py                                      |
| `data/raw/abs/ssc_to_lga.csv`              | SAL→LGA concordance (16,630 rows)                   | Delete + re-run abs_ingestor.py                                      |
| `data/raw/abs/australian_postcodes.csv`    | data.gov.au postcode lookup (18,559 rows)           | Auto-downloaded by geography_builder if missing                      |
| `data/raw/abs/multi_postcode_suburbs.json` | 704 suburbs with multiple postcodes (audit log)     | Re-run geography_builder                                             |
| `data/raw/tier1_candidates.json`           | 8,639 Tier 1 suburbs (abs_ingestor)                 | `python -m plugins.scrapers.abs_ingestor`                            |
| `data/raw/geography_trinity.json`          | 8,254 unique suburbs with postcodes + tiers + slugs | `python -m plugins.scrapers.geography_builder` then tier_classifier  |
| `data/raw/domain_signals.json`             | Domain scrape results — 171 signals (QLD/WA/NT/TAS) | `python -m plugins.scrapers.domain_next_data --state QLD --batch 75` |
| `data/raw/sqm_signals.json`                | SQM vacancy + stock — 75 QLD postcodes              | `python -m plugins.scrapers.sqm_scraper --batch 75`                  |
| `data/raw/scrape_log.json`                 | Run log (all scraper runs)                          | Append-only, do not delete                                           |

## Manual Source Files (not regeneratable)

| File                                 | Source                                   |
| ------------------------------------ | ---------------------------------------- |
| `data/raw/abs/erp_lga_manual.xlsx`   | ABS Regional Population 2024-25 datacube |
| `data/raw/abs/sal_to_lga_manual.csv` | ABS ASGS SAL→LGA concordance 2021        |
