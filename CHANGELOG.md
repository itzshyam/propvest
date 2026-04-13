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
- GitHub repo not yet created
- Hermes not yet pointed at workspace

---

## [0.2.0] — 2026-04-11

### Added

- Pivoted Orchestration from n8n to Windmill.
- Defined Tiered Scraping Funnel (Tier 1 vs Tier 2).
- Added Pydantic Schema layer for data digestibility.
- Integrated Camofox for enhanced anti-bot scraping.

## [0.2.1] — 2026-04-11

### Added

- Remote GitHub repository linked.
- Multi-branch strategy initialized (`main`, `dev`).
- Successful first push to origin.

---

## [0.3.0] — 2026-04-11

### Added

- Python venv (`.venv`, Python 3.11.8) + `requirements.txt`
  - pydantic 2.12.5, pandas 2.3.3, openpyxl, requests, pyyaml, supabase 2.28.3
- `core/__init__.py`, `core/schemas/__init__.py` — package structure
- `core/schemas/suburb.py` — Suburb Pydantic model (includes Growth Funnel tiering flag)
- `core/schemas/signals.py` — DataSignal Pydantic model
- `core/schemas/scorecard.py` — SuburbScorecard Pydantic model
- `plugins/__init__.py`, `plugins/scrapers/__init__.py`
- `plugins/scrapers/base_scraper.py` — abstract base class; `log_run()` writes to `data/raw/scrape_log.json` (Supabase-ready stub)
- `plugins/scrapers/abs_ingestor.py` — Growth Funnel cold filter
  - Parses ABS Regional Population Excel datacube (multi-sheet, 2024–25)
  - Filters LGAs: population > 20,000 AND annual growth > 0.5%
  - Maps suburbs using ASGS SAL→LGA concordance (ABS renamed SSC→SAL in 2021 edition)
  - Outputs `data/raw/tier1_candidates.json` — 8,639 Tier 1 suburbs across 193 LGAs
  - Handles: Excel datacube → API fallback → manual file fallback → clear error with download instructions
- `config.yaml` — added `data_filters` block with `lga_min_population` and `lga_min_growth_pct`
- `data/raw/tier1_candidates.json` — 8,639 Tier 1 suburb candidates (gitignored, regeneratable)
- `data/raw/scrape_log.json` — first run logged

### Changed

- `config.yaml`: `lga_min_growth_pct` set to `0.5` (down from initial `1.5` — 83 LGAs was too restrictive)

### Fixed

- `core/schemas/suburb.py`: corrected import `from .signal` → `from .signals`
- `abs_ingestor.py`: LGA code type mismatch — ERP cache returns int codes, SAL concordance uses strings; both now stringified before comparison

### Notes

- ABS Data API (`api.data.abs.gov.au`) is blocked from this machine — ingestor falls back to manually placed Excel file cleanly
- ABS renamed suburb geography from SSC to SAL; ingestor detects both automatically
- Growth Funnel result: 193 qualifying LGAs → 8,639 suburbs
  - NSW 2816 · QLD 2621 · VIC 1706 · WA 697 · SA 618 · NT 117 · TAS 64

_Versions follow semantic versioning — major.minor.patch_
_Major: breaking architecture change_
_Minor: new feature or plugin added_
_Patch: bug fix, config tweak, or doc update_
