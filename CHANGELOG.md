# Propvest — Changelog

> What changed and when. Update at the end of any session where code, config, or architecture changes.
> AI tools: read this to understand what has recently changed before acting.

---

## Format

```
## [Version] — YYYY-MM-DD
### Added
### Changed
### Fixed
### Removed
### Notes
```

---

## [0.6.0] — 2026-04-14

### Added

- `plugins/scrapers/geography_builder.py` — **postcode enrichment via data.gov.au**
  - New `_load_datagov_postcodes()` method: downloads Australian Postcodes CSV (18,559 rows)
    from data.gov.au (official dataset, GitHub mirror used for programmatic access)
  - New `_enrich_postcodes_from_datagov()`: joins suburb_name + state → postcode with
    parenthetical stripping ("Paddington (Qld)" → "PADDINGTON" for matching)
  - Logs 704 multi-postcode suburbs to `data/raw/abs/multi_postcode_suburbs.json`
  - Postcodes zero-padded to 4 digits (e.g. ACT 200 → "0200")
- `plugins/scrapers/supabase_loader.py` — **new bulk upsert script**
  - Reads geography_trinity.json, bulk-upserts 8,639 suburbs into Supabase `suburbs` table
  - Idempotent: upsert on conflict `(suburb_name, state)`
  - Runs in batches of 500 to stay within PostgREST limits
  - `--dry-run` flag for preview without writing
- `data/raw/abs/australian_postcodes.csv` — auto-downloaded by geography_builder (gitignored)
- `data/raw/abs/multi_postcode_suburbs.json` — 704 multi-postcode audit log (gitignored)
- `data/raw/domain_signals.json` — Domain scrape results keyed by slug (gitignored)
- `data/raw/sqm_signals.json` — SQM vacancy + stock signals keyed by postcode (gitignored)
- `python-dotenv>=1.0,<2.0` added to requirements.txt

### Changed

- `plugins/scrapers/geography_builder.py`
  - `run()` now accepts `enrich_postcodes=True` parameter
  - `_domain_slug()` now strips ABS disambiguation parens before slugifying:
    `"Paddington (Qld)" + "QLD" + "4064"` → `"paddington-qld-4064"` (was `"paddington-qld-qld-4064"`)
  - Updated docstring with postcode fallback strategy documentation
- `plugins/scrapers/base_scraper.py`
  - `log_run()` updated: dual-write to Supabase `scrape_log` table (primary) and file (always)
  - Supabase failures are caught, logged as warnings, and never raise exceptions
  - Added `_get_supabase_client()` helper — returns `None` if credentials unavailable
  - Added `load_dotenv()` call at module level for .env auto-loading
- `plugins/scrapers/domain_next_data.py`
  - `_scrape_batch()` now returns `(results, true_blocks, no_data_count)` as separate values
  - Added `_NO_DATA_SENTINEL` class variable — returned when page loads (200 OK) but has no house data
  - `_extract()` returns `_NO_DATA_SENTINEL` for no-house-data cases (not `None`)
  - Block rate alert now uses `true_blocks` only (WAF 403/429), not no-data results
  - Run log now shows: `scraped, no-house-data, true-blocks, block-rate` separately
- `plugins/scrapers/sqm_scraper.py`
  - `_SQM_LISTINGS_URL` updated: `graph_listings.php` (404) → `/property/total-property-listings`
  - Replaced `_parse_latest_value()` with three targeted methods:
    - `_parse_sqm_data()`: parses `var data = [{...}]` JSON format
    - `_parse_vacancy_rate()`: extracts `vr` field, returns as % (0–100 scale)
    - `_parse_stock_on_market()`: sums `r30 + r60 + r90 + r180 + r180p` age buckets
  - `_fetch_vacancy()` and `_fetch_stock()` updated to use new parsers
- `supabase/migrations/001_create_core_tables.sql`
  - `UNIQUE (state, suburb_name, postcode)` → `UNIQUE (suburb_name, state)`
    (NULL postcode safe — 10 suburbs have no postal address)
  - Fixed `domain_slug` column comment: `"paddington-2021-nsw"` → `"paddington-qld-4064"`

### Fixed

- Domain slug generation broken for ~1,413 suburbs with ABS disambiguation names
  (e.g. "Paddington (Qld)" was producing `paddington-qld-qld-4064` instead of `paddington-qld-4064`)
- SQM scraper returning 0/50 postcodes due to dead `graph_listings.php` URL and wrong
  HTML parser regex (was looking for JS array format; SQM now uses JSON `var data = [...]`)
