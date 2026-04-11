"""
ABS Population Ingestor — Growth Funnel Cold Filter (Step 1)

What it does:
  1. Fetches ABS Estimated Resident Population (ERP) data at LGA level.
  2. Filters to LGAs with: population > 20,000 AND growth > 1.5% (per config.yaml).
  3. Downloads the ASGS SSC-to-LGA concordance to map suburbs into qualifying LGAs.
  4. Emits a list of Tier 1 candidate Suburb objects as JSON.

Data sources (both free, no API key):
  - LGA population: ABS Data API  https://api.data.abs.gov.au
  - Suburb-to-LGA map: ABS ASGS Correspondence File (SSC to LGA)

Output: data/raw/tier1_candidates.json
Log:    data/raw/scrape_log.json  (→ Supabase scrape_log table once DB is wired)

Run standalone:
    python -m plugins.scrapers.abs_ingestor
"""

from __future__ import annotations

import io
import json
import logging
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests
import yaml

from plugins.scrapers.base_scraper import BaseScraper
from core.schemas import Suburb, DataSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "config.yaml"
CACHE_DIR = ROOT / "data" / "raw" / "abs"
OUTPUT_PATH = ROOT / "data" / "raw" / "tier1_candidates.json"

# ---------------------------------------------------------------------------
# ABS endpoints — publicly accessible, no auth required
# ---------------------------------------------------------------------------
# ABS Data API: Estimated Resident Population by LGA, SDMX-JSON
# Dataset: ABS_ERP_LGA  |  measure: 1 (persons)  |  all LGA regions
# Docs: https://api.data.abs.gov.au
ABS_ERP_URL = (
    "https://api.data.abs.gov.au/data/ABS_ERP_LGA"
    "/1.../AUS?detail=dataonly&startPeriod=2020&endPeriod=2023"
)

# ASGS Ed.3 Correspondence: State Suburb (SSC) → LGA (2022)
# Published by ABS, updated with each ASGS edition
ASGS_CONCORDANCE_URL = (
    "https://www.abs.gov.au/statistics/standards/"
    "australian-statistical-geography-standard-asgs-edition-3/"
    "jul2021-jun2026/access-and-downloads/correspondences/"
    "CG_SSC_2021_LGA_2022.zip"
)

# Requests headers — ABS API blocks the default Python UA
_HEADERS = {
    "User-Agent": "Propvest/1.0 (research tool; contact via GitHub)",
    "Accept": "application/json",
}

# ---------------------------------------------------------------------------
# Thresholds (sourced from config.yaml at runtime, these are fallback defaults)
# ---------------------------------------------------------------------------
DEFAULT_POP_THRESHOLD = 20_000
DEFAULT_GROWTH_THRESHOLD = 1.5  # percent


