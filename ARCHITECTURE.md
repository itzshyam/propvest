> **Source of truth for all AI tools (Hermes, Claude Code, Cowork) and contributors.**
> Read this before touching any code.

---

## Project Overview

Propvest is a personal → shareable → productisable property research assistant for Australian suburb capital growth analysis. Aggregates fragmented data sources, scores suburbs deterministically, and provides conversational LLM-powered research via a dashboard interface.

**Core problem solved:** Free-tier property data is fragmented across Domain, SQM Research, ABS, and state government sources. Propvest aggregates, scores, and makes it conversationally queryable without paywalled services.

---

## The Four Absolutes

Every decision is evaluated against these in order. No exceptions.

| Priority | Absolute          | What it means                                                 |
| -------- | ----------------- | ------------------------------------------------------------- |
| 1        | **Cost friendly** | Minimise infrastructure and API spend at every layer          |
| 2        | **Reliable**      | Minimal hallucination, no data invention, deterministic first |
| 3        | **Scalable**      | Plugin architecture, clean interfaces, workflow-as-code       |
| 4        | **Low latency**   | Cache aggressively, async scraping, LLM is last resort        |

---

## Investor Profile

- **Strategy:** Buy and hold — capital growth focus
- **Geography:** All of Australia (~15,000 suburbs)
- **Asset class:** Standalone residential houses only (no units, no townhouses)
- **Price ceiling:** $800,000 suburb median (standalone house)
- **Horizon:** Long term (7-10+ years)
- **Risk appetite:** Moderate — growth focused, not speculative

---

## Data Ingestion Strategy: The Growth Funnel

```
ABS Bulk CSV (all ~15,000 suburbs)
        ↓
Cold Filter (abs_ingestor.py)
LGA population > 20k AND growth > 0.5%
        ↓
8,639 Tier 1 Suburbs (tier1_candidates.json)
        ↓
Property Filter (post first scrape)
Standalone house median ≤ $800k
        ↓
Minimum Volume Filter
≥ 12 house sales trailing 12 months
Otherwise → data_thin flag, excluded from scoring
        ↓
Active Scored Universe
~350-550 suburbs (QLD/WA/NT/TAS/ACT estimate)
+ NSW/VIC/SA from Valuer General bulk
```

---

## Data Source Map (by State)

| State    | Signal Source         | Method                  | Cadence   |
| -------- | --------------------- | ----------------------- | --------- |
| NSW      | NSW Valuer General    | Bulk .DAT download      | Weekly    |
| VIC      | Data.Vic VPSR         | Quarterly CSV           | Quarterly |
| SA       | SA Valuer General     | Quarterly Excel         | Quarterly |
| QLD      | Domain suburb profile | curl-cffi **NEXT_DATA** | Tiered    |
| WA       | Domain suburb profile | curl-cffi **NEXT_DATA** | Tiered    |
| TAS      | Domain suburb profile | curl-cffi **NEXT_DATA** | Tiered    |
| NT       | Domain suburb profile | curl-cffi **NEXT_DATA** | Tiered    |
| ACT      | Domain suburb profile | curl-cffi **NEXT_DATA** | Tiered    |
| National | SQM Research          | curl-cffi               | Weekly    |

**Domain scraping covers:** median price, sales volume, days on market, auction clearance rate, owner/renter ratio
**Valuer General covers:** house sales volume + median price (more reliable, no scraping risk)
**SQM covers:** vacancy rate + stock on market (national)

---

## Scrape Tier System (QLD/WA/NT/TAS/ACT)

Suburbs are classified into scrape tiers based on turnover velocity:

| Tier | Signal        | DOM        | Frequency | Bootstrap (ABS growth) |
| ---- | ------------- | ---------- | --------- | ---------------------- |
| Hot  | High turnover | <30 days   | Weekly    | >2%                    |
| Warm | Moderate      | 30-60 days | Monthly   | 0.5-2%                 |
| Cold | Slow moving   | >60 days   | Quarterly | <0.5%                  |

**Bootstrap:** ABS growth rate from tier1_candidates.json used for initial classification.
**Reclassification:** After first scrape pass, actual DOM from Domain replaces ABS growth as classifier.

**Current tier counts (post Session 6 first scrape):** Hot=1,238 / Warm=2,261 / Cold=0

---

## Data Signals (Scoring Model v1.1)

All scoring is **deterministic math** — LLM never computes scores. Missing signals trigger **Dynamic Re-weighting** (scaling remaining signals to 100%).

| Signal                  | Weight | Source                   | Notes                          |
| ----------------------- | ------ | ------------------------ | ------------------------------ |
| Vacancy rate            | 25%    | SQM Research             | Low = rental demand strong     |
| Stock on market         | 20%    | SQM Research             | Low = supply constrained       |
| Population growth       | 20%    | ABS bulk CSV             | vs state average               |
| Infrastructure pipeline | 20%    | State gov portals + news | LLM parses, confidence flagged |
| Sales volume momentum   | 10%    | Valuer General / Domain  | Q-on-Q house sales trend       |
| Relative median gap     | 5%     | Domain **NEXT_DATA**     | vs neighbouring suburbs        |

