"""
Deterministic Scoring Engine — v1.1

Implements the Propvest suburb scoring formula exactly as defined in config.yaml.
Score computation is deterministic math only — LLM is NEVER used.

Signal weights (from config.yaml v1.1):
    vacancy_rate:          25%  (low = good; strong rental demand)
    stock_on_market:       20%  (low = good; supply constrained)
    population_growth:     20%  (high = good; long-term demand driver)
    infra_pipeline:        20%  (high = good; forward-looking alpha signal)
    sales_volume_momentum: 10%  (positive YoY = good; demand building)
    relative_median:        5%  (below $800k ceiling = value; vs neighbours)

Dynamic re-weighting:
    When a signal is missing (None), its weight is redistributed proportionally
    across the remaining available signals. All re-weighting is logged.

Score range: 0–100 (float, rounded for display).

Input:  SuburbSignals dataclass — raw signal values (any may be None/missing).
Output: ScorecardResult dataclass — total score, per-signal, re-weighting log.

Normalisation reference ranges (v1.1 — review after 30-suburb eval):
    vacancy_rate:          0% → 100pts   5% → 0pts   (linear; clamp)
    stock_on_market:       0  → 100pts  500 → 0pts   (linear count; pending per-dwelling norm.)
    population_growth:     0% → 0pts    3% → 100pts  (linear; clamp)
    infra_pipeline:        confidence 0.0–1.0 mapped to 0–100
    sales_volume_momentum: -40%→0  0%→50  +40%→100   (linear; clamp)
    relative_median:       $0→100  $800k→0             (linear vs $800k ceiling)

Run standalone for built-in test cases:
    python -m plugins.scoring.deterministic
"""
from __future__ import annotations

import json
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "config.yaml"

# Price ceiling from investor profile
_PRICE_CEILING = 800_000.0

# Scoring model version — must match config.yaml
_MODEL_VERSION = "v1.1"

