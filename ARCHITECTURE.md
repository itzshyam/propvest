> **Source of truth for all AI tools (Hermes, Claude Code, Cowork) and contributors.**
> Read this before touching any code.

---

## Project Overview

Propvest is a personal → shareable → productisable property research assistant for Australian suburb capital growth analysis. Aggregates fragmented data sources, scores suburbs deterministically, and provides conversational LLM-powered research via a dashboard interface.

**Core problem solved:** Free-tier property data is fragmented across REA, Domain, SQM Research, ABS, and state government sources. Propvest aggregates, scores, and makes it conversationally queryable without paywalled services.

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

- **Type:** Buy and hold — capital growth focus
- **Geography:** All of Australia (~15,000 suburbs)
- **Use pattern:** Both broad filtering (explore) and suburb deep-dives
- **Sharing:** Personal first, friends/family, eventual product

---

## Data Ingestion Strategy: The Growth Funnel

To respect **Absolute #1** and **Absolute #4**, Propvest uses a tiered ingestion funnel rather than blanket scraping.

1.  **Cold Filter (Deterministic):** Local Python processing of ABS Bulk CSVs. Identifies LGAs with Population > 20k and Growth > 1.5%.
2.  **Tier 1 (Candidates):** ~3,000 suburbs within growth LGAs. These are indexed for high-priority weekly scraping.
3.  **Tier 2 (On-Demand):** Remaining ~12,000 suburbs. Data is fetched only when a user explicitly requests a deep-dive via chat. Requests are queued in `scrape_queue`.

---

## Data Signals (Scoring Model)

All scoring is **deterministic math** — LLM never computes scores. Missing signals trigger **Dynamic Re-weighting** (scaling remaining signals to 100%) to avoid unfair penalties.

| Signal                        | Weight | Source                  | Notes                          |
| ----------------------------- | ------ | ----------------------- | ------------------------------ |
| Vacancy rate                  | 25%    | SQM Research            | Low = rental demand strong     |
| Stock on market               | 20%    | SQM Research            | Low = supply constrained       |
| Population growth             | 20%    | ABS (bulk CSV)          | Filtered via Ingestor          |
| Infrastructure pipeline       | 20%    | State gov portals, news | LLM parses unstructured source |
| Relative median vs neighbours | 15%    | REA / Domain            | Relative value signal          |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      HERMES AGENT (Brain)                        │
│   Self-learning · Skill generation · Persistent memory           │
│   Profiles: Coordinator · Researcher · Auditor                   │
└──────────────┬──────────────────────┬──────────────────────────-┘
               │                      │
    ┌──────────▼──────────┐  ┌────────▼────────────────┐
    │      CRAWL4AI       │  │     SCRAPEGRAPHAI        │
    │  REA, Domain, SQM   │  │  Infra pipeline:         │
    │  Camofox backend    │  │  Gov portals, PDFs       │
    │  LLM-ready Markdown │  │  Natural lang prompts    │
    └──────────┬──────────┘  └────────┬────────────────┘
               │                      │
    ┌──────────▼──────────────────────▼──────────────────┐
    │                      WINDMILL                       │
    │      Orchestration · Workflow-as-code · Alerting    │
    │      Pydantic Validation · Typed Python scripts     │
    │      Manages Tier 1 Sync + On-Demand Queue          │
    └──────────────────────┬──────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────┐
    │                 SUPABASE (Postgres)       │
    │   suburbs · signals · scrape_queue        │
    └──────────────────────┬────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────────┐
    │              TOKEN EFFICIENCY GATE                   │
    │   Pydantic Schema Check? → Ensure "Digestible Data" │
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

**Core rule:** The core only orchestrates. All business logic lives in plugins.

**Three laws:**

1. Every plugin implements a base interface.
2. Plugins communicate via event bus — never direct imports.
3. Feature flags in `config.yaml` — disable without deleting code.

