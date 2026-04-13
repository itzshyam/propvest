"""
SQM Research Scraper — Vacancy Rate + Stock on Market (National)

Scrapes SQM Research suburb-level data using curl-cffi (Chrome TLS impersonation).
Covers all Australian suburbs nationally — SQM is indexed by postcode.

Signals extracted:
  - Vacancy rate (%) — strongest scored signal (25% weight)
  - Stock on market (count) — supply constraint signal (20% weight)

SQM URL structure (suburb vacancy/listings):
  https://sqmresearch.com.au/graph_vacancy.php?postcode={postcode}&t=1

Data is served as embedded JavaScript data arrays in the HTML — not JSON.
We parse the JS arrays using regex.

Rate limiting:
  Same conservative approach as Domain: randomised 3–8s delays.
  SQM is less aggressive than Domain but respect the site.

Postcode dependency:
  SQM is looked up by postcode. If geography_trinity.json has no postcodes
  (e.g. ABS POA concordance wasn't available), the scraper will skip those
  suburbs and log a warning. Postcodes can be manually enriched later.

Output: data/raw/sqm_signals.json
  [{postcode, suburb_name, state, vacancy_rate, stock_on_market, scraped_at}, ...]

Usage:
  # Scrape all tier1 postcodes (up to daily cap)
  python -m plugins.scrapers.sqm_scraper

  # Scrape a specific postcode
  python -m plugins.scrapers.sqm_scraper --postcode 4064
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import curl_cffi.requests as cffi_requests

from plugins.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
OUTPUT_PATH = ROOT / "data" / "raw" / "sqm_signals.json"

_SQM_VACANCY_URL = "https://sqmresearch.com.au/graph_vacancy.php?postcode={postcode}&t=1"
_SQM_LISTINGS_URL = "https://sqmresearch.com.au/graph_listings.php?postcode={postcode}&t=1"

_MIN_DELAY = 3.0
_MAX_DELAY = 8.0
_DAILY_MAX = 80

_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://sqmresearch.com.au/",
    "Cache-Control": "no-cache",
}


class SqmScraper(BaseScraper):
    source_name = "SQM"

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self, postcodes: list[str] | None = None) -> list[dict]:
        logger.info("SqmScraper: starting run")
        error = None
        results: list[dict] = []

        try:
            if postcodes is None:
                postcodes = self._load_queue()

            if not postcodes:
                logger.info("No postcodes to scrape — check geography_trinity has postcodes populated")
                return []

            if len(postcodes) > _DAILY_MAX:
                logger.warning("Capping queue at %d (daily limit)", _DAILY_MAX)
                postcodes = postcodes[:_DAILY_MAX]

            results = self._scrape_batch(postcodes)
            self._save(results)
            logger.info("SQM: %d postcodes scraped → %s", len(results), OUTPUT_PATH)

        except Exception as exc:
            error = str(exc)
            logger.error("SqmScraper failed: %s", exc)
            raise
        finally:
            self.log_run(records_processed=len(results), error=error)

        return results

    # ------------------------------------------------------------------
    # Scrape batch
    # ------------------------------------------------------------------
    def _scrape_batch(self, postcodes: list[str]) -> list[dict]:
        results = []
        for i, postcode in enumerate(postcodes):
            logger.info("[%d/%d] Scraping SQM postcode: %s", i + 1, len(postcodes), postcode)
            record = self._scrape_postcode(postcode)
            if record:
                results.append(record)

            if i < len(postcodes) - 1:
                delay = random.uniform(_MIN_DELAY, _MAX_DELAY)
                time.sleep(delay)

        return results

    # ------------------------------------------------------------------
    # Scrape a single postcode
    # ------------------------------------------------------------------
    def _scrape_postcode(self, postcode: str) -> dict | None:
        vacancy_rate = self._fetch_vacancy(postcode)
        stock = self._fetch_stock(postcode)

        if vacancy_rate is None and stock is None:
            logger.warning("No data retrieved for postcode %s", postcode)
            return None

        return {
            "postcode": postcode,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "vacancy_rate": vacancy_rate,
            "stock_on_market": stock,
        }

    def _fetch_vacancy(self, postcode: str) -> float | None:
        """Fetch vacancy rate % for a postcode from SQM Research."""
        url = _SQM_VACANCY_URL.format(postcode=postcode)
        html = self._get(url)
        if not html:
            return None
        return self._parse_latest_value(html, signal="vacancy")

    def _fetch_stock(self, postcode: str) -> int | None:
        """Fetch total stock on market for a postcode from SQM Research."""
        url = _SQM_LISTINGS_URL.format(postcode=postcode)
        html = self._get(url)
        if not html:
            return None
        val = self._parse_latest_value(html, signal="listings")
        return int(val) if val is not None else None

    def _get(self, url: str) -> str | None:
        try:
            resp = cffi_requests.get(
                url,
                impersonate="chrome110",
                timeout=20,
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                logger.warning("SQM returned %d for %s", resp.status_code, url)
                return None
            return resp.text
        except Exception as exc:
            logger.warning("SQM request error: %s — %s", url, exc)
            return None

    def _parse_latest_value(self, html: str, signal: str) -> float | None:
        """
        SQM embeds chart data as JavaScript arrays in the HTML.
        Common patterns:
          data.addRows([[new Date(2024,10,1), 1.2], ...])
          var data = [[...], [...]]

        We extract the most recent (last) numeric value in the data array.
        """
        # Pattern 1: Highcharts / Google Charts style data arrays
        # Looks for sequences like [[..., numeric], [... numeric]]
        arrays = re.findall(r'\[\s*(?:new Date\([^)]+\)\s*,\s*)?([\d.]+)\s*\]', html)
        if arrays:
            try:
                return float(arrays[-1])
            except ValueError:
                pass

        # Pattern 2: JSON array embedded as a variable
        match = re.search(r'data\s*=\s*(\[.*?\])\s*;', html, re.DOTALL)
        if match:
            try:
                rows = json.loads(match.group(1))
                if rows and isinstance(rows[-1], (list, tuple)) and len(rows[-1]) >= 2:
                    return float(rows[-1][-1])
            except (json.JSONDecodeError, ValueError, IndexError):
                pass

        logger.debug("Could not parse %s data from SQM response", signal)
        return None

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------
    def _load_queue(self) -> list[str]:
        """
        Load unique postcodes from geography_trinity.json.
        Tier1 suburbs only, with non-empty postcodes.
        Ordered: Hot tier first (highest scrape priority).
        """
        trinity_path = ROOT / "data" / "raw" / "geography_trinity.json"
        if not trinity_path.exists():
            logger.warning("geography_trinity.json not found")
            return []

        suburbs = json.loads(trinity_path.read_text())

        tier_order = {"Hot": 0, "Warm": 1, "Cold": 2, None: 3}
        suburbs_with_pc = [
            s for s in suburbs
            if s.get("is_tier1") and s.get("postcode", "").strip()
        ]
        suburbs_with_pc.sort(key=lambda s: tier_order.get(s.get("scrape_tier"), 3))

        # Deduplicate by postcode (SQM is postcode-keyed)
        seen: set[str] = set()
        postcodes = []
        for s in suburbs_with_pc:
            pc = s["postcode"].strip()
            if pc not in seen:
                seen.add(pc)
                postcodes.append(pc)

        if not postcodes:
            logger.warning(
                "No postcodes found in geography_trinity.json. "
                "Run geography_builder with POA concordance to populate postcodes."
            )

        logger.info("SQM queue: %d unique postcodes", len(postcodes))
        return postcodes

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    def _save(self, records: list[dict]) -> None:
        """Append/overwrite by postcode (latest wins)."""
        existing: dict[str, dict] = {}
        if OUTPUT_PATH.exists():
            try:
                for r in json.loads(OUTPUT_PATH.read_text()):
                    existing[r["postcode"]] = r
            except (json.JSONDecodeError, KeyError):
                pass

        for r in records:
            existing[r["postcode"]] = r

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(list(existing.values()), indent=2, default=str))


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="SQM Research scraper")
    parser.add_argument("--postcode", help="Single postcode to scrape, e.g. 4064")
    parser.add_argument("--batch", type=int, default=10, help="Max postcodes to scrape")
    args = parser.parse_args()

    scraper = SqmScraper()

    if args.postcode:
        result = scraper._scrape_postcode(args.postcode)
        print(json.dumps(result, indent=2))
    else:
        queue = scraper._load_queue()[:args.batch]
        results = scraper.run(postcodes=queue)
        print(f"\nDone. {len(results)} postcodes scraped → {OUTPUT_PATH}")

    sys.exit(0)
