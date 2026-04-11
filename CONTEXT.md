# Propvest — Investor Context & Scoring Weights

> Hermes and Claude read this to personalise research and analysis.
> Update when your investment strategy or scoring priorities change.

---

## Investor Profile

| Attribute | Detail |
|-----------|--------|
| Strategy | Buy and hold — capital growth focus |
| Geography | All of Australia (~15,000 suburbs) |
| Asset class | Residential property |
| Horizon | Long term (7–10+ years) |
| Risk appetite | Moderate — growth focused, not speculative |

---

## What "Good" Looks Like

A high-scoring suburb for this investor has:
- Low and falling vacancy rate (strong rental demand)
- Low stock on market (supply constrained)
- Population growing faster than state average
- Confirmed infrastructure pipeline not yet priced in by market
- Median price below surrounding comparable suburbs (relative value)

---

## What to Avoid

- High vacancy rates (weak rental demand)
- Oversupplied markets (high stock on market)
- Shrinking or flat population
- No infrastructure pipeline or government investment signals
- Overpriced relative to neighbours with no clear catalyst

---

## Scoring Weights (v1.0)

```yaml
scoring_weights:
  vacancy_rate:      0.25   # strongest demand signal
  stock_on_market:   0.20   # supply constraint signal
  population_growth: 0.20   # long term demand driver
  infra_pipeline:    0.20   # forward-looking alpha signal
  relative_median:   0.15   # relative value entry point
```

> See DECISIONS.md → Scoring Weights History before changing any value.
> Always run 30-suburb eval set after any weight change.

---

## Geography Priorities

- **National scope:** all Australian suburbs considered
- **No state bias:** do not filter by state unless explicitly asked
- **Regional included:** do not exclude regional areas — infrastructure
  pipeline signal is often strongest outside capitals

---

## How to Use This File

- When ranking or filtering suburbs → apply these weights
- When explaining a score → frame it against this investor profile
- When surfacing infrastructure signals → prioritise unpriced announcements
- When comparing suburbs → use relative median as tiebreaker

---

*Last updated: Session 1*
*Weights version: v1.0 — see DECISIONS.md for change history*