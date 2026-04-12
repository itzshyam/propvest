# Propvest — TODO

> Session state. Update at the end of every session.
> AI tools: read this after PROJECT.md to understand current state before acting.

---

## Current Status

**Phase:** 1 — Foundation (Session 3 Complete)
**Focus:** ABS ingestor shipped. 8,639 Tier 1 suburbs identified. Windmill next.

## Completed

- [x] Whiteboard session 1 & 2 complete.
- [x] Switched to Windmill for "Digestible Data" rigor.
- [x] Defined 3,000-suburb Growth Funnel strategy.
- [x] Hermes Profile strategy (Coordinator, Researcher, Auditor).
- [x] Create GitHub repo (main and dev branches initialized)
- [x] git init + first commit + remote origin set
- [x] Python venv set up (.venv, Python 3.11.8)
- [x] requirements.txt defined (pydantic, pandas, requests, pyyaml, supabase)
- [x] `/core/schemas`: `suburb.py`, `signals.py`, `scorecard.py` + `__init__.py`
- [x] `plugins/scrapers/base_scraper.py` — abstract base with file-based scrape_log
- [x] `plugins/scrapers/abs_ingestor.py` — Growth Funnel cold filter (Step 1) ✓ COMPLETE
  - Reads ABS ERP Excel datacube (2024-25 data, 546 LGAs)
  - Filters: population > 20k AND growth > 0.5% (from config.yaml) → 193 qualifying LGAs
  - Maps suburbs using ASGS SAL→LGA concordance (new SAL naming, 2021 edition)
  - Output: `data/raw/tier1_candidates.json` — **8,639 Tier 1 suburbs**
  - By state: NSW 2816, QLD 2621, VIC 1706, WA 697, SA 618, NT 117, TAS 64
  - Logs run to `data/raw/scrape_log.json`

## Up Next (Phase 1 — Unblocked)

- [ ] Setup Windmill local workspace.
- [ ] First "Tier 1" scrape test with Crawl4AI + Camofox.
