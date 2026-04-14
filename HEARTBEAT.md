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
- [ ] Check Domain scraper **true** block rate (WAF blocks only — 403/429 responses)
  - If >20% of Domain requests return 403 or 429 → alert user immediately
  - Do NOT count "no house data" responses (200 OK, empty suburb) as blocks — these are
    legitimate for rural hamlets and small localities with no house sales on Domain
  - Do not auto-retry more than 2x — reduces Akamai detection risk

---

## Daily

- [ ] Check Domain and SQM for structure changes
  - Domain: verify `__NEXT_DATA__` JSON still contains `propertyCategories` and `statistics` keys
    inside `__APOLLO_STATE__` (keys: `LocationProfile:*` and `Suburb:*`)
  - SQM vacancy: verify `var data = [{year,month,listings,properties,vr},...]` still present
  - SQM listings: verify `var data = [{year,month,r30,r60,r90,r180,r180p},...]` still present
    at `/property/total-property-listings?postcode={pc}&t=1`
  - If either returns empty or malformed → flag for skill update, disable plugin
- [ ] Check `api_cost_log` — alert if daily Claude API spend exceeds $1.00
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

| Skill                      | Trigger for improvement                                 |
| -------------------------- | ------------------------------------------------------- |
| `scrape_domain.md`         | True block rate >20% or **NEXT_DATA** structure changes |
| `scrape_sqm.md`            | Scrape returns <50% expected rows or URL/format changes |
| `scrape_valuer_general.md` | Parse returns unexpected format                         |
| `parse_infra_pipeline.md`  | LLM extraction confidence <70%                          |
| `score_suburb.md`          | Eval set divergence >15 points                          |
| `tier_classifier.md`       | >30% of suburbs reclassified after first DOM data       |

---

## Known Data File Locations (as of Session 7)

| File                                       | Purpose                                               | Regenerate with                                                                        |
| ------------------------------------------ | ----------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `data/raw/abs/erp_lga.csv`                 | Cached ABS ERP parse (546 LGAs)                       | Delete + re-run `abs_ingestor.py`                                                      |
| `data/raw/abs/ssc_to_lga.csv`              | Cached SAL→LGA concordance (16,630 rows)              | Delete + re-run `abs_ingestor.py`                                                      |
| `data/raw/abs/australian_postcodes.csv`    | data.gov.au postcode lookup (18,559 rows)             | Auto-downloaded by `geography_builder` if missing                                      |
| `data/raw/abs/multi_postcode_suburbs.json` | 704 suburbs mapped to multiple postcodes              | Re-run `geography_builder`                                                             |
| `data/raw/tier1_candidates.json`           | 8,639 Tier 1 suburbs with ABS growth rates            | `python -m plugins.scrapers.abs_ingestor`                                              |
| `data/raw/geography_trinity.json`          | 8,254 unique suburbs with postcodes + tiers + slugs   | `python -m plugins.scrapers.geography_builder` then `tier_classifier --mode bootstrap` |
| `data/raw/domain_signals.json`             | 171 Domain signals — QLD/WA/NT/TAS (Session 7)        | `python -m plugins.scrapers.domain_next_data --state QLD --batch 75`                   |
| `data/raw/sqm_signals.json`                | 75 QLD postcode signals — vacancy + stock (Session 7) | `python -m plugins.scrapers.sqm_scraper --batch 75`                                    |
| `data/raw/scrape_log.json`                 | Run log (all scraper runs) — append-only              | Do not delete                                                                          |

Manual source files (not regeneratable automatically):

| File                                 | Source                                    |
| ------------------------------------ | ----------------------------------------- |
| `data/raw/abs/erp_lga_manual.xlsx`   | ABS Regional Population 2024-25 datacube  |
| `data/raw/abs/sal_to_lga_manual.csv` | ABS ASGS SAL→LGA concordance 2021 edition |

---

## Known Issues / Gotchas (Session 7)

- **SQM `graph_listings.php` is 404** as of April 2026. Correct URL: `/property/total-property-listings`
- **Domain "block rate" false positive**: small rural hamlets return 200 OK with no house data —
  this is NOT a WAF block. Only count 403/429 responses as true blocks.
- **ACT has 0 qualifying Tier 1 suburbs** — LGA growth filter excludes ACT LGAs. Investigate separately if ACT coverage needed.
- **Migration 002 not yet run** — `signals` table and `suburbs.score` column do not exist. Run
  `supabase/migrations/002_add_signals_and_scores.sql` in Supabase SQL Editor before Session 8.
- **10 suburbs have no postcode** — national parks and territories (Blue Mountains NP, Moreton Bay area, etc.). These will never have Domain data and are data_thin by definition.
- **geography_trinity.json silent failure mode** — if `australian_postcodes.csv` download fails during
  geography_builder, all postcodes come out null and all Domain slugs are malformed → 100% apparent block rate.
  Detection: count non-null postcodes after rebuild; should be ≥ 8,620.
- **True suburb count is 8,254 not 8,639** — SAL→LGA M:N join creates 385 duplicate (suburb_name, state)
  pairs; supabase_loader deduplicates before upsert. The raw geography_trinity.json still has 8,639 rows.
- **SQM signals only cover QLD** — WA/NT/TAS postcodes not yet scraped; those suburbs will have
  vacancy_rate and stock_on_market missing (dynamic re-weighting will fire for them in scorer).

---

_Last updated: Session 7_
_Hermes workspace: C:\Users\itzsh\Documents\Projects\Propvest_
