"""
Supabase Loader — Bulk upsert geography_trinity.json → suburbs table

Reads all 8,639 Tier 1 suburbs from data/raw/geography_trinity.json and
bulk-upserts them into the Supabase `suburbs` table.

Idempotent: uses upsert with conflict resolution on (suburb_name, state).
Runs in batches of 500 to stay within Supabase PostgREST request size limits.

Requirements:
  - 001_create_core_tables.sql must have been run in Supabase SQL editor first
  - SUPABASE_URL and SUPABASE_ANON_KEY in .env (or environment)

Run standalone:
    python -m plugins.scrapers.supabase_loader
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
TRINITY_PATH = ROOT / "data" / "raw" / "geography_trinity.json"
BATCH_SIZE = 500

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass


def _suburb_row(s: dict) -> dict:
    """Map a geography_trinity record to the Supabase suburbs table schema."""
    return {
        "suburb_name": s.get("suburb_name"),
        "state": s.get("state"),
        "postcode": s.get("postcode") or None,
        "sal_code": s.get("sal_code") or None,
        "sa2_code": s.get("sa2_code") or None,
        "lga_code": s.get("lga_code") or None,
        "lga_name": s.get("lga_name") or None,
        "population": s.get("population"),
        "abs_growth_rate": s.get("abs_growth_rate"),
        "is_tier1": s.get("is_tier1", True),
        "scrape_tier": s.get("scrape_tier") or None,
        "domain_slug": s.get("domain_slug") or None,
        "data_thin": s.get("data_thin", False),
        "median_house_price": s.get("median_house_price"),
    }


def bulk_upsert(dry_run: bool = False) -> dict:
    """
    Load geography_trinity.json and upsert all suburbs into Supabase.

    Returns a summary dict: {total, upserted, errors}
    """
    if not TRINITY_PATH.exists():
        raise FileNotFoundError(
            f"geography_trinity.json not found at {TRINITY_PATH}\n"
            "Run: python -m plugins.scrapers.geography_builder"
        )

    suburbs = json.loads(TRINITY_PATH.read_text())
    rows = [_suburb_row(s) for s in suburbs]
    total = len(rows)
    logger.info("Supabase upsert: %d suburbs to load", total)

    if dry_run:
        logger.info("DRY RUN — no data written")
        print(f"Dry run: would upsert {total} rows in {total // BATCH_SIZE + 1} batches")
        print("Sample row:", json.dumps(rows[0], indent=2))
        return {"total": total, "upserted": 0, "errors": 0, "dry_run": True}

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env or environment"
        )

    from supabase import create_client
    client = create_client(url, key)

    upserted = 0
    errors = 0

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Batch %d/%d (%d rows)...", batch_num, total_batches, len(batch))

        try:
            result = (
                client.table("suburbs")
                .upsert(batch, on_conflict="suburb_name,state")
                .execute()
            )
            upserted += len(batch)
            logger.info("Batch %d/%d OK", batch_num, total_batches)
        except Exception as exc:
            logger.error("Batch %d/%d FAILED: %s", batch_num, total_batches, exc)
            errors += len(batch)

    summary = {"total": total, "upserted": upserted, "errors": errors}
    logger.info("Supabase upsert complete: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse
    parser = argparse.ArgumentParser(description="Bulk upsert suburbs into Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Print sample without writing")
    args = parser.parse_args()

    result = bulk_upsert(dry_run=args.dry_run)
    print(f"\nResult: {result}")
    sys.exit(0 if result.get("errors", 0) == 0 else 1)
