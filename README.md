# Propvest

> Australian suburb capital growth analyser — free, open, conversational.

Propvest aggregates fragmented Australian property data (Domain, SQM Research, ABS, state Valuer General) into a scored, rankable, conversationally queryable research assistant. No CoreLogic subscription. No manual suburb-by-suburb searching.

---

## What It Does

- **Scores** Australian suburbs for standalone house capital growth potential using deterministic weighted signals
- **Ranks and filters** suburbs across all of Australia by your criteria
- **Deep-dives** on any suburb — vacancy rates, stock on market, population trends, infrastructure pipeline, sales momentum
- **Answers questions** conversationally via an LLM grounded in real scraped data
- **Alerts** you when a suburb's score shifts significantly

---

## Scope

- **Asset class:** Standalone residential houses only (no units, no townhouses)
- **Price ceiling:** $800,000 suburb median
- **Minimum liquidity:** 12+ house sales per year (below = excluded as data-thin)
- **Strategy:** Buy and hold, capital growth, 7-10+ year horizon

---

## Signals (Scoring Model v1.1)

| Signal                  | Weight | Source                   |
| ----------------------- | ------ | ------------------------ |
| Vacancy rate            | 25%    | SQM Research             |
| Stock on market         | 20%    | SQM Research             |
| Population growth       | 20%    | ABS bulk CSV             |
| Infrastructure pipeline | 20%    | State gov portals + news |
| Sales volume momentum   | 10%    | Valuer General / Domain  |
| Relative median gap     | 5%     | Domain suburb profiles   |

Scoring is fully deterministic — the LLM explains scores, never computes them.

---

## Data Sources

| State             | Source                 | Method            |
| ----------------- | ---------------------- | ----------------- |
| NSW               | NSW Valuer General     | Bulk download     |
| VIC               | Data.Vic VPSR          | Quarterly CSV     |
| SA                | SA Valuer General      | Quarterly Excel   |
| QLD/WA/NT/TAS/ACT | Domain suburb profiles | curl-cffi scraper |
| National          | SQM Research           | curl-cffi scraper |

---

## Tech Stack

| Layer         | Tool                          |
| ------------- | ----------------------------- |
| Agent runtime | Hermes (Nous Research)        |
| Scraping      | curl-cffi (TLS impersonation) |
| Infra parsing | ScrapeGraphAI                 |
| Orchestration | Windmill                      |
| Database      | Supabase (Postgres)           |
| RAG           | LlamaIndex                    |
| LLM           | Claude API                    |
| Backend       | FastAPI                       |
| Frontend      | Next.js                       |

**Estimated cost: ~$5-15/mo**

---

## Project Status

Currently in **Phase 1 — Foundation (Session 8 complete).**

| Component                      | Status                                                                     |
| ------------------------------ | -------------------------------------------------------------------------- |
| ABS Growth Funnel ingestor     | ✓ Complete — 8,639 Tier 1 suburbs                                          |
| Geography Trinity builder      | ✓ Complete — postcodes + slugs populated (8,254 unique)                    |
| Scrape tier classifier         | ✓ Complete — Hot=1,290 / Warm=2,189 / Cold=20                              |
| Domain scraper (QLD/WA/NT/TAS) | ✓ Running — 282 suburbs, batch 1+2 complete; --offset batching added       |
| SQM scraper (national)         | ✓ Running — QLD/WA/NT/TAS all scraped; --state filter added                |
| NSW/VIC/SA Valuer General      | ✓ Built — awaiting data file downloads                                     |
| Supabase suburbs table         | ✓ Loaded — 8,254 rows (migration 001 run)                                  |
| Supabase signals table         | ✓ Loaded — 13,353 rows, 0 errors (migration 002 run)                       |
| Deterministic scoring engine   | ✓ Running — v1.1, 197 suburbs scored; data_thin exclusion + --include-thin |
| Signals loader                 | ✓ Running — 13,353 rows, 0 errors; intra-batch dedup fix applied           |
| Windmill workflow definitions  | ← TODO Phase 1 backlog                                                     |
| FastAPI backend                | ← TODO Phase 2                                                             |
| Next.js frontend               | ← TODO Phase 2                                                             |

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full technical design and [TODO.md](./TODO.md) for current session state.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Supabase project (free tier) with credentials in `.env`

### Setup

```bash
git clone https://github.com/itzshyam/propvest.git
cd propvest
cp .env.example .env
# Add SUPABASE_URL and SUPABASE_ANON_KEY to .env
pip install -r requirements.txt
```

### Run the data pipeline

```bash
# Step 1: ABS Growth Funnel — generates tier1_candidates.json (8,639 suburbs)
python -m plugins.scrapers.abs_ingestor

# Step 2: Geography Trinity — generates geography_trinity.json with postcodes + slugs
python -m plugins.scrapers.geography_builder

# Step 3: Bootstrap scrape tiers from ABS growth rates
python -m plugins.scoring.tier_classifier --mode bootstrap

# Step 4: Run Supabase migration 001 (manual — paste SQL into Supabase SQL Editor)
# File: supabase/migrations/001_create_core_tables.sql

# Step 5: Bulk upsert suburbs into Supabase
python -m plugins.scrapers.supabase_loader

# Step 6: Scrape Domain signals (QLD, 75 suburbs per run)
python -m plugins.scrapers.domain_next_data --state QLD --batch 75

# Step 7: Reclassify tiers from real DOM data
python -m plugins.scoring.tier_classifier --mode reclassify

# Step 8: Scrape SQM vacancy + stock signals
python -m plugins.scrapers.sqm_scraper --batch 75

# Step 9: Run Supabase migration 002 (manual — paste SQL into Supabase SQL Editor)
# File: supabase/migrations/002_add_signals_and_scores.sql

# Step 10: Load all signals into Supabase
python -m plugins.scrapers.signals_loader

# Step 11: Score all suburbs and write to Supabase
python -m plugins.scoring.deterministic --score-all --write-supabase
```

### Required manual data files

These files must be downloaded manually and placed before running `abs_ingestor.py`:

| File                                 | Source                                                                                                                                                                                                           |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `data/raw/abs/erp_lga_manual.xlsx`   | [ABS Regional Population 2024-25](https://www.abs.gov.au/statistics/people/population/regional-population/latest-release)                                                                                        |
| `data/raw/abs/sal_to_lga_manual.csv` | [ABS ASGS Correspondences](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/correspondences) — find SAL→LGA concordance |

---

## Disclaimer

This tool scrapes publicly available data for personal research use. Always verify data independently before making investment decisions. Not financial advice.
