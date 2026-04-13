"""
SA Valuer General — Property Sales Data Ingestor

Parses the quarterly Excel file published by the SA Land Services Group.
Extracts standalone house sales volume and median price per suburb per quarter.

Data source (free, no registration required):
  https://www.sa.gov.au/topics/planning-and-property/land-and-property-information/property-information

File: Quarterly Excel workbook — "Property Sales Data"
  Typical sheet layout:
    Column A: Suburb
    Column B: Postcode
    Column C: Property Type (House/Unit/Vacant Land/etc.)
    Column D: Sale Date (or Settlement Date)
    Column E: Sale Price
    Column F: Land Area (m²)
    ... (additional columns vary by release)

  Some releases are pre-aggregated by suburb and quarter.

Standalone house filter:
  - Property Type contains 'HOUSE' or 'DWELLING' or 'RESIDENTIAL'
  - Excludes: Unit, Apartment, Flat, Strata, Townhouse, Vacant Land

Output: data/raw/sa_vg_signals.json
  [{suburb_name, state, postcode, quarter, house_count, median_price}, ...]

Manual download steps:
  1. Go to: https://www.sa.gov.au/topics/planning-and-property/land-and-property-information/property-information
     OR: https://data.sa.gov.au (search for "property sales")
  2. Download the latest quarterly Excel workbook.
  3. Save to: data/raw/sa/
  4. Run: python -m plugins.scrapers.sa_valuer_general
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
INPUT_DIR = ROOT / "data" / "raw" / "sa"
OUTPUT_PATH = ROOT / "data" / "raw" / "sa_vg_signals.json"

# Candidate column names — SA format has varied across releases
_SUBURB_COLS    = ["SUBURB", "LOCALITY", "SUBURB_NAME", "LOCATION"]
_POSTCODE_COLS  = ["POSTCODE", "POST_CODE", "PCODE"]
_PRICE_COLS     = ["SALE_PRICE", "PRICE", "SETTLEMENT_PRICE", "CONTRACT_PRICE", "SALEAMOUNT"]
_TYPE_COLS      = ["PROPERTY_TYPE", "TYPE", "PROPERTY TYPE", "PROPERTYTYPE", "CATEGORY"]
_DATE_COLS      = ["SALE_DATE", "SETTLEMENT_DATE", "CONTRACT_DATE", "DATE"]
_COUNT_COLS     = ["COUNT", "NUMBER_OF_SALES", "SALES_COUNT"]
_MEDIAN_COLS    = ["MEDIAN_PRICE", "MEDIAN_SALE_PRICE", "MEDIANPRICE"]

_HOUSE_KEYWORDS     = {"HOUSE", "DWELLING", "RESIDENTIAL", "DETACHED"}
_EXCLUDE_KEYWORDS   = {"UNIT", "APARTMENT", "APT", "FLAT", "STRATA", "TOWNHOUSE",
                       "VILLA", "VACANT", "LAND", "COMMERCIAL", "INDUSTRIAL"}


class SaValuerGeneral(BaseScraper):
    source_name = "SA_VALUER_GENERAL"

    _MANUAL_INSTRUCTIONS = """
SA Valuer General data not found.

1. Go to: https://www.sa.gov.au/topics/planning-and-property/land-and-property-information/property-information
   OR search data.sa.gov.au for "property sales"
