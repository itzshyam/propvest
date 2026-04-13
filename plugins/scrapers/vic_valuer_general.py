"""
VIC Valuer General — Data.Vic Victorian Property Sales Report (VPSR) Ingestor

Parses the quarterly CSV published on the Victorian government open data portal.
Extracts standalone house sales volume and median price per suburb per quarter.

Data source (free, no API key, open licence):
  https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics

File: "Property Sales Statistics — All Years" CSV (one large file, updated quarterly)
  OR: Individual quarterly Excel files

Known column layout (VIC VPSR as at 2024):
  Property Type, Municipality, Locality (suburb), Postcode, Sale Price,
  Contract Date, Settlement Date, Property Count, Median Sale Price (pre-aggregated)

VIC publishes TWO formats:
  A. Detailed records CSV (one row per sale) — preferred, allows our own aggregation
  B. Pre-aggregated quarterly summary — use if detailed not available

Standalone house filter:
  - Property Type contains 'HOUSE' or == 'RES' (residential, non-strata)
  - NOT Unit/Apartment/Townhouse/Villa

Output: data/raw/vic_vg_signals.json
  [{suburb_name, state, postcode, quarter, house_count, median_price}, ...]

Manual download steps:
  1. Go to: https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics
  2. Download "Property Sales Statistics" (choose CSV format where available)
  3. Save to: data/raw/vic/
  4. Run: python -m plugins.scrapers.vic_valuer_general
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import median

import pandas as pd

from plugins.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
INPUT_DIR = ROOT / "data" / "raw" / "vic"
OUTPUT_PATH = ROOT / "data" / "raw" / "vic_vg_signals.json"

# Candidate column names — VIC has changed its column naming across releases
_SUBURB_COLS    = ["LOCALITY", "SUBURB", "SUBURB_NAME"]
_POSTCODE_COLS  = ["POSTCODE", "POST_CODE", "PCODE"]
_PRICE_COLS     = ["SALE_PRICE", "PRICE", "PURCHASEPRICE", "CONTRACT_PRICE"]
_TYPE_COLS      = ["PROPERTY_TYPE", "PROPERTYTYPE", "TYPE", "PROPERTY TYPE"]
_DATE_COLS      = ["CONTRACT_DATE", "CONTRACTDATE", "SALE_DATE", "SETTLEMENT_DATE"]
_COUNT_COLS     = ["PROPERTY_COUNT", "COUNT", "NUMBER_OF_SALES"]         # for pre-agg format
_MEDIAN_COLS    = ["MEDIAN_SALE_PRICE", "MEDIAN_PRICE", "MEDIANPRICE"]   # for pre-agg format

# House type keywords (case-insensitive match in property type field)
_HOUSE_KEYWORDS = {"HOUSE", "RESIDENTIAL", "RES"}
_EXCLUDE_KEYWORDS = {"UNIT", "APARTMENT", "APT", "VILLA", "TOWNHOUSE", "STRATA", "FLAT"}


class VicValuerGeneral(BaseScraper):
    source_name = "VIC_VALUER_GENERAL"

    _MANUAL_INSTRUCTIONS = """
VIC Valuer General data not found.

