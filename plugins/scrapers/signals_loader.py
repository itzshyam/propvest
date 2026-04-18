"""
Signals Loader — Wire Domain + SQM scraper outputs → Supabase signals table

Reads domain_signals.json and sqm_signals.json and upserts each signal value
as a separate row in the Supabase `signals` table.

REQUIRES: Migration 002_add_signals_and_scores.sql must be run in Supabase
SQL editor before this script can write.

Signal mapping:
    DOMAIN → signals:
        median_sold_price, number_sold, days_on_market,
        auction_clearance_rate, owner_occupier_pct, renter_pct,
        sales_volume_momentum (computed from salesGrowthList)

    SQM → signals:
        vacancy_rate, stock_on_market

    ABS (from geography_trinity.json) → signals:
        population_growth (abs_growth_rate)

Upsert key: (suburb_name, state, signal_name, source) — latest wins.

Run standalone:
    python -m plugins.scrapers.signals_loader
    python -m plugins.scrapers.signals_loader --dry-run
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
DOMAIN_PATH = ROOT / "data" / "raw" / "domain_signals.json"
SQM_PATH = ROOT / "data" / "raw" / "sqm_signals.json"
TRINITY_PATH = ROOT / "data" / "raw" / "geography_trinity.json"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

BATCH_SIZE = 200


# ---------------------------------------------------------------------------
# Signal extraction helpers
# ---------------------------------------------------------------------------

def _extract_sales_momentum(sales_growth_list: list[dict]) -> float | None:
    """Compute YoY change in number_sold from Domain salesGrowthList."""
    if not sales_growth_list or len(sales_growth_list) < 2:
        return None
    sorted_years = sorted(sales_growth_list, key=lambda r: r.get("year", 0))
    recent = sorted_years[-2:]
    prev = recent[0].get("numberSold") or 0
    curr = recent[1].get("numberSold") or 0
    if prev == 0:
        return None
    return (curr - prev) / prev * 100.0


def _domain_to_signal_rows(record: dict, trinity_by_slug: dict[str, dict]) -> list[dict]:
    """
    Convert one Domain scrape record into signal rows for Supabase.
    Returns [] if no slug or no matching trinity record.
    """
    slug = record.get("slug", "")
    trinity = trinity_by_slug.get(slug)
    if not trinity:
        logger.debug("No trinity match for slug %s — skipping", slug)
        return []

    suburb_name = trinity.get("suburb_name", slug)
    state = trinity.get("state", "?")
    postcode = trinity.get("postcode") or None
    scraped_at = record.get("scraped_at") or datetime.now(timezone.utc).isoformat()

    # Signals to extract: (signal_name, value, unit)
    signal_specs = [
        ("median_sold_price", record.get("median_sold_price"), "dollars"),
        ("number_sold",        record.get("number_sold"),        "count"),
        ("days_on_market",     record.get("days_on_market"),     "days"),
        ("auction_clearance_rate", record.get("auction_clearance_rate"), "ratio"),
        ("owner_occupier_pct", record.get("owner_occupier_pct"), "ratio"),
        ("renter_pct",         record.get("renter_pct"),         "ratio"),
    ]

    # Computed: sales volume momentum
    momentum = _extract_sales_momentum(record.get("sales_growth_list") or [])
    if momentum is not None:
        signal_specs.append(("sales_volume_momentum", momentum, "percent"))

    rows = []
    for signal_name, value, unit in signal_specs:
        if value is None:
            continue
        rows.append({
            "suburb_name": suburb_name,
            "state":        state,
            "postcode":     postcode,
            "signal_name":  signal_name,
            "value":        float(value),
            "source":       "DOMAIN",
            "unit":         unit,
            "scraped_at":   scraped_at,
            "raw_json":     None,  # omit full record to keep rows small
        })

    return rows


def _sqm_to_signal_rows(record: dict, trinity_by_postcode: dict[str, list[dict]]) -> list[dict]:
    """
    Convert one SQM scrape record into signal rows for Supabase.
    SQM is postcode-level — may match multiple suburbs sharing a postcode.
    """
    postcode = str(record.get("postcode", "")).strip()
    if not postcode:
        return []

    scraped_at = record.get("scraped_at") or datetime.now(timezone.utc).isoformat()
    vacancy_rate = record.get("vacancy_rate")
    stock = record.get("stock_on_market")

    suburbs_in_postcode = trinity_by_postcode.get(postcode, [])
    if not suburbs_in_postcode:
        logger.debug("No suburbs match postcode %s — skipping SQM record", postcode)
        return []

    rows = []
    for trinity in suburbs_in_postcode:
        suburb_name = trinity.get("suburb_name", "")
        state = trinity.get("state", "?")

        specs = []
        if vacancy_rate is not None:
            specs.append(("vacancy_rate", float(vacancy_rate), "percent"))
        if stock is not None:
            specs.append(("stock_on_market", float(stock), "count"))

        for signal_name, value, unit in specs:
            rows.append({
                "suburb_name": suburb_name,
                "state":        state,
                "postcode":     postcode,
                "signal_name":  signal_name,
                "value":        value,
                "source":       "SQM",
                "unit":         unit,
                "scraped_at":   scraped_at,
                "raw_json":     None,
            })

    return rows


def _abs_to_signal_rows(trinity_records: list[dict]) -> list[dict]:
    """
    Extract population_growth from geography_trinity.json → signal rows.
    """
    rows = []
    for trinity in trinity_records:
        growth = trinity.get("abs_growth_rate")
        if growth is None:
            continue
        rows.append({
            "suburb_name": trinity.get("suburb_name", ""),
            "state":        trinity.get("state", "?"),
            "postcode":     trinity.get("postcode") or None,
            "signal_name":  "population_growth",
            "value":        float(growth),
            "source":       "ABS",
            "unit":         "percent",
            "scraped_at":   datetime.now(timezone.utc).isoformat(),
            "raw_json":     None,
        })
    return rows


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

def load_signals(dry_run: bool = False) -> dict:
    """
    Read all signal files and upsert into Supabase signals table.

    Returns summary: {total, upserted, errors, skipped}
    """
    # Load source files
    if not DOMAIN_PATH.exists():
        logger.warning("domain_signals.json not found — no Domain signals to load")
        domain_records = []
    else:
        domain_records = json.loads(DOMAIN_PATH.read_text())

    if not SQM_PATH.exists():
        logger.warning("sqm_signals.json not found — no SQM signals to load")
        sqm_records = []
    else:
        sqm_records = json.loads(SQM_PATH.read_text())

    trinity_records = []
    if TRINITY_PATH.exists():
        trinity_records = json.loads(TRINITY_PATH.read_text())

    # Build lookup indexes
    trinity_by_slug: dict[str, dict] = {
        r["domain_slug"]: r for r in trinity_records if r.get("domain_slug")
    }
    # Postcode → list of suburbs (multiple suburbs share a postcode)
    trinity_by_postcode: dict[str, list[dict]] = {}
    for r in trinity_records:
        pc = str(r.get("postcode", "") or "")
        if pc:
            trinity_by_postcode.setdefault(pc, []).append(r)

    # Build all signal rows
    all_rows: list[dict] = []

    for rec in domain_records:
        all_rows.extend(_domain_to_signal_rows(rec, trinity_by_slug))

    for rec in sqm_records:
        all_rows.extend(_sqm_to_signal_rows(rec, trinity_by_postcode))

    all_rows.extend(_abs_to_signal_rows(trinity_records))

    # Deduplicate by upsert key (suburb_name, state, signal_name, source).
    # geography_trinity.json contains 385+ duplicate (suburb_name, state) pairs from the
    # ABS SAL→LGA M:N concordance join. Without dedup, the same conflict key appears twice
    # in one batch → PostgreSQL error 21000. Mirror of the supabase_loader.py fix.
    # Tiebreak: keep the row with the most recent scraped_at.
    seen: dict[tuple, dict] = {}
    for row in all_rows:
        key = (row["suburb_name"], row["state"], row["signal_name"], row["source"])
        if key not in seen or (row.get("scraped_at") or "") >= (seen[key].get("scraped_at") or ""):
            seen[key] = row
    duplicates_dropped = len(all_rows) - len(seen)
    if duplicates_dropped:
        logger.warning(
            "Deduplication: dropped %d duplicate signal rows (same upsert key) — "
            "likely from multi-LGA suburbs in geography_trinity.json",
            duplicates_dropped,
        )
    all_rows = list(seen.values())

    logger.info("Signals to load: %d rows from %d Domain, %d SQM, %d ABS records",
                len(all_rows), len(domain_records), len(sqm_records), len(trinity_records))

    if dry_run:
        logger.info("DRY RUN — not writing to Supabase")
        print(f"\nDry run: would upsert {len(all_rows)} signal rows")
        if all_rows:
            print("Sample rows:")
            for r in all_rows[:5]:
                print(f"  {r['suburb_name']}/{r['state']} | {r['signal_name']} = {r['value']} ({r['source']})")
        return {"total": len(all_rows), "upserted": 0, "errors": 0, "dry_run": True}

    # Write to Supabase
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")

    from supabase import create_client
    client = create_client(url, key)

    upserted = errors = 0
    total_batches = (len(all_rows) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(all_rows), BATCH_SIZE):
        batch = all_rows[i: i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        try:
            client.table("signals").upsert(
                batch,
                on_conflict="suburb_name,state,signal_name,source",
            ).execute()
            upserted += len(batch)
            logger.info("Batch %d/%d OK (%d rows)", batch_num, total_batches, len(batch))
        except Exception as exc:
            logger.error("Batch %d/%d FAILED: %s", batch_num, total_batches, exc)
            errors += len(batch)

    summary = {"total": len(all_rows), "upserted": upserted, "errors": errors}
    logger.info("Signals load complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse
    parser = argparse.ArgumentParser(description="Load signals into Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    result = load_signals(dry_run=args.dry_run)
    print(f"\nResult: {result}")
    sys.exit(0 if result.get("errors", 0) == 0 else 1)
