# Propvest — Heartbeat Checklist

> Hermes reads this every 30 minutes and acts on any item that requires attention.
> Update this file when new monitoring tasks are needed.

---

## Frequency

| Task type | Cadence |
|-----------|---------|
| Scrape health check | Every 30 min |
| Score drift alert | Every 30 min |
| Knowledge drop watcher | Every 30 min |
| Site structure check | Daily |
| Eval set validation | Weekly |

---

## Every 30 Minutes

- [ ] Check `scrape_log` for any failures in the last 24hrs
  - If failure found → alert via Telegram/Discord + log to `/logs/errors.md`
  - If same source fails 3x consecutively → disable plugin via `config.yaml` flag, alert user
- [ ] Check if any suburb score has shifted >10 points since last run
  - If yes → alert user with suburb name, old score, new score, and which signal changed
- [ ] Check `/knowledge-drop` for any unprocessed files
  - If new file found → convert to Markdown → chunk → index into LlamaIndex → mark as processed

---

## Daily

- [ ] Check REA and SQM for frontend structure changes
  - If scraper returns empty or malformed data → flag for skill update
- [ ] Check `api_cost_log` — alert if daily Claude API spend exceeds $1.00
- [ ] Verify Redis cache is healthy and TTLs are set correctly

---

## Weekly

- [ ] Run 30-suburb eval set against current scoring model
  - Compare output against manually scored benchmarks in `/evals`
  - If any suburb diverges by >15 points → alert user, do not auto-adjust weights
- [ ] Check `DECISIONS.md` scoring weights history matches `config.yaml` current weights
- [ ] Check `TODO.md` — alert if it hasn't been updated in >7 days
- [ ] Summarise week's scrape success rate, token spend, and score changes into weekly digest

---

## On Any config.yaml Change

- [ ] Verify `ARCHITECTURE.md` still reflects current plugin state
- [ ] Verify `DECISIONS.md` has rationale for the change logged
- [ ] Run affected plugin tests before re-enabling

---

## Alert Channels

```yaml
# Set in .env — never hardcode here
alerts:
  primary: Telegram
  fallback: Discord
```

---

## Skill Files to Monitor

Hermes should self-improve these skills based on outcomes:

| Skill | Trigger for improvement |
|-------|------------------------|
| `scrape_rea.md` | Scrape returns <50% expected rows |
| `scrape_sqm.md` | Scrape returns <50% expected rows |
| `parse_infra_pipeline.md` | LLM extraction confidence <70% |
| `score_suburb.md` | Eval set divergence >15 points |

---

---

## Known Data File Locations (as of Session 3)

These files are gitignored and regeneratable — but Hermes should know they exist:

| File | Purpose | Regenerate with |
|------|---------|-----------------|
| `data/raw/abs/erp_lga.csv` | Cached ABS ERP parse (546 LGAs) | Delete + re-run `abs_ingestor.py` |
| `data/raw/abs/ssc_to_lga.csv` | Cached SAL→LGA concordance (16,630 rows) | Delete + re-run `abs_ingestor.py` |
| `data/raw/tier1_candidates.json` | 8,639 Tier 1 suburbs | `python -m plugins.scrapers.abs_ingestor` |
| `data/raw/scrape_log.json` | Run log (all scraper runs) | Append-only, do not delete |

Manual source files (user downloads — not regeneratable automatically):

| File | Source |
|------|--------|
| `data/raw/abs/erp_lga_manual.xlsx` | ABS Regional Population 2024–25 datacube |
| `data/raw/abs/sal_to_lga_manual.csv` | ABS ASGS SAL→LGA concordance (2021 edition) |

---

*Last updated: Session 3*
*Hermes workspace: C:\Users\itzsh\Documents\Projects\Propvest*