2. Download the latest quarterly Excel workbook.
3. Save to: data/raw/sa/
4. Re-run: python -m plugins.scrapers.sa_valuer_general
""".strip()

    def __init__(self) -> None:
        INPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self) -> list[dict]:
        logger.info("SaValuerGeneral: starting run")
        error = None
        records: list[dict] = []

        try:
            tier1 = self._load_tier1_suburbs()
            df = self._load_input()
            records = self._aggregate(df, tier1)
            self._save(records)
            logger.info(
                "SA VG: %d suburb-quarter records → %s", len(records), OUTPUT_PATH
            )
        except Exception as exc:
            error = str(exc)
            logger.error("SaValuerGeneral failed: %s", exc)
            raise
        finally:
            self.log_run(records_processed=len(records), error=error)

        return records

    # ------------------------------------------------------------------
    # Load + normalise input
    # ------------------------------------------------------------------
    def _load_input(self) -> pd.DataFrame:
        files = (
            list(INPUT_DIR.glob("*.xlsx"))
            + list(INPUT_DIR.glob("*.xls"))
            + list(INPUT_DIR.glob("*.csv"))
            + list(INPUT_DIR.glob("*.CSV"))
        )

        if not files:
            raise FileNotFoundError(self._MANUAL_INSTRUCTIONS)

        source = max(files, key=lambda p: p.stat().st_size)
        logger.info("Loading SA VG data: %s", source.name)

        if source.suffix.lower() in (".xlsx", ".xls"):
            # SA Excel often has multiple sheets — use the largest/first data sheet
            xl = pd.ExcelFile(source)
            sheet = self._pick_data_sheet(xl)
            df = pd.read_excel(source, sheet_name=sheet, dtype=str)
        else:
            df = pd.read_csv(source, dtype=str, low_memory=False)

        df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

        # Drop fully empty rows
        df.dropna(how="all", inplace=True)
        logger.info("Loaded %d rows, columns: %s", len(df), list(df.columns))
        return df

    def _pick_data_sheet(self, xl: pd.ExcelFile) -> str:
        """Choose the sheet with the most rows (skip cover/legend sheets)."""
        best, best_count = xl.sheet_names[0], 0
        for name in xl.sheet_names:
            try:
                sample = pd.read_excel(xl, sheet_name=name, nrows=5)
                count = len(pd.read_excel(xl, sheet_name=name))
                if count > best_count:
                    best, best_count = name, count
            except Exception:
                continue
        logger.info("Using sheet: '%s' (%d rows)", best, best_count)
        return best

    # ------------------------------------------------------------------
    # Aggregate to suburb-quarter signals
    # ------------------------------------------------------------------
    def _aggregate(self, df: pd.DataFrame, tier1: set[str]) -> list[dict]:
        suburb_col   = _find_col(df, _SUBURB_COLS)
        postcode_col = _find_col(df, _POSTCODE_COLS, required=False)
        type_col     = _find_col(df, _TYPE_COLS, required=False)
        date_col     = _find_col(df, _DATE_COLS)

        price_col   = _find_col(df, _PRICE_COLS, required=False)
        count_col   = _find_col(df, _COUNT_COLS, required=False)
        median_col  = _find_col(df, _MEDIAN_COLS, required=False)

        is_preagg = price_col is None and count_col is not None and median_col is not None

        # House type filter
        if type_col:
            house_mask = df[type_col].str.upper().str.strip().apply(_is_house_type)
            df = df[house_mask].copy()
            logger.info("After house filter: %d rows", len(df))
        else:
            logger.warning("No property type column — including all types")

        # Quarter
        df["quarter"] = df[date_col].apply(_date_to_quarter)
        df = df[df["quarter"].notna()].copy()

        df["suburb_norm"] = df[suburb_col].str.strip().str.title()
        pc_series = df[postcode_col].str.strip() if postcode_col else pd.Series([""] * len(df), index=df.index)

        results = []

        if is_preagg:
            df[count_col] = pd.to_numeric(df[count_col], errors="coerce")
            df[median_col] = pd.to_numeric(df[median_col], errors="coerce")
            df["_pc"] = pc_series.values
            for (suburb, postcode, quarter), group in df.groupby(["suburb_norm", "_pc", "quarter"]):
                if tier1 and suburb.upper() not in tier1:
                    continue
                house_count = int(group[count_col].sum())
                med_price = float(group[median_col].median())
                results.append(_make_record(suburb, "SA", str(postcode), quarter, house_count, med_price))
        else:
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
            df = df[df[price_col] > 0].copy()
            df["_pc"] = pc_series.values
            for (suburb, postcode, quarter), group in df.groupby(["suburb_norm", "_pc", "quarter"]):
                if tier1 and suburb.upper() not in tier1:
                    continue
                prices = sorted(group[price_col].dropna().tolist())
                if not prices:
                    continue
                results.append(_make_record(suburb, "SA", str(postcode), quarter, len(prices), median(prices)))

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
                sa = {r[name_key].upper() for r in data if r.get("state", "").upper() == "SA"}
                logger.info("Tier 1 SA suburbs: %d (from %s)", len(sa), path.name)
                return sa
        logger.warning("No tier1 file — processing all SA suburbs")
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
        "SA VG may have updated its column names."
    )


def _is_house_type(value: str) -> bool:
    val = str(value).upper().strip()
    if any(kw in val for kw in _EXCLUDE_KEYWORDS):
        return False
    if any(kw in val for kw in _HOUSE_KEYWORDS):
        return True
    return False


def _date_to_quarter(date_str: str) -> str | None:
    import datetime
    date_str = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d", "%m/%d/%Y"):
        try:
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
    ingestor = SaValuerGeneral()
    results = ingestor.run()
    print(f"\nDone. {len(results)} suburb-quarter records → {OUTPUT_PATH}")
    sys.exit(0)
