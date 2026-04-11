# Propvest

> Australian suburb capital growth analyser — free, open, conversational.

Propvest aggregates fragmented Australian property data (REA, Domain, SQM Research, ABS) into a scored, rankable, conversationally queryable research assistant. No CoreLogic subscription. No manual suburb-by-suburb searching.

---

## What It Does

- **Scores** every Australian suburb for capital growth potential using deterministic weighted signals
- **Ranks and filters** suburbs across all of Australia by your criteria
- **Deep-dives** on any suburb — vacancy rates, stock on market, population trends, infrastructure pipeline
- **Answers questions** conversationally via an LLM grounded in real scraped data
- **Alerts** you when a suburb's score shifts significantly

---

## Signals (Scoring Model)

| Signal | Weight |
|--------|--------|
| Vacancy rate | 25% |
| Stock on market | 20% |
| Population growth | 20% |
| Infrastructure pipeline | 20% |
| Relative median vs neighbours | 15% |

Scoring is fully deterministic — the LLM explains scores, never computes them.

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Agent runtime | Hermes (Nous Research) |
| Scraping | Crawl4AI |
| Infra parsing | ScrapeGraphAI |
| Orchestration | n8n |
| Database | Supabase (Postgres) |
| Cache | Redis |
| RAG | LlamaIndex |
| LLM | Claude API |
| Backend | FastAPI |
| Frontend | Next.js |

**Estimated cost: ~$5–18/mo**

---

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full technical design, plugin structure, token efficiency rules, and phased delivery plan.

---

## Getting Started

> Prerequisites: Python 3.11+, Node.js 18+, Docker (optional)

```bash
# Clone the repo
git clone https://github.com/itzshyam/propvest.git
cd propvest

# Copy environment template
cp .env.example .env
# Fill in your API keys in .env

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && npm install
```

Full setup guide coming in Phase 1 completion.

---

## Project Status

Currently in **Phase 1 — Foundation.**

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full phased delivery plan.

---

## Disclaimer

This tool scrapes publicly available data for personal research use. Always verify data independently before making investment decisions. Not financial advice.