```
/Propvest
  /core
    __init__.py
    /schemas              ← Pydantic models (The "Contract")
      __init__.py         ← exports Suburb, DataSignal, SuburbScorecard
      suburb.py           ✓ BUILT — Suburb model with is_tier_1 flag
      signals.py          ✓ BUILT — DataSignal model
      scorecard.py        ✓ BUILT — SuburbScorecard model
  config.yaml             ← plugin registry + weights + data_filters thresholds
  /plugins
    __init__.py
    /scrapers
      __init__.py
      base_scraper.py     ✓ BUILT — abstract base + log_run() stub
      abs_ingestor.py     ✓ BUILT — Growth Funnel cold filter (8,639 Tier 1 suburbs)
      rea_scraper.py      ← TODO: Playwright anti-bot (approach TBD: playwright-stealth vs Camofox)
      sqm/                ← TODO: SQM vacancy + stock scraper (public pages, no account)
    /scoring
      __init__.py         ✓ BUILT
      deterministic.py    ✓ BUILT — weighted math + dynamic re-weighting (see Scoring Engine below)
  /data
    /raw
      /abs                ← ABS source files (gitignored)
      tier1_candidates.json  ← 8,639 Tier 1 suburbs (gitignored, regeneratable)
      scrape_log.json     ← append-only run log (gitignored)
  /workflows              ← TODO: Windmill script definitions
  /skills                 ← Hermes SKILL.md files
  /api                    ← TODO: FastAPI endpoints (Phase 2)
  /frontend               ← TODO: Next.js (Phase 2)
```

---

## Scoring Engine

**File:** `plugins/scoring/deterministic.py`
**Entry point:** `score_suburb(suburb: Suburb, config: dict | None) -> SuburbScorecard`

### How it works

1. Reads `scoring_weights` and `scoring_bounds` from `config.yaml`
2. Indexes `suburb.signals` by name (O(1) lookup)
3. Normalises each present signal to 0–100 using its configured bounds and direction:
   - `low_is_good` — lower raw value maps to higher score (vacancy rate, stock on market)
   - `high_is_good` — higher raw value maps to higher score (population growth, infra pipeline)
4. **Dynamic re-weighting:** if any signals are absent, the weights of present signals are scaled proportionally so they still sum to 100%. No suburb is penalised for missing data.
5. Returns `SuburbScorecard` with:
   - `overall_score` — weighted sum (0–100)
   - `component_scores` — each signal's weighted contribution to the total
   - `is_incomplete` — `True` if any configured signal was absent

### Normalization bounds (config.yaml `scoring_bounds`)

| Signal              | Range        | Direction    | Notes                               |
| ------------------- | ------------ | ------------ | ----------------------------------- |
| `vacancy_rate`      | 0–5%         | low is good  | SQM Research                        |
| `stock_on_market`   | 0–10%        | low is good  | SQM Research                        |
| `population_growth` | 0–3%         | high is good | ABS bulk data                       |
| `infra_pipeline`    | 0–100        | high is good | Pre-scored by LLM infra parser      |
| `relative_median`   | −30% to +30% | low is good  | REA/Domain (negative = undervalued) |

> Bounds live in `config.yaml`, not in code. Change bounds there. Run 30-suburb eval set after any change.

### Important constraint

`population_growth` is stored directly on `Suburb.pop_growth_rate` from the ABS ingestor. To include it in scoring, the data pipeline **must** emit a `DataSignal(name='population_growth', value=pop_growth_rate)` into `suburb.signals`. The scoring engine only reads signals — it does not read raw Suburb fields.

---

## Token Efficiency & "Digestible Data"

**LLM is the last resort.**

1.  **Pydantic Enforcement:** All data from scrapers must validate against `/core/      schemas` before storage. This guarantees clean, digestible inputs for both the Dashboard and the LLM.
2.  **Pre-filter pattern:** `candidates = sql_filter(pop_growth > 1.5, vacancy < 2)`
    Only the resulting subset is ever sent for LLM summarization.
3.  **Tiered Review:**
    - **Standard:** Deterministic data display.
    - **Premium:** Auditor Profile (LLM) review triggered only for the Top 10% of suburbs.

---

## Infrastructure & Cost (Estimated)

| Layer         | Tool                   | Est. Cost               |
| ------------- | ---------------------- | ----------------------- |
| Database      | Supabase               | Free / $25              |
| Orchestration | Windmill (Self-hosted) | Free                    |
| Scraping      | Crawl4AI + Camofox     | Free (Proxy costs vary) |
| Backend       | FastAPI (Railway)      | ~$5/mo                  |
| LLM           | Claude API             | <$10/mo                 |
| **Total**     |                        | **~$5-15/mo**           |

---

## Session Continuity — agents.md + PROJECT.md

**Decision:** `agents.md` (public) tells all AI tools to read `PROJECT.md` (gitignored) first every session. This preserves memory and identifies the current active focus (Tier 1 vs Tier 2).

---

_Last updated: Session 4 — Deterministic scoring engine complete_
_Next: Phase 1 — Docker Desktop install → Windmill setup → REA + SQM scrapers_

```

```