1. Go to: https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics
2. Download "Property Sales Statistics" CSV or Excel.
3. Save to: data/raw/vic/
4. Re-run: python -m plugins.scrapers.vic_valuer_general
""".strip()

    def __init__(self) -> None:
        INPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self) -> list[dict]:
        logger.info("VicValuerGeneral: starting run")
        error = None
        records: list[dict] = []

        try:
            tier1 = self._load_tier1_suburbs()
            df = self._load_input()
            records = self._aggregate(df, tier1)
            self._save(records)
            logger.info(
                "VIC VG: %d suburb-quarter records → %s", len(records), OUTPUT_PATH
            )
        except Exception as exc:
            error = str(exc)
            logger.error("VicValuerGeneral failed: %s", exc)
            raise
        finally:
            self.log_run(records_processed=len(records), error=error)

        return records

    # ------------------------------------------------------------------
    # Load + normalise input
    # ------------------------------------------------------------------
    def _load_input(self) -> pd.DataFrame:
        """Load CSV or Excel from INPUT_DIR. Returns normalised DataFrame."""
        files = (
            list(INPUT_DIR.glob("*.csv"))
            + list(INPUT_DIR.glob("*.CSV"))
            + list(INPUT_DIR.glob("*.xlsx"))
            + list(INPUT_DIR.glob("*.xls"))
        )

        if not files:
            raise FileNotFoundError(self._MANUAL_INSTRUCTIONS)

        # Use the largest file if multiple present (most complete dataset)
        source = max(files, key=lambda p: p.stat().st_size)
        logger.info("Loading VIC VG data: %s", source.name)

        if source.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(source, dtype=str)
        else:
            df = pd.read_csv(source, dtype=str, low_memory=False)

        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
        logger.info("Loaded %d rows, columns: %s", len(df), list(df.columns))
        return df

    # ------------------------------------------------------------------
    # Aggregate to suburb-quarter signals
    # ------------------------------------------------------------------
    def _aggregate(self, df: pd.DataFrame, tier1: set[str]) -> list[dict]:
        suburb_col   = _find_col(df, _SUBURB_COLS)
        postcode_col = _find_col(df, _POSTCODE_COLS, required=False)
        type_col     = _find_col(df, _TYPE_COLS, required=False)
        date_col     = _find_col(df, _DATE_COLS)

        # Detect format: detailed (one row per sale) vs pre-aggregated
        price_col   = _find_col(df, _PRICE_COLS, required=False)
        count_col   = _find_col(df, _COUNT_COLS, required=False)
        median_col  = _find_col(df, _MEDIAN_COLS, required=False)

        is_preagg = price_col is None and count_col is not None and median_col is not None

        # Apply house type filter
        if type_col:
            type_upper = df[type_col].str.upper().str.strip()
            house_mask = type_upper.apply(_is_house_type)
            df = df[house_mask].copy()
            logger.info("After house filter: %d rows", len(df))
        else:
            logger.warning("No property type column found — including all property types")

        # Parse quarter
        df["quarter"] = df[date_col].apply(_date_to_quarter)
        df = df[df["quarter"].notna()].copy()

        # Normalise suburb name
        df["suburb_norm"] = df[suburb_col].str.strip().str.title()
        postcode_series = df[postcode_col].str.strip() if postcode_col else pd.Series([""] * len(df))

        results = []

        if is_preagg:
            # Pre-aggregated: count + median already in source
            df[count_col] = pd.to_numeric(df[count_col], errors="coerce")
            df[median_col] = pd.to_numeric(df[median_col], errors="coerce")
            for (suburb, postcode, quarter), group in df.groupby(
                ["suburb_norm", postcode_series.rename("pc"), "quarter"]
            ):
                if tier1 and suburb.upper() not in tier1:
                    continue
                house_count = int(group[count_col].sum())
                med_price = float(group[median_col].median())
                results.append(_make_record(suburb, "VIC", str(postcode), quarter, house_count, med_price))
        else:
            # Detailed: aggregate ourselves
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
            df = df[df[price_col] > 0].copy()
            df["_postcode"] = postcode_series.values
            for (suburb, postcode, quarter), group in df.groupby(
                ["suburb_norm", "_postcode", "quarter"]
            ):
                if tier1 and suburb.upper() not in tier1:
                    continue
                prices = sorted(group[price_col].dropna().tolist())
                if not prices:
                    continue
                results.append(_make_record(suburb, "VIC", str(postcode), quarter, len(prices), median(prices)))

        return sorted(results, key=lambda r: (r["suburb_name"], r["quarter"]))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_tier1_suburbs(self) -> set[str]:
        trinity = ROOT / "data" / "raw" / "geography_trinity.json"
        tier1 = ROOT / "data" / "raw" / "tier1_candidates.json"
        for path in (trinity, tier1):
            if path.exists():
                data = json.loads(path.read_text())
                name_key = "suburb_name" if "geography" in path.name else "name"
                vic = {r[name_key].upper() for r in data if r.get("state", "").upper() == "VIC"}
                logger.info("Tier 1 VIC suburbs: %d (from %s)", len(vic), path.name)
                return vic
        logger.warning("No tier1 file — processing all VIC suburbs")
        return set()

    def _save(self, records: list[dict]) -> None:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(records, indent=2, default=str))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _find_col(df: pd.DataFrame, candidates: list[str], required: bool = True) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    if not required:
        return None
    raise ValueError(
        f"Could not find any of {candidates} in columns: {list(df.columns)}. "
        "VIC VG may have updated its column names."
    )


def _is_house_type(value: str) -> bool:
    val = str(value).upper().strip()
    if any(kw in val for kw in _EXCLUDE_KEYWORDS):
        return False
    if any(kw in val for kw in _HOUSE_KEYWORDS):
        return True
    # If type is ambiguous, exclude — better to miss than to include non-houses
    return False


def _date_to_quarter(date_str: str) -> str | None:
    from datetime import date as date_cls
    date_str = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            import datetime
            d = datetime.datetime.strptime(date_str, fmt).date()
            q = (d.month - 1) // 3 + 1
            return f"{d.year}-Q{q}"
        except ValueError:
            continue
    return None


def _make_record(
    suburb: str, state: str, postcode: str, quarter: str, count: int, med: float
) -> dict:
    return {
        "suburb_name": suburb,
        "state": state,
        "postcode": postcode,
        "quarter": quarter,
        "house_count": count,
        "median_price": round(med, 2),
        "data_thin": count < 3,
        "above_price_ceiling": med > 800_000,
    }


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    ingestor = VicValuerGeneral()
    results = ingestor.run()
    print(f"\nDone. {len(results)} suburb-quarter records → {OUTPUT_PATH}")
    sys.exit(0)
