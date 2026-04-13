"""
NSW Valuer General — Property Sales Information (PPSR) Ingestor

Parses the weekly bulk sales data files published by NSW Land Registry Services.
Extracts standalone house sales volume and median price per suburb per quarter.

Data source (free, no API key):
  https://valuation.property.nsw.gov.au/embed/propertySalesInformation

Download format: ZIP containing multiple semicolon-delimited .DAT files, one per
LGA district. Each file has two record types interleaved:
  A record (district header):
    A;DISTRICT_CODE;FILE_DATE;DESCRIPTION
  B record (sale entry):
    B;DISTRICT_CODE;PROPERTY_ID;SALE_COUNTER;DOWNLOAD_DATE;SALE_DATE;PURCHASE_PRICE;
    LAND_DESCRIPTION;AREA;AREA_TYPE;CONTRACT_DATE;SETTLEMENT_DATE;PROPERTY_NAME;
    UNIT_NUMBER;HOUSE_NUMBER;STREET_NAME;LOCALITY;POST_CODE;NATURE_OF_PROPERTY;
    PRIMARY_PURPOSE;STRATA_LOT_NUMBER;COMPONENT_CODE;SALE_CODE;INTEREST_OF_SALE;
    DEALING_NUMBER

Standalone house filter (applied to B records):
  - NATURE_OF_PROPERTY == 'R' (residential)
  - STRATA_LOT_NUMBER is empty  (no strata = freestanding house or Torrens-title)
  - PURCHASE_PRICE > 0          (exclude $0 transfers/gifts)

Output: data/raw/nsw_vg_signals.json
  [{suburb_name, state, postcode, quarter, house_count, median_price}, ...]

Manual download steps:
  1. Go to: https://valuation.property.nsw.gov.au/embed/propertySalesInformation
  2. Select date range (suggest: last 12 months for initial load)
  3. Download the ZIP file
  4. Place the ZIP (or extracted .DAT files) at: data/raw/nsw/
  5. Run: python -m plugins.scrapers.nsw_valuer_general
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import date
from pathlib import Path
from statistics import median
from typing import Generator

import pandas as pd
import yaml

from plugins.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "config.yaml"
INPUT_DIR = ROOT / "data" / "raw" / "nsw"
OUTPUT_PATH = ROOT / "data" / "raw" / "nsw_vg_signals.json"

# B record field positions (0-indexed, semicolon-delimited)
_B_FIELDS = {
    "record_type":        0,
    "district_code":      1,
    "property_id":        2,
    "sale_counter":       3,
    "download_date":      4,
    "sale_date":          5,
    "purchase_price":     6,
    "land_description":   7,
    "area":               8,
    "area_type":          9,
    "contract_date":      10,
    "settlement_date":    11,
    "property_name":      12,
    "unit_number":        13,
    "house_number":       14,
    "street_name":        15,
    "locality":           16,
    "post_code":          17,
    "nature_of_property": 18,
    "primary_purpose":    19,
    "strata_lot_number":  20,
    "component_code":     21,
    "sale_code":          22,
    "interest_of_sale":   23,
    "dealing_number":     24,
}


class NswValuerGeneral(BaseScraper):
    source_name = "NSW_VALUER_GENERAL"

    _MANUAL_INSTRUCTIONS = """
NSW Valuer General data not found.

