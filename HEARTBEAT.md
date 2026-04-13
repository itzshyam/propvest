# Propvest — Heartbeat Checklist

> Hermes reads this every 30 minutes and acts on any item that requires attention.
> Update this file when new monitoring tasks are needed.

---

## Frequency

| Task type              | Cadence      |
| ---------------------- | ------------ |
| Scrape health check    | Every 30 min |
| Score drift alert      | Every 30 min |
| Knowledge drop watcher | Every 30 min |
| Site structure check   | Daily        |
| Eval set validation    | Weekly       |

---

## Every 30 Minutes

- [ ] Check `scrape_log` for any failures in the last 24hrs
  - If failure found → alert via Telegram/Discord + log to `/logs/errors.md`
  - If same source fails 3x consecutively → disable plugin via `config.yaml` flag, alert user
- [ ] Check if any suburb score has shifted >10 points since last run
  - If yes → alert user with suburb name, old score, new score, and which signal changed
- [ ] Check `/knowledge-drop` for any unprocessed files
  - If new file found → convert to Markdown → chunk → index into LlamaIndex → mark as processed
- [ ] Check Domain scraper block rate
  - If >20% of Domain requests return non-200 or empty **NEXT_DATA** → alert user immediately
  - Do not auto-retry more than 2x — reduces Akamai detection risk

---

## Daily

- [ ] Check Domain and SQM for structure changes
  - Domain: verify `__NEXT_DATA__` JSON still contains `propertyCategories` and `statistics` keys
  - SQM: verify scraper returns expected vacancy + stock fields
  - If either returns empty or malformed → flag for skill update, disable plugin
- [ ] Check `api_cost_log` — alert if daily Claude API spend exceeds $1.00
- [ ] Verify Redis cache is healthy and TTLs are set correctly
- [ ] Check curl-cffi Domain scraper ran within expected request window (50-80/day)
  - If over 80 requests in a day → alert, review rate limiting config

---

## Weekly

- [ ] Run 30-suburb eval set against current scoring model (v1.1)
  - Compare output against manually scored benchmarks in `/evals`
  - If any suburb diverges by >15 points → alert user, do not auto-adjust weights
- [ ] Check `DECISIONS.md` scoring weights history matches `config.yaml` current weights
- [ ] Check `TODO.md` — alert if it hasn't been updated in >7 days
- [ ] Summarise week's scrape success rate, token spend, and score changes into weekly digest
- [ ] Check data_thin suburbs — any that now have ≥12 sales should be reclassified and scored
- [ ] Review scrape tier classifications — any Hot/Warm/Cold reclassifications needed based on new DOM data

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

| Skill                      | Trigger for improvement                            |
| -------------------------- | -------------------------------------------------- |
| `scrape_domain.md`         | Block rate >20% or **NEXT_DATA** structure changes |
| `scrape_sqm.md`            | Scrape returns <50% expected rows                  |
| `scrape_valuer_general.md` | Parse returns unexpected format                    |
| `parse_infra_pipeline.md`  | LLM extraction confidence <70%                     |
| `score_suburb.md`          | Eval set divergence >15 points                     |
| `tier_classifier.md`       | >30% of suburbs reclassified after first DOM data  |

---

## Known Data File Locations (as of Session 5)

| File                              | Purpose                                        | Regenerate with                                                                        |
| --------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------- |
| `data/raw/abs/erp_lga.csv`        | Cached ABS ERP parse (546 LGAs)                | Delete + re-run abs_ingestor.py                                                        |
| `data/raw/abs/ssc_to_lga.csv`     | Cached SAL→LGA concordance (16,630 rows)       | Delete + re-run abs_ingestor.py                                                        |
| `data/raw/tier1_candidates.json`  | 8,639 Tier 1 suburbs with ABS growth rates     | `python -m plugins.scrapers.abs_ingestor`                                              |
| `data/raw/geography_trinity.json` | 8,639 suburbs with scrape tiers + domain slugs | `python -m plugins.scrapers.geography_builder` then `tier_classifier --mode bootstrap` |
| `data/raw/scrape_log.json`        | Run log (all scraper runs)                     | Append-only, do not delete                                                             |

Manual source files (not regeneratable automatically):

| File                                 | Source                                    |
| ------------------------------------ | ----------------------------------------- |
| `data/raw/abs/erp_lga_manual.xlsx`   | ABS Regional Population 2024-25 datacube  |
| `data/raw/abs/sal_to_lga_manual.csv` | ABS ASGS SAL→LGA concordance 2021 edition |

---

_Last updated: Session 5_
_Hermes workspace: C:\Users\itzsh\Documents\Projects\Propvest_
