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

## Getting Started

> Prerequisites: Python 3.11+, Node.js 18+

```bash
git clone https://github.com/itzshyam/propvest.git
cd propvest
cp .env.example .env
pip install -r requirements.txt
```

Full setup guide coming in Phase 1 completion.

---

## Project Status

Currently in **Phase 1 — Foundation (Session 5 complete).**

All scrapers built and tested. Geography Trinity generated (8,639 suburbs). Scrape tiers bootstrapped. Postcode enrichment is the only remaining blocker before first live scrape runs.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full technical design and [TODO.md](./TODO.md) for current session state.

---

## Disclaimer

This tool scrapes publicly available data for personal research use. Always verify data independently before making investment decisions. Not financial advice.