- Domain block rate false positive: small rural hamlets returning "no house data" (200 OK)
  were being counted as WAF blocks, triggering 34% alert despite 0 true 403/429 responses

### Notes

- 8,629/8,639 suburbs now have postcodes. 10 remaining = national parks and territories
  with no postal addresses (Blue Mountains NP, Moreton Bay, Palmerston City NT, etc.)
  These will never appear on Domain and are data_thin by definition.
- ACT has 0 qualifying Tier 1 suburbs due to LGA growth filter. Investigate separately.
- Supabase migration not yet run — tables don't exist. `supabase_loader.py` and
  `log_run()` Supabase writes will activate automatically once migration is applied.
- First Domain scrape: 33 signals extracted, 0 true blocks (17 no-house-data rural hamlets)
- First SQM scrape: 50/50 postcodes, vacancy 0.00–4.41%, stock 5–1,089

---

## [0.5.0] — 2026-04-13

### Added

- `plugins/scrapers/geography_builder.py` — Geography Trinity builder
  - Joins SAL→LGA (from abs_ingestor cache), SAL→SA2, SAL→POA concordances
  - Outputs `data/raw/geography_trinity.json` — 8,639 suburbs with tiers + slugs
  - M:N resolution: dominant assignment by highest `RATIO_FROM_TO`
  - Manual fallback: checks for `sal_to_poa_manual.csv` and `sal_to_sa2_manual.csv`
- `plugins/scrapers/nsw_valuer_general.py` — NSW Valuer General .DAT bulk parser
  - Parses `RPEDATA.DAT` weekly download; filters to standalone house sales
- `plugins/scrapers/vic_valuer_general.py` — VIC Data.Vic VPSR quarterly CSV parser
  - Filters to residential property type, aggregates by suburb
- `plugins/scrapers/sa_valuer_general.py` — SA Valuer General quarterly Excel parser
  - Handles multi-sheet workbook, normalises suburb names
- `plugins/scrapers/domain_next_data.py` — Domain **NEXT_DATA** scraper
  - curl-cffi Chrome TLS impersonation (bypasses Akamai JA3/JA4 fingerprinting)
  - Extracts from `__APOLLO_STATE__` inside `__NEXT_DATA__`: `LocationProfile:*` (price/volume)
    and `Suburb:*` (statistics)
  - Per-bedroom aggregation: `number_sold` = sum, price signals = dominant bedroom count
  - Rate limiting: randomised 3–8 second delays, 80 requests/day cap
  - Block detection: alerts if >20% of requests return 403/429
  - Live tested: `paddington-qld-4064` → all signals extracted ✓
- `plugins/scrapers/sqm_scraper.py` — SQM Research vacancy + stock scraper
  - curl-cffi, postcode-keyed, national coverage
  - Loads scrape queue from geography_trinity.json ordered by scrape tier
- `plugins/scoring/tier_classifier.py` — scrape tier classifier
  - Bootstrap mode: ABS growth rate → Hot/Warm/Cold (run before first Domain scrape)
  - Reclassify mode: real `daysOnMarket` from Domain → re-tier (run after first scrape)
  - Bootstrap result: Hot=1,240, Warm=2,259, Cold=0 (Domain states: QLD/WA/NT/TAS/ACT)
- `core/schemas/suburb.py` — updated with `sa2_code`, `sal_code`, `scrape_tier`,
  `domain_slug`, `data_thin` fields
- `supabase/migrations/001_create_core_tables.sql` — DDL for `suburbs`, `scrape_log`,
  `api_cost_log` tables with indexes and `updated_at` trigger

### Changed

- `config.yaml` updated to v1.1 scoring model weights, correct plugin list, correct cadences

### Notes

- ABS SAL→POA and SAL→SA2 concordance ZIPs all return 404 — postcodes left blank pending
  alternative source (resolved Session 6 with data.gov.au CSV)
- Domain URL format confirmed: `{suburb}-{state}-{postcode}` e.g. `paddington-qld-4064`
- Domain uses Apollo GraphQL `__APOLLO_STATE__` — NOT top-level `suburbData` in pageProps
- SA2 enrichment deferred — no scored signal requires SA2 directly

---

## [0.4.0] — 2026-04-12

### Added

