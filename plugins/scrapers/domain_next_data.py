"""
Domain __NEXT_DATA__ Scraper — QLD / WA / NT / TAS / ACT

Scrapes Domain suburb profile pages using curl-cffi (Chrome TLS impersonation)
to bypass Akamai JA3/JA4 fingerprinting. Extracts suburb signals from the
__NEXT_DATA__ JSON block embedded in each page.

Why curl-cffi:
  Akamai (Domain's WAF) uses TLS fingerprinting as its primary detection
  vector. Standard requests expose a non-browser TLS signature and are
  blocked. curl-cffi impersonates real Chrome TLS handshakes at the library
  level — free, lightweight, no full browser required.

States covered: QLD, WA, NT, TAS, ACT only.
  NSW, VIC, SA use Valuer General bulk data (more reliable, no scraping risk).

Fields extracted per suburb (from __NEXT_DATA__, propertyCategory: "House"):
  medianSoldPrice, numberSold, daysOnMarket, auctionClearanceRate,
  salesGrowthList (year-on-year history)

From statistics:
  ownerOccupierPercentage, renterPercentage, population

Rate limiting:
  50–80 requests/day — enforced via randomised 3–8 second delays.
  Not bulletproof — monitor block rate, alert if >20%.

Usage:
  # Scrape a single suburb:
  python -m plugins.scrapers.domain_next_data --suburb "paddington-4064-qld"

  # Scrape a batch from the queue:
  python -m plugins.scrapers.domain_next_data --batch 50

  # Scrape all tier1 suburbs for a state:
  python -m plugins.scrapers.domain_next_data --state QLD --batch 50
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import curl_cffi.requests as cffi_requests

from plugins.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
OUTPUT_DIR = ROOT / "data" / "raw" / "domain"
OUTPUT_PATH = ROOT / "data" / "raw" / "domain_signals.json"
BLOCK_LOG_PATH = ROOT / "data" / "raw" / "domain_block_log.json"

_DOMAIN_BASE = "https://www.domain.com.au/suburb-profile/"
_DOMAIN_STATES = {"QLD", "WA", "NT", "TAS", "ACT"}

# Rate limiting
_MIN_DELAY = 3.0   # seconds between requests
_MAX_DELAY = 8.0
_DAILY_MAX = 80    # hard cap — never exceed this in a single run

# Block detection
_BLOCK_RATE_ALERT = 0.20   # alert if >20% of requests are blocked


class DomainNextData(BaseScraper):
    source_name = "DOMAIN"

    def __init__(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self, slugs: list[str] | None = None) -> list[dict]:
        """
        Scrape a list of domain slugs (e.g. ["paddington-4064-qld", ...]).
        If slugs is None, loads from the scrape queue (geography_trinity.json,
        ordered by scrape_tier: Hot first).
        """
        logger.info("DomainNextData: starting run")
        error = None
        results: list[dict] = []

        try:
            if slugs is None:
                slugs = self._load_queue()

            if not slugs:
                logger.info("Scrape queue is empty — nothing to do")
                return []

            # Enforce daily cap
            if len(slugs) > _DAILY_MAX:
                logger.warning(
                    "Queue has %d slugs — capping at %d (daily limit)",
                    len(slugs),
                    _DAILY_MAX,
                )
                slugs = slugs[:_DAILY_MAX]

            results, true_blocks, no_data = self._scrape_batch(slugs)

            # Block rate = true WAF blocks only (403/429/network errors)
            # "No house data" returns are NOT blocks — they're legitimate empty suburbs
            block_rate = true_blocks / len(slugs) if slugs else 0
            if block_rate > _BLOCK_RATE_ALERT:
                logger.warning(
                    "TRUE block rate %.0f%% exceeds threshold %.0f%% — "
                    "consider pausing Domain scraping",
                    block_rate * 100,
                    _BLOCK_RATE_ALERT * 100,
                )

            self._save(results)
            logger.info(
                "Domain: %d scraped, %d no-house-data, %d true-blocks (%.0f%% block rate)",
                len(results),
                no_data,
                true_blocks,
                block_rate * 100,
            )
        except Exception as exc:
            error = str(exc)
            logger.error("DomainNextData failed: %s", exc)
            raise
        finally:
            self.log_run(records_processed=len(results), error=error)

        return results

    # ------------------------------------------------------------------
    # Scrape batch
    # ------------------------------------------------------------------
    _NO_DATA_SENTINEL = object()  # Returned when page loads fine but has no house data

    def _scrape_batch(self, slugs: list[str]) -> tuple[list[dict], int, int]:
        """
        Returns (results, true_blocks, no_data_count).
          true_blocks  — HTTP 403/429/network errors (genuine WAF blocks)
          no_data_count — page returned 200 but had no house data (legitimate, not a block)
        """
        results = []
        true_blocks = 0
        no_data = 0

        for i, slug in enumerate(slugs):
            logger.info("[%d/%d] Scraping: %s", i + 1, len(slugs), slug)
            record = self._scrape_suburb(slug)

            if record is self._NO_DATA_SENTINEL:
                no_data += 1  # legitimate empty — don't log as block
            elif record is None:
                true_blocks += 1
                self._log_block(slug)
            else:
                results.append(record)

            # Rate limiting — randomised delay between requests
            if i < len(slugs) - 1:
                delay = random.uniform(_MIN_DELAY, _MAX_DELAY)
                logger.debug("Sleeping %.1fs", delay)
                time.sleep(delay)

        return results, true_blocks, no_data

    # ------------------------------------------------------------------
    # Scrape a single suburb
    # ------------------------------------------------------------------
    def _scrape_suburb(self, slug: str) -> dict | None:
        """
        Fetch the Domain suburb profile page and extract __NEXT_DATA__.
        Returns a signal record dict, or None if blocked/failed.
        """
        url = _DOMAIN_BASE + slug
        try:
            resp = cffi_requests.get(
                url,
                impersonate="chrome110",
                timeout=20,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-AU,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Cache-Control": "no-cache",
                },
            )
        except Exception as exc:
            logger.warning("Request error for %s: %s", slug, exc)
            return None

        if resp.status_code == 403 or resp.status_code == 429:
            logger.warning("Blocked (%d) for %s", resp.status_code, slug)
            return None  # True WAF block

        if resp.status_code != 200:
            logger.warning("Unexpected status %d for %s", resp.status_code, slug)
            return None  # Treat non-200 as true block

        return self._extract(slug, resp.text)

    # ------------------------------------------------------------------
    # Extract __NEXT_DATA__ from page HTML
    # ------------------------------------------------------------------
    def _extract(self, slug: str, html: str) -> dict | None:
        """
        Parse __NEXT_DATA__ from page HTML and extract house-specific fields.

        Domain uses Apollo GraphQL client-side caching. The suburb data lives in
        __APOLLO_STATE__ under two keys:
          - LocationProfile:{id}  — propertyCategories (per-bedroom price/volume data)
          - Suburb:{base64}       — statistics (owner-occupier %, population, etc.)

        propertyCategories has one entry per bedroom count (2-bed, 3-bed, 4-bed etc.)
        — there is no aggregate "all bedrooms" entry.
        Aggregation strategy:
          - number_sold      = sum across all House bedroom entries
          - median_sold_price / days_on_market / etc. = entry with highest number_sold
            (dominant bedroom count = most representative price signal)
        """
        import re as _re

        match = _re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            _re.DOTALL,
        )
        if not match:
            logger.warning("__NEXT_DATA__ not found on page: %s", slug)
            return None  # Structural failure — treat as block

        try:
            raw = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error for %s: %s", slug, exc)
            return None

        apollo = _dig(raw, ["props", "pageProps", "__APOLLO_STATE__"])
        if not apollo:
            logger.warning("__APOLLO_STATE__ not found for %s", slug)
            return None

        # LocationProfile — price/volume data
        lp_key = next((k for k in apollo if k.startswith("LocationProfile:")), None)
        if not lp_key:
            logger.warning("LocationProfile not found for %s", slug)
            return None

        property_categories = _dig(apollo[lp_key], ["data", "propertyCategories"]) or []
        house_entries = [
            c for c in property_categories
            if c.get("propertyCategory", "").lower() == "house"
            and (_safe_int(c.get("numberSold")) or 0) > 0
        ]

        if not house_entries:
            logger.info("No house data for %s (possibly no houses or no recent sales)", slug)
            return DomainNextData._NO_DATA_SENTINEL  # Legitimate empty — not a WAF block

        # Aggregate: sum sales, use dominant bedroom count for price signals
        total_sold = sum(_safe_int(c.get("numberSold")) or 0 for c in house_entries)
        dominant = max(house_entries, key=lambda c: _safe_int(c.get("numberSold")) or 0)

        # Suburb statistics (owner-occupier %, population)
        suburb_key = next((k for k in apollo if k.startswith("Suburb:")), None)
        statistics = _dig(apollo, [suburb_key, "statistics"]) if suburb_key else {}
        statistics = statistics or {}

        record = {
            "slug": slug,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            # Scored signals
            "median_sold_price": _safe_float(dominant.get("medianSoldPrice")),
            "number_sold": total_sold,                         # aggregate across all bedroom counts
            "dominant_bedrooms": _safe_int(dominant.get("bedrooms")),
            "sales_growth_list": dominant.get("salesGrowthList", []),
            # Scrape tier reclassification
            "days_on_market": _safe_int(dominant.get("daysOnMarket")),
            # Context layer (display only)
            "auction_clearance_rate": _safe_float(dominant.get("auctionClearanceRate")),
            "owner_occupier_pct": _safe_float(statistics.get("ownerOccupierPercentage")),
            "renter_pct": _safe_float(statistics.get("renterPercentage")),
            "population": _safe_int(statistics.get("population")),
            # Derived flags
            "data_thin": total_sold < 12,
            "above_price_ceiling": (_safe_float(dominant.get("medianSoldPrice")) or 0) > 800_000,
            # Red flag alerts
            "red_flag_owner_occupier": (
                (_safe_float(statistics.get("ownerOccupierPercentage")) or 1.0) < 0.70
            ),
            "red_flag_renter_concentration": (
                (_safe_float(statistics.get("renterPercentage")) or 0.0) > 0.50
            ),
        }

        return record

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------
    def _load_queue(
        self,
        state_filter: str | None = None,
        limit: int = _DAILY_MAX,
    ) -> list[str]:
        """
        Load domain_slugs from geography_trinity.json ordered by scrape tier.
        Hot > Warm > Cold > unclassified.
        """
        trinity_path = ROOT / "data" / "raw" / "geography_trinity.json"
        if not trinity_path.exists():
            logger.warning("geography_trinity.json not found — run geography_builder first")
            return []

        suburbs = json.loads(trinity_path.read_text())

        tier_order = {"Hot": 0, "Warm": 1, "Cold": 2, None: 3}
        domain_states = {state_filter} if state_filter else _DOMAIN_STATES

        candidates = [
            s for s in suburbs
            if s.get("state", "").upper() in domain_states
            and s.get("domain_slug")
        ]

        candidates.sort(key=lambda s: tier_order.get(s.get("scrape_tier"), 3))
        slugs = [s["domain_slug"] for s in candidates[:limit]]

        logger.info(
            "Scrape queue: %d slugs loaded (state=%s, limit=%d)",
            len(slugs),
            state_filter or "all",
            limit,
        )
        return slugs

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    def _save(self, records: list[dict]) -> None:
        """Append results to domain_signals.json (keyed by slug, latest wins)."""
        existing: dict[str, dict] = {}
        if OUTPUT_PATH.exists():
            try:
                for r in json.loads(OUTPUT_PATH.read_text()):
                    existing[r["slug"]] = r
            except (json.JSONDecodeError, KeyError):
                pass

        for r in records:
            existing[r["slug"]] = r

        OUTPUT_PATH.write_text(json.dumps(list(existing.values()), indent=2, default=str))

    def _log_block(self, slug: str) -> None:
        """Append a block event to domain_block_log.json."""
        entry = {"slug": slug, "blocked_at": datetime.now(timezone.utc).isoformat()}
        existing = []
        if BLOCK_LOG_PATH.exists():
            try:
                existing = json.loads(BLOCK_LOG_PATH.read_text())
            except json.JSONDecodeError:
                pass
        existing.append(entry)
        BLOCK_LOG_PATH.write_text(json.dumps(existing, indent=2))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dig(obj: Any, path: list[str]) -> Any:
    """Safely navigate nested dicts/lists."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Domain __NEXT_DATA__ scraper")
    parser.add_argument("--suburb", help="Single slug, e.g. paddington-4064-qld")
    parser.add_argument("--state", help="State filter, e.g. QLD")
    parser.add_argument("--batch", type=int, default=10, help="Max suburbs to scrape")
    args = parser.parse_args()

    scraper = DomainNextData()

    if args.suburb:
        result = scraper._scrape_suburb(args.suburb)
        print(json.dumps(result, indent=2))
    else:
        queue = scraper._load_queue(state_filter=args.state, limit=args.batch)
        results = scraper.run(slugs=queue)
        print(f"\nDone. {len(results)} suburbs scraped → {OUTPUT_PATH}")

    sys.exit(0)