1. Go to: https://valuation.property.nsw.gov.au/embed/propertySalesInformation
2. Select date range — suggest last 12 months for initial load.
3. Download the ZIP file.
4. Place the ZIP file (or extracted .DAT files) at: data/raw/nsw/
5. Re-run: python -m plugins.scrapers.nsw_valuer_general
""".strip()

    def __init__(self) -> None:
        INPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self) -> list[dict]:
        logger.info("NswValuerGeneral: starting run")
        error = None
        records: list[dict] = []

        try:
            tier1 = self._load_tier1_suburbs()
            rows = list(self._parse_all_dat_files())

            if not rows:
                raise FileNotFoundError(self._MANUAL_INSTRUCTIONS)

            df = pd.DataFrame(rows)
            records = self._aggregate(df, tier1)
            self._save(records)
            logger.info(
                "NSW VG: %d suburb-quarter records → %s", len(records), OUTPUT_PATH
            )
        except Exception as exc:
            error = str(exc)
            logger.error("NswValuerGeneral failed: %s", exc)
            raise
        finally:
            self.log_run(records_processed=len(records), error=error)

        return records

    # ------------------------------------------------------------------
    # Parse all .DAT files in INPUT_DIR (ZIP or raw)
    # ------------------------------------------------------------------
    def _parse_all_dat_files(self) -> Generator[dict, None, None]:
        """Yield one dict per qualifying sale row across all source files."""
        sources = list(INPUT_DIR.glob("*.zip")) + list(INPUT_DIR.glob("*.ZIP"))

        if sources:
            for zip_path in sources:
                logger.info("Reading ZIP: %s", zip_path.name)
                with zipfile.ZipFile(zip_path) as zf:
                    dat_names = [n for n in zf.namelist() if n.upper().endswith(".DAT")]
                    for name in dat_names:
                        with zf.open(name) as f:
                            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
                            yield from self._parse_dat(text, source=name)
        else:
            for dat_path in INPUT_DIR.glob("*.DAT"):
                with open(dat_path, encoding="utf-8", errors="replace") as f:
                    yield from self._parse_dat(f, source=dat_path.name)

    def _parse_dat(self, lines, source: str) -> Generator[dict, None, None]:
        """Parse a single .DAT file stream, yielding qualifying sale rows."""
        for raw_line in lines:
            line = raw_line.strip()
            if not line or not line.startswith("B;"):
                continue

            parts = line.split(";")
            if len(parts) < 21:
                continue

            def field(name: str) -> str:
                idx = _B_FIELDS.get(name, -1)
                return parts[idx].strip() if 0 <= idx < len(parts) else ""

            # Standalone house filter
            if field("nature_of_property").upper() != "R":
                continue
            if field("strata_lot_number"):  # non-empty = strata unit
                continue

            price_str = field("purchase_price")
            try:
                price = float(price_str)
            except ValueError:
                continue
            if price <= 0:
                continue

            sale_date_str = field("sale_date")
            quarter = _date_to_quarter(sale_date_str)
            if not quarter:
                continue

            yield {
                "suburb_name": field("locality").title(),
                "postcode": field("post_code"),
                "sale_price": price,
                "quarter": quarter,
                "source_file": source,
            }

    # ------------------------------------------------------------------
    # Aggregate to suburb-quarter signals
    # ------------------------------------------------------------------
    def _aggregate(self, df: pd.DataFrame, tier1: set[str]) -> list[dict]:
        """
        Group sales by (suburb_name, postcode, quarter).
        Only return suburbs present in the tier1 set.
        Applies $800k median filter — marks ineligible suburbs.
        """
        results = []
        for (suburb, postcode, quarter), group in df.groupby(
            ["suburb_name", "postcode", "quarter"]
        ):
            suburb_key = suburb.upper()
            if tier1 and suburb_key not in tier1:
                continue

            prices = sorted(group["sale_price"].tolist())
            house_count = len(prices)
            med_price = median(prices)

            results.append({
                "suburb_name": suburb,
                "state": "NSW",
                "postcode": postcode,
                "quarter": quarter,
                "house_count": house_count,
                "median_price": med_price,
                "data_thin": house_count < 3,        # < 3 sales in a single quarter is thin
                "above_price_ceiling": med_price > 800_000,
            })

        return sorted(results, key=lambda r: (r["suburb_name"], r["quarter"]))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_tier1_suburbs(self) -> set[str]:
        """Return set of uppercased suburb names from Geography Trinity (or tier1 fallback)."""
        trinity = ROOT / "data" / "raw" / "geography_trinity.json"
        tier1 = ROOT / "data" / "raw" / "tier1_candidates.json"

        for path in (trinity, tier1):
            if path.exists():
                data = json.loads(path.read_text())
                name_key = "suburb_name" if path == trinity else "name"
                nsw = {
                    r[name_key].upper()
                    for r in data
                    if r.get("state", "").upper() == "NSW"
                }
                logger.info("Tier 1 NSW suburbs loaded: %d (from %s)", len(nsw), path.name)
                return nsw

        logger.warning("No tier1 file found — processing all NSW suburbs")
        return set()

    def _save(self, records: list[dict]) -> None:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(records, indent=2, default=str))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _date_to_quarter(date_str: str) -> str | None:
    """
    Convert a sale date string (DD/MM/YYYY or YYYYMMDD) to ISO quarter string.
    Returns e.g. "2024-Q3" or None if unparseable.
    """
    date_str = date_str.strip()
    try:
        if len(date_str) == 10 and "/" in date_str:
            d = date.fromisoformat(date_str[6:] + "-" + date_str[3:5] + "-" + date_str[:2])
        elif len(date_str) == 8 and date_str.isdigit():
            d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        else:
            return None
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-Q{q}"
    except (ValueError, IndexError):
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
    ingestor = NswValuerGeneral()
    results = ingestor.run()
    print(f"\nDone. {len(results)} suburb-quarter records → {OUTPUT_PATH}")
    sys.exit(0)