- `curl-cffi>=0.6,<1.0` added to requirements.txt
- Domain scraping strategy locked: curl-cffi TLS impersonation for QLD/WA/NT/TAS/ACT
- Data source map finalised by state (see DECISIONS.md Session 4)
- Scrape Tier System defined (Hot/Warm/Cold with bootstrap + reclassify modes)
- Scoring Model v1.1 defined: added Sales Volume Momentum at 10%, reduced Relative Median to 5%

### Changed

- Camoufox removed — confirmed unstable/experimental in 2026 (year-long maintenance gap)
- ScrapeGraphAI retained for infrastructure pipeline only (not for Domain/SQM)
- `config.yaml` updated with v1.1 scoring weights

### Decisions

- Domain URL slug format confirmed: `{suburb}-{state}-{postcode}` (e.g. `paddington-qld-4064`)
- Price filter: suburb standalone house median ≤ $800,000
- Minimum sales volume: 12 house sales/year → below = `data_thin`, excluded from scoring
- NSW/VIC/SA use Valuer General bulk data (more reliable, no scraping risk)
- QLD/WA/NT/TAS/ACT use Domain `__NEXT_DATA__` scraping

---

## [0.3.0] — 2026-04-11

### Added

- Python venv (`.venv`, Python 3.11.8) + `requirements.txt`
  - pydantic 2.12.5, pandas 2.3.3, openpyxl, requests, pyyaml, supabase 2.28.3
- `core/__init__.py`, `core/schemas/__init__.py` — package structure
- `core/schemas/suburb.py` — Suburb Pydantic model (Growth Funnel tiering flag)
- `core/schemas/signals.py` — DataSignal Pydantic model
- `core/schemas/scorecard.py` — SuburbScorecard Pydantic model
- `plugins/__init__.py`, `plugins/scrapers/__init__.py`
- `plugins/scrapers/base_scraper.py` — abstract base class; `log_run()` writes to file
- `plugins/scrapers/abs_ingestor.py` — Growth Funnel cold filter
  - Parses ABS Regional Population Excel datacube (multi-sheet, 2024–25)
  - Filters LGAs: population > 20,000 AND annual growth > 0.5%
  - Maps suburbs using ASGS SAL→LGA concordance (ABS renamed SSC→SAL in 2021 edition)
  - Outputs `data/raw/tier1_candidates.json` — 8,639 Tier 1 suburbs across 193 LGAs
- `config.yaml` — `data_filters` block with `lga_min_population` and `lga_min_growth_pct`
- `data/raw/tier1_candidates.json` — 8,639 Tier 1 suburb candidates (gitignored)

### Changed

- `config.yaml`: `lga_min_growth_pct` set to `0.5` (down from `1.5` — 83 LGAs too restrictive)

### Fixed

- `core/schemas/suburb.py`: corrected import `from .signal` → `from .signals`
- `abs_ingestor.py`: LGA code type mismatch — ERP cache returns int codes, SAL concordance
  uses strings; both now stringified before comparison

### Notes

- ABS Data API (`api.data.abs.gov.au`) blocked from this machine — falls back to manual Excel
- Growth Funnel result: 193 qualifying LGAs → 8,639 suburbs
  - NSW 2816 · QLD 2621 · VIC 1706 · WA 697 · SA 618 · NT 117 · TAS 64

---

## [0.2.1] — 2026-04-11

### Added

- Remote GitHub repository linked
- Multi-branch strategy initialized (`main`, `dev`)
- Successful first push to origin

---

## [0.2.0] — 2026-04-11

### Added

- Orchestration pivoted from n8n to Windmill (workflow-as-code, typed Python, Pydantic)
- Tiered scraping funnel defined (Tier 1 filter → Hot/Warm/Cold cadence)
- Pydantic schema layer planned for data validation
- Camoufox evaluated for anti-bot scraping (later removed in Session 4)

---

## [0.1.0] — 2026-04-11

### Added

- Project scaffolded — full folder structure created
- `agents.md` — AI tool behaviour rules
- `PROJECT.md` — local project index (gitignored)
- `ARCHITECTURE.md` — full technical architecture locked
- `README.md` — public GitHub intro
- `TODO.md` — session state tracking
- `DECISIONS.md` — architecture decisions + rationale
- `CONTEXT.md` — investor profile + scoring weights
- `HEARTBEAT.md` — Hermes monitoring checklist
- `CHANGELOG.md` — this file

### Notes

- Session 1 complete — whiteboard + architecture locked, scaffold in progress
- No code written yet — foundation files only

---

_Versions follow semantic versioning — major.minor.patch_
_Major: breaking architecture change | Minor: new feature or plugin | Patch: bug fix or doc update_
