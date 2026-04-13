# Propvest — Investor Context & Scoring Weights

> Hermes and Claude read this to personalise research and analysis.
> Update when your investment strategy or scoring priorities change.

---

## Investor Profile

| Attribute     | Detail                                     |
| ------------- | ------------------------------------------ |
| Strategy      | Buy and hold — capital growth focus        |
| Geography     | All of Australia (~15,000 suburbs)         |
| Asset class   | Standalone residential houses only         |
| Price ceiling | $800,000 suburb median (standalone house)  |
| Horizon       | Long term (7-10+ years)                    |
| Risk appetite | Moderate — growth focused, not speculative |

---

## What "Good" Looks Like

A high-scoring suburb for this investor has:

- Low and falling vacancy rate (strong rental demand)
- Low stock on market (supply constrained)
- Population growing faster than state average
- Confirmed infrastructure pipeline not yet priced in by market
- Rising sales volume quarter-on-quarter (demand building)
- Standalone house median ≤ $800k with relative value vs neighbours

---

## What to Avoid

- High vacancy rates (weak rental demand)
- Oversupplied markets (high stock on market)
- Shrinking or flat population
- No infrastructure pipeline or government investment signals
- Suburb median > $800k (outside budget)
- Fewer than 12 house sales in trailing 12 months (data_thin — unreliable signal)
- Units, townhouses, apartments (excluded from scope entirely)

---

## Scoring Weights (v1.1)

```yaml
scoring_weights:
  vacancy_rate: 0.25 # strongest demand signal
  stock_on_market: 0.20 # supply constraint signal
  population_growth: 0.20 # long term demand driver
  infra_pipeline: 0.20 # forward-looking alpha signal
  sales_volume_momentum: 0.10 # Q-on-Q house sales trend
  relative_median: 0.05 # relative value entry point
```

> See DECISIONS.md → Scoring Weights History before changing any value.
> Always run 30-suburb eval set after any weight change.

---

## Context Layer (Display Only — Not Scored)

These signals appear on suburb cards but do not affect the score:

- Days on market trend
- Auction clearance rate
- Owner-occupier vs renter percentage
- Population count
- Income-to-median affordability ratio (ABS Census data — display only, too stale to score)

---

## Red Flag Alerts

These trigger alerts on suburb cards but do not affect the score directly:

- Owner-occupier ratio < 70% → investor concentration risk
- Renter concentration > 50% → investor concentration risk
- House sales < 12 trailing 12 months → data_thin, excluded from scoring

---

## Geography Priorities

- **National scope:** all Australian suburbs considered
- **No state bias:** do not filter by state unless explicitly asked
- **Regional included:** do not exclude regional areas — infrastructure pipeline signal often strongest outside capitals
- **Standalone houses only:** never include unit or townhouse data in scoring or recommendations

---

## How to Use This File

- When ranking or filtering suburbs → apply v1.1 weights
- When explaining a score → frame it against this investor profile
- When surfacing infrastructure signals → prioritise unpriced announcements
- When comparing suburbs → use relative median as tiebreaker
- When a suburb has <12 house sales → flag as data_thin, do not score

---

_Last updated: Session 6_
_Weights version: v1.1 — see DECISIONS.md for change history_
