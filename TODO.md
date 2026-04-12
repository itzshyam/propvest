# Propvest — TODO

> Session state. Update at the end of every session.
> AI tools: read this after PROJECT.md to understand current state before acting.

---

## Current Status

**Phase:** 1 — Foundation (Session 4 Complete)
**Focus:** Deterministic scoring engine shipped. Windmill setup pending Docker Desktop install. REA anti-bot approach decision pending Shyam's call on Camofox vs playwright-stealth.

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
- [x] `plugins/scrapers/abs_ingestor.py` — Growth Funnel cold filter ✓ COMPLETE
  - Filters: population > 20k AND growth > 0.5% → 193 qualifying LGAs, 8,639 suburbs
  - Output: `data/raw/tier1_candidates.json`
- [x] `plugins/scoring/deterministic.py` — deterministic scoring engine ✓ COMPLETE
  - Normalises each signal to 0–100 using bounds from `config.yaml`
  - Dynamic re-weighting: absent signals scaled out so present weights always sum to 100%
  - `scoring_bounds` block added to `config.yaml` (all 5 signals configured)
  - `plugins/scoring/__init__.py` added

## Up Next (Phase 1)

- [ ] **[SHYAM]** Install Docker Desktop — required for Windmill self-hosting
- [ ] **[SHYAM]** Confirm REA anti-bot approach: `playwright-stealth` (free, lower reliability) vs Camofox (~$50–150/mo, more robust)
- [ ] Setup Windmill local workspace via Docker Compose (blocked on Docker)
- [ ] Build `plugins/scrapers/rea_scraper.py` (blocked on anti-bot approach decision)
- [ ] Build `plugins/scrapers/sqm/` — public vacancy + stock on market scraper (unblocked)
- [ ] First Tier 1 scrape test end-to-end