class AbsIngestor(BaseScraper):
    source_name = "ABS"

    def __init__(self) -> None:
        cfg = yaml.safe_load(CONFIG_PATH.read_text())
        # Growth Funnel thresholds live in config.yaml under data_filters if present,
        # otherwise fall back to architecture defaults.
        filters = cfg.get("data_filters", {})
        self.pop_threshold: int = filters.get("lga_min_population", DEFAULT_POP_THRESHOLD)
        self.growth_threshold: float = filters.get("lga_min_growth_pct", DEFAULT_GROWTH_THRESHOLD)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self) -> list[dict]:
        logger.info("AbsIngestor: starting run")
        error = None
        candidates: list[dict] = []

        try:
            lga_df = self._fetch_lga_population()
            qualifying_lgas = self._filter_lgas(lga_df)
            logger.info("Qualifying LGAs: %d", len(qualifying_lgas))

            suburb_map = self._fetch_suburb_lga_map()
            candidates = self._build_candidates(qualifying_lgas, suburb_map, lga_df)

            self._save(candidates)
            logger.info("Tier 1 candidates: %d → %s", len(candidates), OUTPUT_PATH)
        except Exception as exc:
            error = str(exc)
            logger.error("AbsIngestor failed: %s", exc)
            raise
        finally:
            self.log_run(records_processed=len(candidates), error=error)

        return candidates

    # ------------------------------------------------------------------
    # Step 1 — LGA population data
    # ------------------------------------------------------------------
    _MANUAL_FILE_INSTRUCTIONS = """
Manual download required for ABS LGA population data.

1. Go to: https://www.abs.gov.au/statistics/people/population/regional-population/latest-release
2. Scroll to "Data downloads" → download the Excel datacube (.xlsx).
3. Save it to:  data/raw/abs/erp_lga_manual.xlsx
   (The file has sheets "Table 1"–"Table 7", one per state — the ingestor reads all of them.)
""".strip()

    # ABS datacube Excel: Table 1–7 = LGA data per state, Table 8 = state totals (skip)
    _SHEET_STATE_MAP = {
        "Table 1": "NSW",
        "Table 2": "VIC",
        "Table 3": "QLD",
        "Table 4": "SA",
        "Table 5": "WA",
        "Table 6": "TAS",
        "Table 7": "NT",
    }

    def _fetch_lga_population(self) -> pd.DataFrame:
        cache_file = CACHE_DIR / "erp_lga.csv"
        manual_xlsx = CACHE_DIR / "erp_lga_manual.xlsx"

        # 1. Cached result (written by any path below)
        if cache_file.exists():
            logger.info("Using cached LGA ERP: %s", cache_file)
            return pd.read_csv(cache_file)

        # 2. ABS datacube Excel (preferred manual path)
        if manual_xlsx.exists():
            logger.info("Parsing ABS datacube Excel: %s", manual_xlsx)
            df = self._load_abs_datacube_xlsx(manual_xlsx)
            df.to_csv(cache_file, index=False)
            return df

        # 3. ABS Data API (may be blocked by network/firewall)
        logger.info("Attempting ABS API download …")
        try:
            resp = requests.get(ABS_ERP_URL, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            df = self._parse_sdmx_json(resp.json())
            df.to_csv(cache_file, index=False)
            return df
        except Exception as exc:
            logger.warning("ABS API unavailable (%s).", exc)

        raise FileNotFoundError(self._MANUAL_FILE_INSTRUCTIONS)

    def _load_abs_datacube_xlsx(self, path: Path) -> pd.DataFrame:
        """
        Parse the ABS Regional Population Excel datacube.

        Sheet layout (each Table sheet):
          Row 0–3  : title / metadata (skip)
          Row 4    : year labels — e.g. '2024', '2025', '2024–25', ...
          Row 5    : unit labels — 'LGA code', 'LGA name', 'no.', 'no.', 'no.', '%', ...
          Row 6+   : data — LGA code | LGA name | ERP prev | ERP latest | Δ no. | Δ % | ...

        We extract columns by position:
          col 0 → REGION      (LGA code)
          col 1 → REGION_NAME (LGA name)
          col 2 → prev year ERP
          col 3 → latest year ERP
          col 5 → % growth (pre-computed by ABS, annual % change)

        Returns long-format DataFrame: REGION, REGION_NAME, STATE, TIME_PERIOD, OBS_VALUE
        (two rows per LGA — prev year + latest year — so _filter_lgas can calculate growth).
        """
        xl = pd.ExcelFile(path)
        frames = []

        for sheet, state in self._SHEET_STATE_MAP.items():
            if sheet not in xl.sheet_names:
                logger.warning("Sheet '%s' not found in Excel — skipping.", sheet)
                continue

            raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype=str)

            # Find year labels row (row where col 2 and col 3 look like 4-digit years)
            year_row_idx = None
            for i, row in raw.iterrows():
                vals = [str(v).strip() for v in row]
                if len(vals) > 3 and vals[2].isdigit() and len(vals[2]) == 4:
                    year_row_idx = i
                    break

            if year_row_idx is None:
                logger.warning("Could not find year header row in sheet '%s' — skipping.", sheet)
                continue

            year_vals = [str(v).strip() for v in raw.iloc[year_row_idx]]
            prev_year = year_vals[2] if len(year_vals) > 2 else "prev"
            latest_year = year_vals[3] if len(year_vals) > 3 else "latest"

            # Data starts two rows after the year header (year row + unit label row)
            data_start = year_row_idx + 2
            data = raw.iloc[data_start:].copy()
            data.reset_index(drop=True, inplace=True)

            # Drop rows where col 0 is not a numeric LGA code
            data = data[data.iloc[:, 0].str.match(r"^\d{5}$", na=False)]

            if data.empty:
                logger.warning("No data rows found in sheet '%s'.", sheet)
                continue

            lga_codes = data.iloc[:, 0].str.strip()
            lga_names = data.iloc[:, 1].str.strip()
            erp_prev = pd.to_numeric(data.iloc[:, 2], errors="coerce")
            erp_latest = pd.to_numeric(data.iloc[:, 3], errors="coerce")

            # Build long format: one row per LGA per year
            for year, erp_series in [(prev_year, erp_prev), (latest_year, erp_latest)]:
                frame = pd.DataFrame({
                    "REGION": lga_codes.values,
                    "REGION_NAME": lga_names.values,
                    "STATE": state,
                    "TIME_PERIOD": year,
                    "OBS_VALUE": erp_series.values,
                })
                frames.append(frame)

        if not frames:
            raise ValueError("No LGA data could be parsed from the Excel file.")

        combined = pd.concat(frames, ignore_index=True)
        combined.dropna(subset=["OBS_VALUE"], inplace=True)
        return combined

    def _parse_sdmx_json(self, payload: dict) -> pd.DataFrame:
        """
        Convert ABS SDMX-JSON response to a flat DataFrame with columns:
        REGION, TIME_PERIOD, OBS_VALUE
        """
        data = payload["data"]
        structure = data["structure"]
        dataset = data["dataSets"][0]

        # Build lookup: dimension position → code → value
        series_dims = structure["dimensions"]["series"]
        obs_dims = structure["dimensions"]["observation"]

        # Find which series dimension index holds REGION and which holds TIME_PERIOD
        region_idx = next(
            i for i, d in enumerate(series_dims) if d["id"] in ("REGION", "LGA")
        )
        region_values = series_dims[region_idx]["values"]  # [{id, name}, ...]

        # Observation dimension 0 is TIME_PERIOD
        time_values = obs_dims[0]["values"]  # [{id, name}, ...]

        rows = []
        for series_key, series_data in dataset["series"].items():
            parts = series_key.split(":")
            region_code = region_values[int(parts[region_idx])]["id"]
            region_name = region_values[int(parts[region_idx])]["name"]
            for obs_key, obs_value in series_data["observations"].items():
                time_period = time_values[int(obs_key)]["id"]
                value = obs_value[0] if obs_value[0] is not None else float("nan")
                rows.append({
                    "REGION": region_code,
                    "REGION_NAME": region_name,
                    "TIME_PERIOD": time_period,
                    "OBS_VALUE": value,
                })

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Step 2 — Apply Growth Funnel filter
    # ------------------------------------------------------------------
    def _filter_lgas(self, df: pd.DataFrame) -> dict[str, dict]:
        """
        Returns {lga_code: {"lga_name": ..., "population": ..., "growth_pct": ...}}
        for all LGAs meeting both thresholds.

        The ABS ERP CSV has columns: DATAFLOW, MEASURE, REGION, TIME_PERIOD, OBS_VALUE, ...
        We need two consecutive years per LGA to compute growth.
        """
        # Normalise column names — ABS CSVs can vary slightly between releases
        df.columns = [c.strip().upper() for c in df.columns]

        required = {"REGION", "TIME_PERIOD", "OBS_VALUE"}
        if not required.issubset(df.columns):
            raise ValueError(
                f"Unexpected ABS CSV columns: {list(df.columns)}. "
                "Expected at least: REGION, TIME_PERIOD, OBS_VALUE. "
                "Re-delete the cache file and retry — the ABS may have updated its format."
            )

        # Preserve STATE column if present (comes from Excel path)
        has_state = "STATE" in df.columns
        has_name = "REGION_NAME" in df.columns

        keep_cols = ["REGION", "TIME_PERIOD", "OBS_VALUE"]
        if has_state:
            keep_cols.append("STATE")
        if has_name:
            keep_cols.append("REGION_NAME")

        df = df[keep_cols].copy()
        df["TIME_PERIOD"] = df["TIME_PERIOD"].astype(str)
        df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
        df.dropna(subset=["OBS_VALUE"], inplace=True)

        # Build a lookup for STATE and REGION_NAME per LGA code (use latest occurrence)
        meta_cols = [c for c in ["STATE", "REGION_NAME"] if c in df.columns]
        meta = df.drop_duplicates(subset=["REGION"], keep="last").set_index("REGION")[meta_cols] if meta_cols else None

        # Pivot: rows = LGA code, columns = year
        pivot = df.pivot_table(index="REGION", columns="TIME_PERIOD", values="OBS_VALUE", aggfunc="sum")
        pivot.columns = pivot.columns.astype(str)

        years = sorted(pivot.columns)
        if len(years) < 2:
            raise ValueError("Need at least 2 years of data to calculate growth rate.")

        latest_year = years[-1]
        prev_year = years[-2]

        pivot["population"] = pivot[latest_year]
        pivot["growth_pct"] = (
            (pivot[latest_year] - pivot[prev_year]) / pivot[prev_year] * 100
        ).round(2)

        mask = (pivot["population"] >= self.pop_threshold) & (pivot["growth_pct"] >= self.growth_threshold)
        qualifying = pivot[mask][["population", "growth_pct"]].copy()
        qualifying.index.name = "lga_code"
        result = qualifying.reset_index()

        # Re-attach state/name metadata if available
        if meta is not None:
            result = result.merge(meta.reset_index().rename(columns={"REGION": "lga_code"}), on="lga_code", how="left")

        return result.to_dict(orient="records")

    # ------------------------------------------------------------------
    # Step 3 — Suburb-to-LGA concordance
    # ------------------------------------------------------------------

    # Multiple URL candidates — ABS restructures downloads periodically
    _CONCORDANCE_URLS = [
        # ASGS Ed.3 — try recent LGA boundary years
        (
            "https://www.abs.gov.au/statistics/standards/"
            "australian-statistical-geography-standard-asgs-edition-3/"
            "jul2021-jun2026/access-and-downloads/correspondences/"
            "CG_SSC_2021_LGA_2022.zip"
        ),
        (
            "https://www.abs.gov.au/statistics/standards/"
            "australian-statistical-geography-standard-asgs-edition-3/"
            "jul2021-jun2026/access-and-downloads/correspondences/"
            "CG_SSC_2021_LGA_2023.zip"
        ),
        (
            "https://www.abs.gov.au/statistics/standards/"
            "australian-statistical-geography-standard-asgs-edition-3/"
            "jul2021-jun2026/access-and-downloads/correspondences/"
            "CG_SSC_2021_LGA_2024.zip"
        ),
    ]

    _CONCORDANCE_INSTRUCTIONS = """
ASGS concordance file not found. Manual download required.

1. Go to: https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/correspondences
2. Find a file named "CG_SSC_2021_LGA_<year>.zip" and download it.
3. Extract the CSV and save it to:  data/raw/abs/ssc_to_lga_manual.csv
   Required columns: SSC_CODE (or SSC_CODE_2021), SSC_NAME, LGA_CODE (or LGA_CODE_2022), LGA_NAME, STATE_NAME
""".strip()

    def _fetch_suburb_lga_map(self) -> pd.DataFrame:
        cache_file = CACHE_DIR / "ssc_to_lga.csv"
        manual_file = CACHE_DIR / "ssc_to_lga_manual.csv"

        # 1. Cached download
        if cache_file.exists():
            logger.info("Using cached SSC→LGA concordance: %s", cache_file)
            return pd.read_csv(cache_file, dtype=str)

        # 2. Manually placed file — accept both SSC and SAL naming conventions
        sal_manual = CACHE_DIR / "sal_to_lga_manual.csv"
        manual_file = sal_manual if sal_manual.exists() else manual_file
        if manual_file.exists():
            logger.info("Using manually placed concordance: %s", manual_file)
            df = pd.read_csv(manual_file, dtype=str)
            df.columns = [c.strip().upper() for c in df.columns]
            df.to_csv(cache_file, index=False)
            return df

        # 3. Try each URL candidate
        for url in self._CONCORDANCE_URLS:
            logger.info("Attempting concordance download: %s", url)
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=60)
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Failed (%s): %s", type(exc).__name__, exc)
                continue

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    logger.warning("No CSV in ZIP at %s", url)
                    continue
                with zf.open(csv_names[0]) as f:
                    concordance = pd.read_csv(f, dtype=str)

            concordance.columns = [c.strip().upper() for c in concordance.columns]
            concordance.to_csv(cache_file, index=False)
            logger.info("Concordance cached: %d rows", len(concordance))
            return concordance

        raise FileNotFoundError(self._CONCORDANCE_INSTRUCTIONS)

    # ------------------------------------------------------------------
    # Step 4 — Build Tier 1 Suburb objects
    # ------------------------------------------------------------------
    def _build_candidates(
        self,
        qualifying_lgas: list[dict],
        suburb_map: pd.DataFrame,
        lga_df: pd.DataFrame,
    ) -> list[dict]:
        """
        Join qualifying LGAs with the suburb concordance.
        Returns a list of dicts matching the Suburb schema.
        """
        qualifying_codes = {str(row["lga_code"]) for row in qualifying_lgas}
        pop_lookup = {str(row["lga_code"]): row for row in qualifying_lgas}

        # Identify concordance column names — handles both SSC (old) and SAL (new) naming
        suburb_map.columns = [c.strip().upper() for c in suburb_map.columns]

        ssc_col   = _find_col(suburb_map, ["SAL_CODE_2021", "SSC_CODE_2021", "SSC_CODE", "SAL_CODE"])
        name_col  = _find_col(suburb_map, ["SAL_NAME_2021", "SSC_NAME_2021", "SSC_NAME", "SAL_NAME"])
        lga_col   = _find_col(suburb_map, ["LGA_CODE_2021", "LGA_CODE_2022", "LGA_CODE"])
        lga_name_col = _find_col(suburb_map, ["LGA_NAME_2021", "LGA_NAME_2022", "LGA_NAME"])
        # STATE column is optional — SAL concordance doesn't include it; we use ERP data instead
        state_col = _find_col(suburb_map, ["STATE_NAME_2021", "STATE_NAME", "STATE_ABBREV"], required=False)

        matched = suburb_map[suburb_map[lga_col].isin(qualifying_codes)].copy()

        candidates = []
        for _, row in matched.iterrows():
            lga_code = str(row[lga_col])
            lga_info = pop_lookup.get(lga_code, {})

            # Prefer state from ABS Excel (already abbreviated); fall back to concordance or LGA code
            if lga_info.get("STATE"):
                state_abbrev = lga_info["STATE"]
            elif state_col:
                state_raw = str(row.get(state_col, "")).strip()
                state_abbrev = _state_to_abbrev(state_raw)
            else:
                state_abbrev = _state_from_lga_code(lga_code)

            suburb_name = str(row.get(name_col, "")).strip()
            postcode = ""  # postcode not in ASGS concordance; enriched later by scraper

            suburb_id = f"{state_abbrev}_{postcode}_{suburb_name}".upper().replace(" ", "_")

            pop_signal = DataSignal(
                name="population_growth",
                value=lga_info.get("growth_pct", 0.0),
                unit="percentage",
                source="ABS",
            )

            suburb = Suburb(
                suburb_id=suburb_id,
                name=suburb_name,
                state=state_abbrev,
                postcode=postcode,
                lga_name=str(row.get(lga_name_col, "")).strip(),
                population=int(lga_info.get("population", 0)),
                pop_growth_rate=float(lga_info.get("growth_pct", 0.0)),
                is_tier_1=True,
                signals=[pop_signal],
            )
            candidates.append(suburb.model_dump(mode="json"))

        return candidates

    # ------------------------------------------------------------------
    # Step 5 — Persist
    # ------------------------------------------------------------------
    def _save(self, candidates: list[dict]) -> None:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(candidates, indent=2, default=str))


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
        "ABS may have updated the concordance file format."
    )


# ABS LGA code prefix → state abbreviation (ASGS Ed.3)
def _state_from_lga_code(code: str) -> str:
    prefix = str(code).strip()[:1]
    return {"1": "NSW", "2": "VIC", "3": "QLD", "4": "SA",
            "5": "WA", "6": "TAS", "7": "NT", "8": "ACT"}.get(prefix, "UNK")


_STATE_MAP = {
    "new south wales": "NSW",
    "victoria": "VIC",
    "queensland": "QLD",
    "south australia": "SA",
    "western australia": "WA",
    "tasmania": "TAS",
    "northern territory": "NT",
    "australian capital territory": "ACT",
    "other territories": "OT",
}


def _state_to_abbrev(state: str) -> str:
    return _STATE_MAP.get(state.lower(), state.upper()[:3])


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    ingestor = AbsIngestor()
    results = ingestor.run()
    print(f"\nDone. {len(results)} Tier 1 suburbs written to {OUTPUT_PATH}")
    sys.exit(0)
