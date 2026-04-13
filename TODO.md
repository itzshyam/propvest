# Propvest — TODO

> Session state. Update at the end of every session.
> AI tools: read this after PROJECT.md to understand current state before acting.

---

## Current Status

**Phase:** 1 — Foundation (Session 6 Complete)
**Focus:** Postcode enrichment complete (8,629/8,639). Domain slugs corrected. First Domain scrape run (33 signals, 0 true blocks). First SQM scrape run (50/50 postcodes, both signals). Supabase tables not yet created — blocked on manual SQL migration step.

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

---

## Up Next (Session 7 — Priority Order)

### 1. Supabase Migration (BLOCKER — manual action required)

- Go to Supabase dashboard → SQL Editor
- Run `supabase/migrations/001_create_core_tables.sql`
- Then run: `python -m plugins.scrapers.supabase_loader`
- Verify row count = 8,639

### 2. Full QLD Domain Scrape (50 per day cadence)

- Continue Domain scrape: `python -m plugins.scrapers.domain_next_data --state QLD --batch 50`
- 2,618 QLD suburbs total → ~53 daily sessions to complete
- After each batch, run reclassify: `python -m plugins.scoring.tier_classifier --mode reclassify`
- Consider running WA/NT/TAS too (smaller suburb counts)

### 3. Deterministic Scoring Engine

- Build `plugins/scoring/deterministic.py`
- Implement v1.1 weighted scoring formula
- Dynamic re-weighting for missing signals
- Test against 30-suburb eval set

### 4. Valuer General Data Downloads (manual)

- NSW: https://valuation.property.nsw.gov.au/embed/propertySalesInformation
  → Download last 12 months → save to `data/raw/nsw/`
- VIC: https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics
  → Download latest CSV → save to `data/raw/vic/`
- SA: https://www.sa.gov.au/topics/planning-and-property/land-and-property-information/property-information
  → Download latest Excel → save to `data/raw/sa/`

### 5. Windmill Local Workspace Setup

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

| File                                       | Purpose                                         | Regenerate with                                                      |
| ------------------------------------------ | ----------------------------------------------- | -------------------------------------------------------------------- |
| `data/raw/abs/erp_lga.csv`                 | Cached ABS ERP parse (546 LGAs)                 | Delete + re-run abs_ingestor.py                                      |
| `data/raw/abs/ssc_to_lga.csv`              | SAL→LGA concordance (16,630 rows)               | Delete + re-run abs_ingestor.py                                      |
| `data/raw/abs/australian_postcodes.csv`    | data.gov.au postcode lookup (18,559 rows)       | Auto-downloaded by geography_builder if missing                      |
| `data/raw/abs/multi_postcode_suburbs.json` | 704 suburbs with multiple postcodes (audit log) | Re-run geography_builder                                             |
| `data/raw/tier1_candidates.json`           | 8,639 Tier 1 suburbs (abs_ingestor)             | `python -m plugins.scrapers.abs_ingestor`                            |
| `data/raw/geography_trinity.json`          | 8,639 suburbs with postcodes + tiers + slugs    | `python -m plugins.scrapers.geography_builder` then tier_classifier  |
| `data/raw/domain_signals.json`             | Domain scrape results (keyed by slug)           | `python -m plugins.scrapers.domain_next_data --state QLD --batch 50` |
| `data/raw/sqm_signals.json`                | SQM vacancy + stock signals (keyed by postcode) | `python -m plugins.scrapers.sqm_scraper --batch 50`                  |
| `data/raw/scrape_log.json`                 | Run log (all scraper runs)                      | Append-only, do not delete                                           |

## Manual Source Files (not regeneratable)

| File                                 | Source                                   |
| ------------------------------------ | ---------------------------------------- |
| `data/raw/abs/erp_lga_manual.xlsx`   | ABS Regional Population 2024-25 datacube |
| `data/raw/abs/sal_to_lga_manual.csv` | ABS ASGS SAL→LGA concordance 2021        |
