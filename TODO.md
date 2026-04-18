# Propvest — TODO

> Session state. Update at the end of every session.
> AI tools: read this after PROJECT.md to understand current state before acting.

---

## Current Status

**Phase:** 1 — Foundation (Session 8 Complete)
**Focus:** Full scoring pipeline live. Domain batch 1+2 complete for QLD/WA/NT/TAS (282 suburbs scraped; 197 scoreable after data_thin exclusion). SQM vacancy+stock data for all 4 Domain states. 13,353 signals in Supabase. Scores written to suburbs table (197 rows, 0 errors). Top suburb: Furnissdale WA 94.6.

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
  - Run manually in Supabase SQL Editor before Session 8 ✓
- [x] **Session 8: signals_loader.py PostgreSQL 21000 fix**
  - Intra-batch deduplication added by upsert key (suburb_name, state, signal_name, source)
  - 504 duplicate rows dropped (multi-LGA suburbs); 13,353 unique rows loaded; 0 errors
- [x] **Session 8: Deterministic scorer — data_thin exclusion**
  - `--score-all` now excludes data_thin suburbs (<12 house sales) from output by default
  - `--include-thin` flag added for inspection runs
  - 85 data_thin suburbs excluded from 282 total → 197 scoreable suburbs written to Supabase
- [x] **Session 8: SQM scraper — --state filter**
  - `_load_queue()` accepts `state_filter` parameter; CLI `--state` argument added
  - Enables targeted per-state scraping without consuming the full 80-suburb daily cap
- [x] **Session 8: Domain scraper — --offset batching**
  - `_load_queue()` accepts `offset` parameter; CLI `--offset` argument added
  - Enables paginated scraping: batch 2 skips first 75 in sorted queue
- [x] **Session 8: Domain batch 2 — QLD/WA/NT/TAS**
  - QLD: 44 scraped, 30 no-house-data, 1 true block (1% block rate)
  - WA: 49 scraped, 23 no-house-data, 3 true blocks (4% block rate)
  - NT: 32 scraped, 8 no-house-data, 2 true blocks (5% block rate)
  - TAS: 0 scraped (queue exhausted — TAS only has 64 Tier 1 suburbs, all done in batch 1)
- [x] **Session 8: SQM WA/NT/TAS scrapes**
  - WA: 73/75 postcodes, NT: 18/19, TAS: 14/14 — all 4 Domain states now have vacancy+stock
- [x] **Session 8: Final scoring run**
  - Tier reclassification: Hot=1290, Warm=2189, Cold=20 (290 suburbs updated)
  - Signals loaded: 13,353 rows, 0 errors
  - Scores written: 197 suburbs, 0 errors
  - Top 20: Furnissdale WA 94.6 | Girraween NT 91.7 | Bees Creek NT 89.6

---

## Up Next (Session 9 — Priority Order)

1. **NSW/VIC/SA Valuer General data downloads** (manual action — Shyam)
   - NSW: https://www.valuergeneral.nsw.gov.au/land_values/bulk_downloads.html → download latest .DAT
   - VIC: https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics → quarterly CSV
   - SA: https://www.sa.gov.au/topics/housing/buying/property-sales-information → quarterly Excel
   - Place in: `data/raw/valuer_general/` and run respective ingestors

2. **Expand scrape coverage — second pass Domain batches**
   - QLD batch 3: `--state QLD --batch 75 --offset 150`
   - WA batch 3: `--state WA --batch 75 --offset 150`
   - NT batch 2 was small (~42); NT batch 3: `--state NT --batch 75 --offset 117` (check if needed)

3. **Formal 30-suburb eval set** — backtest v1.1 scorer against known high/low performers
   - Compare top-ranked suburbs against 2021-2024 actual capital growth data
   - Identify systematic biases (NT/vacancy overweighting? Price ceiling too blunt?)

4. **v1.2 scorer improvements** (after eval set)
   - `stock_on_market`: per-dwelling normalisation (needs ABS dwelling counts)
   - `relative_median`: percentile vs suburb peers, not fixed $800k ceiling

5. **Windmill workflow definitions** — Phase 1 backlog
   - Automate weekly Domain scrape (75 Hot tier suburbs)
   - Automate weekly SQM scrape (all postcodes)
   - Trigger scorer after each scrape batch

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

| File                                       | Purpose                                                        | Regenerate with                                                      |
| ------------------------------------------ | -------------------------------------------------------------- | -------------------------------------------------------------------- |
| `data/raw/abs/erp_lga.csv`                 | Cached ABS ERP parse (546 LGAs)                                | Delete + re-run abs_ingestor.py                                      |
| `data/raw/abs/ssc_to_lga.csv`              | SAL→LGA concordance (16,630 rows)                              | Delete + re-run abs_ingestor.py                                      |
| `data/raw/abs/australian_postcodes.csv`    | data.gov.au postcode lookup (18,559 rows)                      | Auto-downloaded by geography_builder if missing                      |
| `data/raw/abs/multi_postcode_suburbs.json` | 704 suburbs with multiple postcodes (audit log)                | Re-run geography_builder                                             |
| `data/raw/tier1_candidates.json`           | 8,639 Tier 1 suburbs (abs_ingestor)                            | `python -m plugins.scrapers.abs_ingestor`                            |
| `data/raw/geography_trinity.json`          | 8,254 unique suburbs with postcodes + tiers + slugs            | `python -m plugins.scrapers.geography_builder` then tier_classifier  |
| `data/raw/domain_signals.json`             | Domain scrape results — 282 suburbs (QLD/WA/NT/TAS, batch 1+2) | `python -m plugins.scrapers.domain_next_data --state QLD --batch 75` |
| `data/raw/sqm_signals.json`                | SQM vacancy + stock — QLD/WA/NT/TAS postcodes (all 4 states)   | `python -m plugins.scrapers.sqm_scraper --state QLD --batch 75`      |
| `data/raw/scrape_log.json`                 | Run log (all scraper runs)                                     | Append-only, do not delete                                           |

## Manual Source Files (not regeneratable)

| File                                 | Source                                   |
| ------------------------------------ | ---------------------------------------- |
| `data/raw/abs/erp_lga_manual.xlsx`   | ABS Regional Population 2024-25 datacube |
| `data/raw/abs/sal_to_lga_manual.csv` | ABS ASGS SAL→LGA concordance 2021        |
