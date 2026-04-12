"""
Deterministic scoring engine for Propvest.

Rules (agents.md):
- NEVER use LLM to compute scores — all math is done here
- Score is a weighted sum of normalised signal values (0–100)
- Missing signals trigger Dynamic Re-weighting: present signal weights are
  scaled up proportionally so they still sum to 100%

Entry point:
    score_suburb(suburb, config=None) -> SuburbScorecard

Config keys read from config.yaml:
    scoring_weights  — signal name → weight (must sum to 1.0)
    scoring_bounds   — signal name → {min, max, direction}

Signal direction:
    "low_is_good"  — lower raw value = higher score (vacancy, stock on market)
    "high_is_good" — higher raw value = higher score (population growth, infra)

Note on population_growth:
    The Suburb model stores pop_growth_rate directly. To include it in scoring,
    the data pipeline must emit a DataSignal(name='population_growth', value=...)
    into suburb.signals — this engine does not read raw Suburb fields.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml

from core.schemas.scorecard import SuburbScorecard
from core.schemas.suburb import Suburb

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _normalise(value: float, min_val: float, max_val: float, low_is_good: bool) -> float:
    """
    Clamp value to [min_val, max_val] and map to 0–100.
    low_is_good=True  → 0 at max_val, 100 at min_val
    low_is_good=False → 0 at min_val, 100 at max_val
    """
    if max_val == min_val:
        return 0.0
    clamped = max(min_val, min(max_val, value))
    ratio = (clamped - min_val) / (max_val - min_val)
    raw = (1.0 - ratio) if low_is_good else ratio
    return round(raw * 100.0, 2)


def score_suburb(suburb: Suburb, config: Optional[dict] = None) -> SuburbScorecard:
    """
    Score a suburb deterministically.

    Returns a SuburbScorecard where:
    - overall_score  — weighted sum (0–100)
    - component_scores — per-signal weighted contribution to overall_score
    - is_incomplete  — True if any configured signal was absent

    Dynamic re-weighting: if signals are missing, the weights of present
    signals are scaled so they still sum to 1.0. No signal is penalised
    simply for being absent.
    """
    if config is None:
        config = _load_config()

    weights: Dict[str, float] = config["scoring_weights"]
    bounds: Dict[str, dict] = config["scoring_bounds"]

    # Index suburb signals by name for O(1) lookup
    signal_map = {s.name: s for s in suburb.signals}

    present_weights: Dict[str, float] = {}
    normalised_scores: Dict[str, float] = {}

    for signal_name, weight in weights.items():
        if signal_name not in signal_map:
            continue  # absent — will be re-weighted out

        signal = signal_map[signal_name]
        bound = bounds[signal_name]

        normalised_scores[signal_name] = _normalise(
            value=signal.value,
            min_val=bound["min"],
            max_val=bound["max"],
            low_is_good=(bound["direction"] == "low_is_good"),
        )
        present_weights[signal_name] = weight

    is_incomplete = len(present_weights) < len(weights)

    # Edge case: no signals at all
    if not present_weights:
        return SuburbScorecard(
            suburb_id=suburb.suburb_id,
            overall_score=0.0,
            component_scores={},
            is_incomplete=True,
        )

    # Dynamic re-weighting: scale present weights to sum to 1.0
    total_weight = sum(present_weights.values())
    scale = 1.0 / total_weight

    component_scores: Dict[str, float] = {}
    overall = 0.0

    for signal_name, weight in present_weights.items():
        effective_weight = weight * scale
        contribution = normalised_scores[signal_name] * effective_weight
        component_scores[signal_name] = round(contribution, 2)
        overall += contribution

    return SuburbScorecard(
        suburb_id=suburb.suburb_id,
        overall_score=round(overall, 2),
        component_scores=component_scores,
        is_incomplete=is_incomplete,
    )
