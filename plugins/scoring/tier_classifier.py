"""
Scrape Tier Classifier

Classifies each QLD/WA/NT/TAS/ACT suburb into a scrape tier:
  Hot   — weekly scrape   (high turnover, growth signal strong)
  Warm  — monthly scrape  (moderate turnover)
  Cold  — quarterly scrape (slow market or borderline Tier 1)

Bootstrap classifier (before any Domain data):
  Uses ABS population growth rate from geography_trinity.json:
    Hot:  abs_growth_rate > 2%
    Warm: 0.5% ≤ abs_growth_rate ≤ 2%
    Cold: < 0.5% (passed Tier 1 filter but borderline)

Post-scrape reclassification (after first Domain scrape pass):
  Uses actual daysOnMarket from domain_signals.json:
    Hot:  DOM < 30 days
    Warm: 30 ≤ DOM ≤ 60 days
    Cold: DOM > 60 days

Run standalone:
    # Bootstrap from ABS (run before first Domain scrape)
    python -m plugins.scoring.tier_classifier --mode bootstrap

    # Reclassify using real DOM data (run after first Domain scrape)
    python -m plugins.scoring.tier_classifier --mode reclassify
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
TRINITY_PATH = ROOT / "data" / "raw" / "geography_trinity.json"
DOMAIN_SIGNALS_PATH = ROOT / "data" / "raw" / "domain_signals.json"

# States that use Domain scraping (not Valuer General)
_DOMAIN_STATES = {"QLD", "WA", "NT", "TAS", "ACT"}

# Bootstrap thresholds (ABS annual % growth rate)
_BOOTSTRAP_HOT_THRESHOLD = 2.0    # > 2% → Hot
_BOOTSTRAP_WARM_MIN = 0.5          # 0.5–2% → Warm (same as Tier 1 filter floor)
# Below 0.5% is impossible for Tier 1 suburbs (they passed the filter) except floating-point
# edge cases — those go to Warm

# DOM thresholds for reclassification
_DOM_HOT_MAX = 30    # DOM < 30 days → Hot
_DOM_COLD_MIN = 60   # DOM > 60 days → Cold


def bootstrap(suburbs: list[dict]) -> list[dict]:
    """
    Assign scrape_tier using ABS growth rate.
    Only applies to Domain-scraped states (QLD/WA/NT/TAS/ACT).
    NSW/VIC/SA are not tiered — their Valuer General data is bulk-downloaded regardless.
    """
    classified = 0
    for suburb in suburbs:
        if suburb.get("state", "").upper() not in _DOMAIN_STATES:
            continue

        growth = suburb.get("abs_growth_rate") or 0.0

        if growth > _BOOTSTRAP_HOT_THRESHOLD:
            tier = "Hot"
        elif growth >= _BOOTSTRAP_WARM_MIN:
            tier = "Warm"
        else:
            tier = "Cold"

        suburb["scrape_tier"] = tier
        classified += 1

    logger.info("Bootstrap: %d suburbs classified", classified)
    return suburbs


def reclassify(suburbs: list[dict], domain_signals: list[dict]) -> list[dict]:
    """
    Reclassify scrape_tier using actual daysOnMarket from Domain scrape.
    Only overwrites suburbs that have real DOM data available.
    """
    # Build lookup: slug → dom
    dom_lookup: dict[str, int] = {}
    for signal in domain_signals:
        slug = signal.get("slug", "")
        dom = signal.get("days_on_market")
        if slug and dom is not None:
            dom_lookup[slug] = int(dom)

    reclassified = 0
    for suburb in suburbs:
        if suburb.get("state", "").upper() not in _DOMAIN_STATES:
            continue

        slug = suburb.get("domain_slug", "")
        dom = dom_lookup.get(slug)
        if dom is None:
            continue  # no real data yet — keep bootstrap tier

        if dom < _DOM_HOT_MAX:
            tier = "Hot"
        elif dom <= _DOM_COLD_MIN:
            tier = "Warm"
        else:
            tier = "Cold"

        suburb["scrape_tier"] = tier
        reclassified += 1

    logger.info("Reclassify: %d suburbs updated from DOM data", reclassified)
    return suburbs


def run(mode: str = "bootstrap") -> list[dict]:
    """
    Load geography_trinity.json, classify, write back.
    mode: "bootstrap" | "reclassify"
    """
    if not TRINITY_PATH.exists():
        raise FileNotFoundError(
            "geography_trinity.json not found — run geography_builder first:\n"
            "    python -m plugins.scrapers.geography_builder"
        )

    suburbs = json.loads(TRINITY_PATH.read_text())

    if mode == "bootstrap":
        suburbs = bootstrap(suburbs)
    elif mode == "reclassify":
        if not DOMAIN_SIGNALS_PATH.exists():
            raise FileNotFoundError(
                "domain_signals.json not found — run a Domain scrape first:\n"
                "    python -m plugins.scrapers.domain_next_data --batch 50"
            )
        domain_signals = json.loads(DOMAIN_SIGNALS_PATH.read_text())
        suburbs = reclassify(suburbs, domain_signals)
    else:
        raise ValueError(f"Unknown mode: {mode!r}. Use 'bootstrap' or 'reclassify'.")

    # Write back to geography_trinity.json
    TRINITY_PATH.write_text(json.dumps(suburbs, indent=2, default=str))
    logger.info("Written %d records to %s", len(suburbs), TRINITY_PATH)

    # Print tier summary
    from collections import Counter
    domain_suburbs = [s for s in suburbs if s.get("state", "").upper() in _DOMAIN_STATES]
    tier_counts = Counter(s.get("scrape_tier") for s in domain_suburbs)
    logger.info(
        "Tier summary (Domain states): Hot=%d  Warm=%d  Cold=%d  unclassified=%d",
        tier_counts.get("Hot", 0),
        tier_counts.get("Warm", 0),
        tier_counts.get("Cold", 0),
        tier_counts.get(None, 0),
    )

    return suburbs


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Scrape Tier Classifier")
    parser.add_argument(
        "--mode",
        choices=["bootstrap", "reclassify"],
        default="bootstrap",
        help="bootstrap: use ABS growth rate | reclassify: use real DOM data",
    )
    args = parser.parse_args()

    suburbs = run(mode=args.mode)

    domain_suburbs = [s for s in suburbs if s.get("state", "").upper() in _DOMAIN_STATES]
    from collections import Counter
    counts = Counter(s.get("scrape_tier") for s in domain_suburbs)
    print(f"\nDone. Tier summary for Domain states ({len(domain_suburbs)} suburbs):")
    print(f"  Hot:  {counts.get('Hot', 0)}")
    print(f"  Warm: {counts.get('Warm', 0)}")
    print(f"  Cold: {counts.get('Cold', 0)}")
    sys.exit(0)