**Context layer (display only, not scored):**

- Days on market trend
- Auction clearance rate
- Owner-occupier / renter ratio
- Income-to-median affordability ratio (ABS Census — stale, display only)
- Population count

**Red flag alerts (threshold triggers, not scored):**

- Owner-occupier ratio < 70%
- Renter concentration > 50%
- numberSold < 12 → data_thin flag

---

## Domain **NEXT_DATA** — Fields Extracted

Per suburb scrape, extract from `propertyCategories` filtered to `propertyCategory: "House"`:

```json
{
  "medianSoldPrice": 650000,
  "numberSold": 34,
  "daysOnMarket": 28,
  "auctionClearanceRate": 0.72,
  "salesGrowthList": [
    { "year": 2022, "numberSold": 28, "medianSoldPrice": 580000 },
    { "year": 2023, "numberSold": 31, "medianSoldPrice": 610000 },
    { "year": 2024, "numberSold": 34, "medianSoldPrice": 650000 }
  ]
}
```

From `statistics`:

```json
{
  "ownerOccupierPercentage": 0.68,
  "renterPercentage": 0.32,
  "population": 8400
}
```

Everything else ignored.

---

## Scraping — curl-cffi

**Why curl-cffi for Domain:**
Akamai (Domain's WAF) uses JA3/JA4 TLS fingerprinting as its primary detection vector in 2026. Standard Python requests expose a non-browser TLS signature and are blocked immediately. curl-cffi impersonates real Chrome browser TLS handshakes at the library level — free, lightweight, no full browser required.

**Rate limiting:**

- 50-80 requests/day to Domain
- Randomised 3-8 second delays between requests
- Not bulletproof — monitor block rate, alert if >20% **true WAF blocks** (403/429)
- Note: "no house data" responses (200 OK, empty suburb) are NOT blocks — rural hamlets
  with zero house sales are expected and do not count toward the block rate threshold

**SQM URL format (as of Session 6, April 2026):**

- Vacancy: `https://sqmresearch.com.au/graph_vacancy.php?postcode={pc}&t=1`
  Data: `var data = [{year, month, listings, properties, vr}, ...]` — parse `vr` field × 100
- Listings: `https://sqmresearch.com.au/property/total-property-listings?postcode={pc}&t=1`
  Data: `var data = [{year, month, r30, r60, r90, r180, r180p}, ...]` — sum all buckets
  ⚠️ `graph_listings.php` is 404 as of April 2026

**Why NOT Camoufox:**
Camoufox had a year-long maintenance gap and is confirmed experimental/unstable as of 2026. Not suitable for production use.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      HERMES AGENT (Brain)                        │
│   Self-learning · Skill generation · Persistent memory           │
│   Profiles: Coordinator · Researcher · Auditor                   │
└──────────────┬──────────────────────┬───────────────────────────┘
               │                      │
    ┌──────────▼──────────┐  ┌────────▼────────────────┐
    │     curl-cffi       │  │     SCRAPEGRAPHAI        │
    │  Domain __NEXT_DATA__  │  │  Infra pipeline:      │
    │  SQM Research       │  │  Gov portals, PDFs       │
    │  TLS impersonation  │  │  Natural lang prompts    │
    └──────────┬──────────┘  └────────┬────────────────┘
               │                      │
    ┌──────────▼──────────┐
    │  Valuer General     │
    │  NSW/VIC/SA bulk    │
    │  Direct ingest      │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────────────────────────────────────┐
    │                      WINDMILL                        │
    │      Orchestration · Workflow-as-code · Alerting     │
    │      Pydantic Validation · Typed Python scripts      │
    │      Manages Tier 1 Sync + On-Demand Queue           │
    │      Scrape tier scheduling (Hot/Warm/Cold)          │
    └──────────────────────┬───────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────┐
    │                 SUPABASE (Postgres)       │
    │   suburbs · signals · scrape_queue        │
    │   scrape_log · api_cost_log               │
    └──────────────────────┬────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────────┐
    │              TOKEN EFFICIENCY GATE                   │
    │   Deterministic? → answer directly, skip LLM        │
    │   Genuine reasoning needed? → pass to LLM           │
    └──────────┬──────────────────────────────────────────┘
               │
    ┌──────────▼──────────────────────────────────────────┐
    │                   CLAUDE API                         │
    │   Auditor Profile for Top 10% Deep Dives            │
    │   MCP tools: get_suburb · compare · get_trend       │
    └──────────┬──────────────────────────────────────────┘
               │
    ┌──────────▼───────────────┐      ┌──────────────────────────┐
    │     FASTAPI BACKEND      │      │     NEXT.JS FRONTEND     │
    │   Chat + Explorer APIs   │ ◄──► │   Dashboard + Chat UI    │
    └──────────────────────────┘      └──────────────────────────┘
```

---

## Plugin Architecture

**Three laws:**

1. Every plugin implements a base interface
2. Plugins communicate via event bus — never direct imports
3. Feature flags in config.yaml — disable without deleting code

```
/Propvest
  /core
    __init__.py
    /schemas
      __init__.py
      suburb.py           ✓ BUILT (updated Session 5: sa2_code, sal_code, scrape_tier, domain_slug, data_thin)
      signals.py          ✓ BUILT
      scorecard.py        ✓ BUILT
  config.yaml             ✓ UPDATED (v1.1 scoring, correct plugin list + cadences)
  /plugins
    __init__.py
    /scrapers
      __init__.py
      base_scraper.py         ✓ BUILT (Session 6: dual-write log_run → Supabase + file)
      abs_ingestor.py         ✓ BUILT — 8,639 Tier 1 suburbs
      geography_builder.py    ✓ BUILT (Session 6: data.gov.au postcode enrichment, fixed slug)
      supabase_loader.py      ✓ BUILT (Session 6: bulk upsert 8,639 suburbs → Supabase)
      nsw_valuer_general.py   ✓ BUILT — NSW .DAT bulk parser (awaiting data files)
      vic_valuer_general.py   ✓ BUILT — VIC Data.Vic CSV parser (awaiting data files)
      sa_valuer_general.py    ✓ BUILT — SA VG Excel parser (awaiting data files)
      domain_next_data.py     ✓ BUILT (Session 6: block detection fixed, first run complete)
      sqm_scraper.py          ✓ BUILT (Session 6: URL + parser fixed, first run complete)
    /scoring
      __init__.py
      tier_classifier.py      ✓ BUILT — bootstrap + DOM reclassify (Session 6: first reclassify run)
      deterministic.py        ← TODO Session 7
      llm_explainer.py        ← TODO (explain only, never compute)
    /signals
      vacancy_rate.py         ← TODO Phase 1 backlog
      stock_on_market.py      ← TODO Phase 1 backlog
      population_growth.py    ← TODO Phase 1 backlog
      infrastructure.py       ← TODO Phase 1 backlog
      sales_volume.py         ← TODO Phase 1 backlog
      relative_median.py      ← TODO Phase 1 backlog
  /data
    /raw
      /abs
      /domain
      tier1_candidates.json       ✓ EXISTS (gitignored)
      geography_trinity.json      ✓ EXISTS (gitignored) — 8,639 suburbs, postcodes + tiers + slugs
      domain_signals.json         ✓ EXISTS (gitignored) — 33 QLD signals (Session 6 first run)
      sqm_signals.json            ✓ EXISTS (gitignored) — 50 postcode signals (Session 6 first run)
      scrape_log.json             ✓ EXISTS (gitignored)
  /supabase
    /migrations
      001_create_core_tables.sql  ✓ BUILT (updated Session 6: UNIQUE constraint fix)
                                  ⚠️ NOT YET RUN — tables don't exist in Supabase
  /workflows                  ← TODO Session 7: Windmill definitions
  /skills                     ← Hermes SKILL.md files
  /api                        ← TODO Phase 2
  /frontend                   ← TODO Phase 2
```

---

## Postcode Enrichment (Session 6)

ABS SAL→POA concordance ZIPs all return 404. Postcode enrichment uses **data.gov.au Australian Postcodes CSV** as fallback:

- Source: `https://data.gov.au/data/dataset/Australian-postcodes`
  (programmatic download via GitHub mirror: matthewproctor/australianpostcodes)
- Match: `suburb_name_upper + state` → `postcode` (4-digit, zero-padded)
- Parenthetical disambiguation stripped: "Paddington (Qld)" → "PADDINGTON" for matching
- 704 suburbs map to multiple postcodes — dominant (lowest/first) chosen; all logged
- Result: 8,629/8,639 suburbs with postcodes (99.9%)
- 10 missing: national parks + territories with no postal addresses

---

## Supabase Setup (Session 6 — PENDING)

Migration SQL written but **not yet run**. Tables don't exist.

```
MANUAL ACTION REQUIRED:
1. Go to Supabase SQL Editor (https://nqnvijfqnxfuwoygfnhs.supabase.co)
2. Run: supabase/migrations/001_create_core_tables.sql
3. Then run: python -m plugins.scrapers.supabase_loader
   Expected: 8,639 rows inserted, 0 errors
```

Once run:

- `base_scraper.log_run()` will automatically write to `scrape_log` table (fallback to file always active)
- `supabase_loader.py` will populate `suburbs` table

---

## Token Efficiency Rules

- SQL/deterministic → never LLM
- Gate pattern cuts 60-70% of potential LLM calls
- Token budgets: scoring_summary=300, deep_dive=800, chat_response=500, infra_parse=600

---

## Infrastructure & Cost

| Layer         | Tool                       | Est. Cost     |
| ------------- | -------------------------- | ------------- |
| Database      | Supabase                   | Free / $25    |
| Orchestration | Windmill (self-hosted)     | Free          |
| Scraping      | curl-cffi + Valuer General | Free          |
| Backend       | FastAPI (Railway)          | ~$5/mo        |
| LLM           | Claude API                 | <$10/mo       |
| **Total**     |                            | **~$5-15/mo** |

---

_Last updated: Session 6_
_Next: Session 7 — Supabase migration (manual) → continue Domain scraping → deterministic scoring engine_