# Signal names in weight order
_SIGNAL_KEYS = [
    "vacancy_rate",
    "stock_on_market",
    "population_growth",
    "infra_pipeline",
    "sales_volume_momentum",
    "relative_median",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SuburbSignals:
    """
    Raw signal inputs for scoring one suburb.
    Any field may be None — triggers dynamic re-weighting for that signal.

    Scored signals:
        vacancy_rate:          % vacancy (0.0–100.0 range; e.g. 1.5 = 1.5%)
        stock_on_market:       Raw listing count (from SQM)
        population_growth:     Annual % LGA ERP growth (from ABS; e.g. 1.2 = 1.2%)
        infra_pipeline:        Confidence score 0.0–1.0 (from LLM parser; None until infra built)
        sales_volume_momentum: YoY change in number_sold % (computed from salesGrowthList)
        relative_median:       Standalone house median price $ (from Domain NEXT_DATA)

    Context-only (not scored; carried through for display):
        median_sold_price, number_sold, days_on_market,
        owner_occupier_pct, renter_pct, population
    """
    # Scored
    vacancy_rate: float | None = None
    stock_on_market: int | None = None
    population_growth: float | None = None
    infra_pipeline: float | None = None
    sales_volume_momentum: float | None = None
    relative_median: float | None = None

    # Context only (display; not scored)
    median_sold_price: float | None = None
    number_sold: int | None = None
    days_on_market: int | None = None
    owner_occupier_pct: float | None = None
    renter_pct: float | None = None
    population: int | None = None

    # Flags
    data_thin: bool = False
    above_price_ceiling: bool = False


@dataclass
class ScorecardResult:
    """
    Output from the deterministic scoring engine for one suburb.

    Fields:
        suburb_name:       Canonical suburb name
        state:             2-letter state code
        total_score:       Weighted composite score, 0–100
        per_signal_scores: {signal: raw_signal_score_0_100} — before weight application
        effective_weights: {signal: actual_weight_used} — after re-weighting
        missing_signals:   Signals that were None (excluded from scoring)
        reweight_log:      Human-readable description of re-weighting applied (or None)
        data_thin:         True if numberSold < 12 → unreliable, exclude from ranking
        above_price_ceiling: True if median > $800k → outside budget
        scoring_model_version: Config version this scorecard was produced under
    """
    suburb_name: str
    state: str
    total_score: float
    per_signal_scores: dict[str, float]
    effective_weights: dict[str, float]
    missing_signals: list[str]
    reweight_log: str | None
    data_thin: bool
    above_price_ceiling: bool
    scoring_model_version: str = _MODEL_VERSION

    def to_dict(self) -> dict:
        return {
            "suburb_name": self.suburb_name,
            "state": self.state,
            "total_score": round(self.total_score, 2),
            "per_signal_scores": {k: round(v, 2) for k, v in self.per_signal_scores.items()},
            "effective_weights": {k: round(v, 4) for k, v in self.effective_weights.items()},
            "missing_signals": self.missing_signals,
            "reweight_log": self.reweight_log,
            "data_thin": self.data_thin,
            "above_price_ceiling": self.above_price_ceiling,
            "scoring_model_version": self.scoring_model_version,
        }


# ---------------------------------------------------------------------------
# Normalisation functions (each maps raw signal → 0–100 score)
# ---------------------------------------------------------------------------

def _score_vacancy_rate(vr: float) -> float:
    """
    0% vacancy → 100pts  (perfectly low, strong rental demand)
    5% vacancy → 0pts    (very high, weak demand)
    Linear, clamped to [0, 100].

    Australian average ~1-2%. Sub-1% = exceptional demand signal.
    """
    score = 100.0 * (1.0 - vr / 5.0)
    return max(0.0, min(100.0, score))


def _score_stock_on_market(count: int) -> float:
    """
    Raw listing count from SQM Research.
    0 listings   → 100pts  (supply fully constrained)
    500 listings → 0pts    (very high supply)
    Linear, clamped to [0, 100].

    NOTE: v1.1 uses absolute count. Normalisation vs dwelling count is pending
    once we have per-suburb dwelling totals. Flag for v1.2 review.
    """
    score = 100.0 * (1.0 - count / 500.0)
    return max(0.0, min(100.0, score))


def _score_population_growth(growth_pct: float) -> float:
    """
    0% annual growth → 0pts   (stagnant)
    3% annual growth → 100pts (strong)
    Linear, clamped to [0, 100]. Negative growth → 0.

    ABS average national growth ~1.5%. Tier 1 minimum = 0.5%.
    """
    score = 100.0 * (growth_pct / 3.0)
    return max(0.0, min(100.0, score))


def _score_infra_pipeline(confidence: float) -> float:
    """
    Confidence score from LLM infrastructure parser, 0.0–1.0.
    Mapped linearly to 0–100.
    """
    score = confidence * 100.0
    return max(0.0, min(100.0, score))


def _score_sales_volume_momentum(yoy_change_pct: float) -> float:
    """
    YoY change in number_sold (as a percentage, e.g. 10.0 = +10%).
    -40% → 0pts   (sharp decline in sales activity)
     0%  → 50pts  (flat — neither positive nor negative signal)
    +40% → 100pts (strong momentum)
    Linear, clamped to [0, 100].
    """
    score = 50.0 + (yoy_change_pct / 40.0) * 50.0
    return max(0.0, min(100.0, score))


def _score_relative_median(median_price: float) -> float:
    """
    Standalone house median price vs $800k investor ceiling.
    $0 → 100pts  (maximum relative value)
    $800k → 0pts (at ceiling; no value gap)
    Linear, clamped to [0, 100].

    NOTE v1.1: This scores against the absolute price ceiling.
    "Relative to neighbours" comparison requires neighbour median data
    which isn't available until more suburbs are scraped. Flagged for v1.2.
    """
    score = 100.0 * (1.0 - median_price / _PRICE_CEILING)
    return max(0.0, min(100.0, score))


# Map signal key → normalisation function
_NORMALISE: dict[str, Any] = {
    "vacancy_rate": _score_vacancy_rate,
    "stock_on_market": _score_stock_on_market,
    "population_growth": _score_population_growth,
    "infra_pipeline": _score_infra_pipeline,
    "sales_volume_momentum": _score_sales_volume_momentum,
    "relative_median": _score_relative_median,
}


# ---------------------------------------------------------------------------
# Dynamic re-weighting
# ---------------------------------------------------------------------------

def _apply_reweighting(
    base_weights: dict[str, float],
    missing: list[str],
) -> tuple[dict[str, float], str | None]:
    """
    Redistribute missing-signal weights proportionally across available signals.

    Returns (effective_weights, reweight_log).
    """
    if not missing:
        return dict(base_weights), None

    available = {k: v for k, v in base_weights.items() if k not in missing}
    removed_weight = sum(base_weights[k] for k in missing)
    total_available = sum(available.values())

    if total_available == 0:
        # No signals at all — return zero weights
        return {k: 0.0 for k in base_weights}, "ALL signals missing — score is 0"

    scale = (total_available + removed_weight) / total_available
    effective = {k: v * scale for k, v in available.items()}
    for k in missing:
        effective[k] = 0.0

    log_parts = [
        f"Missing signals: {', '.join(missing)}.",
        f"Redistributed {removed_weight:.0%} weight proportionally across "
        f"{', '.join(available.keys())}.",
        f"Scale factor applied: {scale:.4f}.",
    ]
    return effective, " ".join(log_parts)


# ---------------------------------------------------------------------------
# Core scorer
# ---------------------------------------------------------------------------

def load_weights() -> dict[str, float]:
    """Load scoring weights from config.yaml."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    return cfg["scoring_weights"]


def score_suburb(
    suburb_name: str,
    state: str,
    signals: SuburbSignals,
    weights: dict[str, float] | None = None,
) -> ScorecardResult:
    """
    Score a single suburb deterministically.

    Args:
        suburb_name: Canonical suburb name (for output label only)
        state:       2-letter state code
        signals:     SuburbSignals instance (any field may be None)
        weights:     Override weights dict (defaults to config.yaml)

    Returns:
        ScorecardResult with total score, per-signal breakdown, and re-weighting log.
    """
    if weights is None:
        weights = load_weights()

    # --- Extract raw values from signals ---
    raw: dict[str, float | None] = {
        "vacancy_rate": signals.vacancy_rate,
        "stock_on_market": float(signals.stock_on_market) if signals.stock_on_market is not None else None,
        "population_growth": signals.population_growth,
        "infra_pipeline": signals.infra_pipeline,
        "sales_volume_momentum": signals.sales_volume_momentum,
        "relative_median": signals.relative_median,
    }

    # --- Identify missing signals ---
    missing = [k for k in _SIGNAL_KEYS if raw.get(k) is None]
    available_keys = [k for k in _SIGNAL_KEYS if raw.get(k) is not None]

    # --- Normalise each available signal to 0–100 ---
    per_signal: dict[str, float] = {}
    for key in available_keys:
        fn = _NORMALISE[key]
        per_signal[key] = fn(raw[key])

    # --- Dynamic re-weighting ---
    base_weights = {k: weights[k] for k in _SIGNAL_KEYS}
    effective_weights, reweight_log = _apply_reweighting(base_weights, missing)

    # --- Compute total score ---
    total = sum(per_signal[k] * effective_weights[k] for k in available_keys)

    return ScorecardResult(
        suburb_name=suburb_name,
        state=state,
        total_score=total,
        per_signal_scores=per_signal,
        effective_weights=effective_weights,
        missing_signals=missing,
        reweight_log=reweight_log,
        data_thin=signals.data_thin,
        above_price_ceiling=signals.above_price_ceiling,
    )


# ---------------------------------------------------------------------------
# Helpers for signal extraction from raw scraper data
# ---------------------------------------------------------------------------

def extract_sales_volume_momentum(sales_growth_list: list[dict]) -> float | None:
    """
    Compute YoY momentum from Domain salesGrowthList.

    salesGrowthList format: [{"year": 2022, "numberSold": 28, ...}, ...]
    Uses two most recent consecutive years.

    Returns YoY change as a percentage (e.g. 10.0 = +10%),
    or None if insufficient data.
    """
    if not sales_growth_list or len(sales_growth_list) < 2:
        return None

    sorted_years = sorted(sales_growth_list, key=lambda r: r.get("year", 0))
    recent = sorted_years[-2:]

    prev_sold = recent[0].get("numberSold") or 0
    curr_sold = recent[1].get("numberSold") or 0

    if prev_sold == 0:
        return None  # Can't compute change from zero baseline

    yoy_pct = (curr_sold - prev_sold) / prev_sold * 100.0
    return yoy_pct


def build_signals_from_raw(
    domain_record: dict,
    sqm_record: dict | None,
    trinity_record: dict,
) -> SuburbSignals:
    """
    Assemble a SuburbSignals from raw scraper outputs.

    Args:
        domain_record:  Record from domain_signals.json
        sqm_record:     Record from sqm_signals.json (keyed by postcode), or None
        trinity_record: Record from geography_trinity.json (ABS data)
    """
    # Sales volume momentum from salesGrowthList
    momentum = extract_sales_volume_momentum(
        domain_record.get("sales_growth_list") or []
    )

    median_price = domain_record.get("median_sold_price")
    above_ceiling = (median_price or 0) > _PRICE_CEILING

    return SuburbSignals(
        # Scored signals
        vacancy_rate=sqm_record.get("vacancy_rate") if sqm_record else None,
        stock_on_market=sqm_record.get("stock_on_market") if sqm_record else None,
        population_growth=trinity_record.get("abs_growth_rate"),
        infra_pipeline=None,  # Not yet implemented — no infra scraper in v1.1
        sales_volume_momentum=momentum,
        relative_median=median_price,
        # Context
        median_sold_price=median_price,
        number_sold=domain_record.get("number_sold"),
        days_on_market=domain_record.get("days_on_market"),
        owner_occupier_pct=domain_record.get("owner_occupier_pct"),
        renter_pct=domain_record.get("renter_pct"),
        population=trinity_record.get("population"),
        # Flags
        data_thin=domain_record.get("data_thin", False),
        above_price_ceiling=above_ceiling,
    )


# ---------------------------------------------------------------------------
# Batch scorer — reads from local JSON files, writes to Supabase suburbs table
# ---------------------------------------------------------------------------

def score_all_suburbs(write_to_supabase: bool = False) -> list[dict]:
    """
    Score all suburbs that have at least one signal available.

    Loads:
        data/raw/domain_signals.json    — Domain scrape outputs
        data/raw/sqm_signals.json       — SQM vacancy + stock
        data/raw/geography_trinity.json — ABS population growth

    Returns list of scorecard dicts.
    Optionally writes score + score_version back to Supabase suburbs table.

    NOTE: Supabase write requires migration 002_add_score_columns.sql to be run first.
    The suburbs table needs: score NUMERIC(5,2), score_version TEXT, scored_at TIMESTAMPTZ.
    """
    domain_path = ROOT / "data" / "raw" / "domain_signals.json"
    sqm_path = ROOT / "data" / "raw" / "sqm_signals.json"
    trinity_path = ROOT / "data" / "raw" / "geography_trinity.json"

    if not domain_path.exists():
        logger.warning("domain_signals.json not found — no Domain signals to score")
        domain_records = []
    else:
        domain_records = json.loads(domain_path.read_text())

    # SQM keyed by postcode
    sqm_by_postcode: dict[str, dict] = {}
    if sqm_path.exists():
        sqm_raw = json.loads(sqm_path.read_text())
        if isinstance(sqm_raw, list):
            for r in sqm_raw:
                if r.get("postcode"):
                    sqm_by_postcode[str(r["postcode"])] = r
        elif isinstance(sqm_raw, dict):
            sqm_by_postcode = sqm_raw

    # Trinity keyed by domain_slug
    trinity_by_slug: dict[str, dict] = {}
    if trinity_path.exists():
        for r in json.loads(trinity_path.read_text()):
            if r.get("domain_slug"):
                trinity_by_slug[r["domain_slug"]] = r

    weights = load_weights()
    scorecards: list[dict] = []

    for domain_rec in domain_records:
        slug = domain_rec.get("slug", "")
        trinity_rec = trinity_by_slug.get(slug, {})
        postcode = trinity_rec.get("postcode", "")
        sqm_rec = sqm_by_postcode.get(str(postcode)) if postcode else None

        suburb_name = trinity_rec.get("suburb_name") or slug
        state = trinity_rec.get("state", "?")

        signals = build_signals_from_raw(domain_rec, sqm_rec, trinity_rec)
        result = score_suburb(suburb_name, state, signals, weights)
        scorecards.append(result.to_dict())

    logger.info("Scored %d suburbs", len(scorecards))

    if write_to_supabase and scorecards:
        _write_scores_to_supabase(scorecards)

    return scorecards


def _write_scores_to_supabase(scorecards: list[dict]) -> None:
    """
    Write scores back to the Supabase suburbs table.

    REQUIRES: migration 002_add_score_columns.sql must be run first.
    The suburbs table must have columns: score, score_version, scored_at.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass

    import os
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        logger.error("Supabase credentials not set — skipping score write")
        return

    from supabase import create_client
    from datetime import datetime, timezone
    client = create_client(url, key)

    ok = err = 0
    for sc in scorecards:
        try:
            (
                client.table("suburbs")
                .update({
                    "score": sc["total_score"],
                    "score_version": sc["scoring_model_version"],
                    "scored_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("suburb_name", sc["suburb_name"])
                .eq("state", sc["state"])
                .execute()
            )
            ok += 1
        except Exception as exc:
            logger.warning("Supabase score write failed for %s/%s: %s", sc["suburb_name"], sc["state"], exc)
            err += 1

    logger.info("Supabase score write: %d OK, %d errors", ok, err)


# ---------------------------------------------------------------------------
# Built-in test cases
# ---------------------------------------------------------------------------

def _run_tests(weights: dict[str, float]) -> None:
    """
    Test the scorer against three canonical scenarios.
    Prints pass/fail for each with score and expected range.
    """
    print("\n" + "=" * 60)
    print("DETERMINISTIC SCORER — v1.1 TEST CASES")
    print("=" * 60)

    # ----------------------------------------------------------------
    # Test 1: High-vacancy regional town (should score LOW)
    # ----------------------------------------------------------------
    t1 = SuburbSignals(
        vacancy_rate=4.5,           # very high — weak rental demand
        stock_on_market=600,        # very high — oversupplied
        population_growth=0.3,      # below Tier 1 threshold
        infra_pipeline=None,        # missing → re-weighting
        sales_volume_momentum=-15.0,  # declining sales
        relative_median=320_000.0,  # well below ceiling
    )
    r1 = score_suburb("Dusty Creek", "QLD", t1, weights)
    passed1 = r1.total_score < 30
    print(f"\nTest 1: High-vacancy regional town")
    print(f"  Score:    {r1.total_score:.1f} / 100")
    print(f"  Expected: <30  ({'PASS' if passed1 else 'FAIL'})")
    print(f"  Per-signal: {json.dumps({k: round(v,1) for k,v in r1.per_signal_scores.items()})}")
    print(f"  Re-weighting: {r1.reweight_log}")

    # ----------------------------------------------------------------
    # Test 2: Low-vacancy, high-growth suburb (should score HIGH)
    # ----------------------------------------------------------------
    t2 = SuburbSignals(
        vacancy_rate=0.5,           # very low — strong rental demand
        stock_on_market=25,         # very low — supply constrained
        population_growth=2.5,      # strong growth
        infra_pipeline=None,        # missing → re-weighting
        sales_volume_momentum=25.0,   # strong momentum
        relative_median=550_000.0,  # below ceiling, moderate value
    )
    r2 = score_suburb("Greenfield Heights", "WA", t2, weights)
    passed2 = r2.total_score > 65
    print(f"\nTest 2: Low-vacancy, high-growth suburb")
    print(f"  Score:    {r2.total_score:.1f} / 100")
    print(f"  Expected: >65  ({'PASS' if passed2 else 'FAIL'})")
    print(f"  Per-signal: {json.dumps({k: round(v,1) for k,v in r2.per_signal_scores.items()})}")
    print(f"  Re-weighting: {r2.reweight_log}")

    # ----------------------------------------------------------------
    # Test 3: Suburb with multiple missing signals (re-weighting trigger)
    # ----------------------------------------------------------------
    t3 = SuburbSignals(
        vacancy_rate=1.5,           # moderate
        stock_on_market=None,       # MISSING
        population_growth=None,     # MISSING
        infra_pipeline=None,        # MISSING
        sales_volume_momentum=10.0,   # modest positive momentum
        relative_median=420_000.0,  # moderate value
    )
    r3 = score_suburb("Partial Data Suburb", "NT", t3, weights)
    passed3 = (
        len(r3.missing_signals) == 3
        and r3.reweight_log is not None
        and abs(sum(r3.effective_weights.values()) - 1.0) < 0.001
    )
    print(f"\nTest 3: Suburb with 3 missing signals")
    print(f"  Score:          {r3.total_score:.1f} / 100")
    print(f"  Missing:        {r3.missing_signals}")
    print(f"  Re-weighting:   {r3.reweight_log}")
    print(f"  Eff. weights:   {json.dumps({k: round(v,4) for k,v in r3.effective_weights.items()})}")
    print(f"  Weight sum:     {sum(r3.effective_weights.values()):.4f} (expected 1.0000)")
    print(f"  Test passed:    {'PASS' if passed3 else 'FAIL'}")

    all_passed = passed1 and passed2 and passed3
    print(f"\n{'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 60)
    return all_passed


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse
    parser = argparse.ArgumentParser(description="Propvest Deterministic Scoring Engine v1.1")
    parser.add_argument("--test", action="store_true", help="Run built-in test cases")
    parser.add_argument("--score-all", action="store_true", help="Score all scraped suburbs")
    parser.add_argument("--write-supabase", action="store_true",
                        help="Write scores to Supabase (requires migration 002)")
    parser.add_argument("--top", type=int, default=20, help="Show top N suburbs (default 20)")
    args = parser.parse_args()

    weights = load_weights()
    logger.info("Loaded scoring weights: %s", weights)
    logger.info("Model version: %s", _MODEL_VERSION)

    if args.test or (not args.score_all):
        passed = _run_tests(weights)
        if not args.score_all:
            sys.exit(0 if passed else 1)

    if args.score_all:
        scorecards = score_all_suburbs(write_to_supabase=args.write_supabase)

        if not scorecards:
            print("\nNo scorecards produced — no Domain signals found.")
            sys.exit(0)

        sorted_cards = sorted(scorecards, key=lambda x: x["total_score"], reverse=True)

        print(f"\n{'=' * 70}")
        print(f"SUBURB RANKINGS — Top {min(args.top, len(sorted_cards))} of {len(sorted_cards)}")
        print(f"{'=' * 70}")
        print(f"{'Rank':<5} {'Suburb':<35} {'State':<5} {'Score':>6} {'Missing'}")
        print("-" * 70)
        for i, sc in enumerate(sorted_cards[:args.top], 1):
            missing = sc["missing_signals"]
            missing_str = f"[{', '.join(missing)}]" if missing else ""
            dt_flag = " [data_thin]" if sc["data_thin"] else ""
            ceil_flag = " [>$800k]" if sc["above_price_ceiling"] else ""
            print(
                f"{i:<5} {sc['suburb_name']:<35} {sc['state']:<5} "
                f"{sc['total_score']:>6.1f} {missing_str}{dt_flag}{ceil_flag}"
            )

        sys.exit(0)
