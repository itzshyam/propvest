"""
Geography Trinity Builder — Master Suburb Lookup Table

Joins three ABS ASGS concordances to build the canonical suburb lookup:
  SAL (suburb) ↔ Postcode/POA (SQM lookup key) ↔ SA2 (ABS signal join) ↔ LGA (infra join)

Sources (all free, ABS ASGS Edition 3):
  - SAL → LGA:  already cached from abs_ingestor run (data/raw/abs/ssc_to_lga.csv)
  - SAL → SA2:  ABS ASGS CG_SAL_2021_SA2_2021.zip
  - SAL → POA:  ABS ASGS CG_SAL_2021_POA_2021.zip  (POA code = 4-digit postcode)

Postcode fallback (Session 6):
  When ABS SAL→POA concordance is unavailable (all known URLs 404), postcode enrichment
  falls back to data.gov.au Australian Postcodes CSV (locality + state → postcode).
  Downloaded from: https://raw.githubusercontent.com/matthewproctor/australianpostcodes/master/australian_postcodes.csv
  (mirror of the official data.gov.au/data/dataset/Australian-postcodes dataset)

  Matching strategy:
    - Suburb names like "Abbotsford (NSW)" have the parenthetical stripped → "ABBOTSFORD"
    - Where a suburb maps to multiple postcodes, the dominant (first/lowest by sort order) is used
    - All multi-postcode mappings are logged to data/raw/abs/multi_postcode_suburbs.json

The SAL→SA2 and SAL→POA files have M:N relationships (a suburb can straddle
multiple postcodes / SA2s). We resolve them by taking the record with the
highest RATIO_FROM_TO per SAL code, i.e. the dominant postcode/SA2.

Output:
  - data/raw/geography_trinity.json   — canonical suburb table (local)
  - supabase/migrations/001_create_core_tables.sql  — Supabase DDL (written once)

Run standalone:
    python -m plugins.scrapers.geography_builder
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests
import yaml

from plugins.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "config.yaml"
CACHE_DIR = ROOT / "data" / "raw" / "abs"
OUTPUT_PATH = ROOT / "data" / "raw" / "geography_trinity.json"
SQL_PATH = ROOT / "supabase" / "migrations" / "001_create_core_tables.sql"

_HEADERS = {
    "User-Agent": "Propvest/1.0 (research tool; contact via GitHub)",
    "Accept": "*/*",
}

_ASGS_BASE = (
    "https://www.abs.gov.au/statistics/standards/"
    "australian-statistical-geography-standard-asgs-edition-3/"
    "jul2021-jun2026/access-and-downloads/correspondences/"
)

# data.gov.au postcode CSV (locality + state → postcode)
# Official dataset: https://data.gov.au/data/dataset/Australian-postcodes
# Served via GitHub mirror (data.gov.au redirect resolution is broken for programmatic access)
_DATAGOV_POSTCODES_URL = (
    "https://raw.githubusercontent.com/matthewproctor/"
    "australianpostcodes/master/australian_postcodes.csv"
)
_DATAGOV_POSTCODES_CACHE = "australian_postcodes.csv"
_MULTI_POSTCODE_LOG = "multi_postcode_suburbs.json"

_SA2_CONCORDANCE_URLS = [
    _ASGS_BASE + "CG_SAL_2021_SA2_2021.zip",
    _ASGS_BASE + "CG_SSC_2021_SA2_2021.zip",
    _ASGS_BASE + "CG_SAL_2021_SA2_2022.zip",
    _ASGS_BASE + "CG_SSC_2021_SA2_2022.zip",
]

_POA_CONCORDANCE_URLS = [
    _ASGS_BASE + "CG_SAL_2021_POA_2021.zip",
    _ASGS_BASE + "CG_SSC_2021_POA_2021.zip",
    _ASGS_BASE + "CG_SAL_2021_POA_2022.zip",
    _ASGS_BASE + "CG_SSC_2021_POA_2022.zip",
]

_SA2_MANUAL_INSTRUCTIONS = """
SAL→SA2 concordance not found. Manual download required.

1. Go to: https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/correspondences
2. Find "CG_SAL_2021_SA2_2021.zip" and download it.
3. Extract the CSV and save it to: data/raw/abs/sal_to_sa2_manual.csv
   Required columns: SAL_CODE_2021, SA2_CODE_2021, SA2_NAME_2021, RATIO_FROM_TO
""".strip()

_POA_MANUAL_INSTRUCTIONS = """
SAL→POA concordance not found. Manual download required.

1. Go to: https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/correspondences
2. Find "CG_SAL_2021_POA_2021.zip" and download it.
3. Extract the CSV and save it to: data/raw/abs/sal_to_poa_manual.csv
   Required columns: SAL_CODE_2021, POA_CODE_2021, RATIO_FROM_TO
   (POA_CODE_2021 is the 4-digit postcode.)
""".strip()


class GeographyBuilder(BaseScraper):
    source_name = "ABS_GEOGRAPHY"

    def __init__(self) -> None:
        cfg = yaml.safe_load(CONFIG_PATH.read_text())
        filters = cfg.get("data_filters", {})
        self.pop_threshold: int = filters.get("lga_min_population", 20_000)
        self.growth_threshold: float = filters.get("lga_min_growth_pct", 0.5)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self, enrich_postcodes: bool = True) -> list[dict]:
        logger.info("GeographyBuilder: starting run")
        error = None
        records: list[dict] = []

        try:
            sal_lga = self._load_sal_lga()
            sal_sa2 = self._load_sal_sa2()
            sal_poa = self._load_sal_poa()
            qualifying = self._qualifying_lgas()

            records = self._build(sal_lga, sal_sa2, sal_poa, qualifying)

            # Postcode enrichment: if ABS POA concordance wasn't available,
            # fill in missing postcodes from data.gov.au locality+state lookup.
            if enrich_postcodes:
                missing_before = sum(1 for r in records if not r.get("postcode"))
                if missing_before > 0:
                    logger.info(
                        "Postcode enrichment: %d suburbs missing postcode — "
                        "enriching from data.gov.au postcodes CSV",
                        missing_before,
                    )
                    postcode_lookup = self._load_datagov_postcodes()
                    records = self._enrich_postcodes_from_datagov(records, postcode_lookup)
                    missing_after = sum(1 for r in records if not r.get("postcode"))
                    logger.info(
                        "Postcode enrichment complete: %d filled, %d still missing",
                        missing_before - missing_after,
                        missing_after,
                    )

            self._save_json(records)

            logger.info(
                "Geography Trinity: %d suburbs written → %s",
                len(records),
                OUTPUT_PATH,
            )
        except Exception as exc:
            error = str(exc)
            logger.error("GeographyBuilder failed: %s", exc)
            raise
        finally:
            self.log_run(records_processed=len(records), error=error)

        return records

    # ------------------------------------------------------------------
    # Qualifying LGAs — re-derived from cached ERP data
    # ------------------------------------------------------------------
    def _qualifying_lgas(self) -> dict[str, dict]:
        """
        Return {lga_code_str: {population, growth_pct, state, lga_name}}
        for all LGAs that pass the Growth Funnel thresholds.

        Re-derives from erp_lga.csv (the abs_ingestor cache) so this module
        has no direct dependency on abs_ingestor.py.
        """
        cache = CACHE_DIR / "erp_lga.csv"
        if not cache.exists():
            raise FileNotFoundError(
                "erp_lga.csv not found — run abs_ingestor first:\n"
                "    python -m plugins.scrapers.abs_ingestor"
            )

        df = pd.read_csv(cache, dtype=str)
        df.columns = [c.strip().upper() for c in df.columns]
        df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
        df.dropna(subset=["OBS_VALUE"], inplace=True)

        pivot = df.pivot_table(
            index="REGION", columns="TIME_PERIOD", values="OBS_VALUE", aggfunc="sum"
        )
        pivot.columns = pivot.columns.astype(str)
        years = sorted(pivot.columns)

        pivot["population"] = pivot[years[-1]]
        pivot["growth_pct"] = (
            (pivot[years[-1]] - pivot[years[-2]]) / pivot[years[-2]] * 100
        ).round(2)

        mask = (
            (pivot["population"] >= self.pop_threshold)
            & (pivot["growth_pct"] >= self.growth_threshold)
        )
        qualifying = pivot[mask][["population", "growth_pct"]].copy()

        # Re-attach state + name from the raw df
        meta = (
            df.drop_duplicates("REGION")
            .set_index("REGION")[
                [c for c in ["STATE", "REGION_NAME"] if c in df.columns]
            ]
        )

        result = {}
        for code, row in qualifying.iterrows():
            code_str = str(code)
            meta_row = meta.loc[code] if code in meta.index else {}
            result[code_str] = {
                "population": int(row["population"]),
                "growth_pct": float(row["growth_pct"]),
                "state": str(meta_row.get("STATE", "")) if isinstance(meta_row, dict) else str(meta_row["STATE"]) if "STATE" in meta_row.index else "",
                "lga_name": str(meta_row.get("REGION_NAME", "")) if isinstance(meta_row, dict) else str(meta_row["REGION_NAME"]) if "REGION_NAME" in meta_row.index else "",
            }

        logger.info("Qualifying LGAs: %d", len(result))
        return result

    # ------------------------------------------------------------------
    # Concordance loaders
    # ------------------------------------------------------------------
    def _load_sal_lga(self) -> pd.DataFrame:
        """SAL→LGA — already cached by abs_ingestor."""
        cache = CACHE_DIR / "ssc_to_lga.csv"
        if not cache.exists():
            raise FileNotFoundError(
                "ssc_to_lga.csv not found — run abs_ingestor first:\n"
                "    python -m plugins.scrapers.abs_ingestor"
            )
        df = pd.read_csv(cache, dtype=str)
        df.columns = [c.strip().upper() for c in df.columns]
        logger.info("SAL→LGA concordance: %d rows", len(df))
        return df

    def _load_sal_sa2(self) -> pd.DataFrame | None:
        return self._load_concordance(
            cache_name="sal_to_sa2.csv",
            manual_names=["sal_to_sa2_manual.csv"],
            urls=_SA2_CONCORDANCE_URLS,
            fallback_instructions=_SA2_MANUAL_INSTRUCTIONS,
            label="SAL→SA2",
            optional=True,
        )

    def _load_sal_poa(self) -> pd.DataFrame | None:
        return self._load_concordance(
            cache_name="sal_to_poa.csv",
            manual_names=["sal_to_poa_manual.csv"],
            urls=_POA_CONCORDANCE_URLS,
            fallback_instructions=_POA_MANUAL_INSTRUCTIONS,
            label="SAL→POA",
            optional=True,
        )

    def _load_datagov_postcodes(self) -> dict[tuple[str, str], str]:
        """
        Load data.gov.au Australian Postcodes CSV and build a lookup:
            (locality_upper, state_upper) → dominant_postcode

        Dominant postcode: where a locality maps to multiple postcodes, we take
        the first entry when sorted by postcode (typically the primary/lowest code).

        Multi-postcode suburbs are logged to data/raw/abs/multi_postcode_suburbs.json.
        Postcodes are zero-padded to 4 digits (e.g. 200 → "0200" for ACT).
        """
        cache = CACHE_DIR / _DATAGOV_POSTCODES_CACHE
        if not cache.exists():
            logger.info("Downloading data.gov.au postcodes CSV: %s", _DATAGOV_POSTCODES_URL)
            try:
                resp = requests.get(_DATAGOV_POSTCODES_URL, headers=_HEADERS, timeout=60)
                resp.raise_for_status()
                cache.write_bytes(resp.content)
                logger.info("Downloaded %d bytes → %s", len(resp.content), cache)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to download postcodes CSV: {exc}\n"
                    f"Manual fix: download {_DATAGOV_POSTCODES_URL} → {cache}"
                ) from exc

        df = pd.read_csv(cache, dtype={"postcode": str}, low_memory=False)
        df["postcode"] = df["postcode"].str.strip().str.zfill(4)
        df["locality_upper"] = df["locality"].str.upper().str.strip()
        df["state_upper"] = df["state"].str.upper().str.strip()

        # Drop rows missing key fields
        df = df.dropna(subset=["locality_upper", "state_upper", "postcode"])
        df = df[df["postcode"].str.match(r"^\d{4}$")]

        # Sort so first entry = lowest postcode per (locality, state)
        df = df.sort_values("postcode")

        # Build multi-postcode audit log
        multi: dict[str, list[str]] = {}
        grouped = df.groupby(["locality_upper", "state_upper"])["postcode"].apply(list)
        for (locality, state), postcodes in grouped.items():
            unique = list(dict.fromkeys(postcodes))  # preserve order, deduplicate
            if len(unique) > 1:
                key = f"{locality} ({state})"
                multi[key] = unique

        multi_log_path = CACHE_DIR / _MULTI_POSTCODE_LOG
        multi_log_path.write_text(json.dumps(multi, indent=2, sort_keys=True))
        logger.info(
            "Multi-postcode suburbs: %d logged to %s", len(multi), multi_log_path
        )

        # Build dominant lookup: first (lowest) postcode per (locality, state)
        dominant = df.drop_duplicates(subset=["locality_upper", "state_upper"], keep="first")
        lookup: dict[tuple[str, str], str] = {
            (row["locality_upper"], row["state_upper"]): row["postcode"]
            for _, row in dominant.iterrows()
        }
        logger.info("Postcode lookup built: %d (locality, state) pairs", len(lookup))
        return lookup

    def _enrich_postcodes_from_datagov(
        self, records: list[dict], lookup: dict[tuple[str, str], str]
    ) -> list[dict]:
        """
        Fill in missing postcodes using the data.gov.au locality+state lookup.
        Also regenerates domain_slug for any record whose postcode changes.

        Matching strategy:
          1. Try exact upper-case match: (suburb_name.upper(), state.upper())
          2. Try stripped (remove parenthetical suffixes): "Abbotsford (NSW)" → "ABBOTSFORD"
        """
        filled = 0
        still_missing = 0
        for record in records:
            if record.get("postcode"):
                continue  # already has a postcode from ABS concordance

            name = record.get("suburb_name", "")
            state = record.get("state", "").upper()

            # Try exact match first
            postcode = lookup.get((name.upper(), state))

            # Fallback: strip parenthetical suffix  e.g. "Abbotsford (NSW)" → "ABBOTSFORD"
            if not postcode and "(" in name:
                stripped = re.sub(r"\s*\(.*?\)\s*", "", name).strip().upper()
                postcode = lookup.get((stripped, state))

            if postcode:
                record["postcode"] = postcode
                # Regenerate slug now that postcode is known
                record["domain_slug"] = _domain_slug(name, postcode, record.get("state", ""))
                filled += 1
            else:
                still_missing += 1

        logger.info(
            "_enrich_postcodes_from_datagov: filled=%d still_missing=%d",
            filled,
            still_missing,
        )
        return records

    def _load_concordance(
        self,
        cache_name: str,
        manual_names: list[str],
        urls: list[str],
        fallback_instructions: str,
        label: str,
        optional: bool = False,
    ) -> pd.DataFrame | None:
        cache_file = CACHE_DIR / cache_name

        if cache_file.exists():
            df = pd.read_csv(cache_file, dtype=str)
            logger.info("%s concordance (cached): %d rows", label, len(df))
            return df

        for manual_name in manual_names:
            manual = CACHE_DIR / manual_name
            if manual.exists():
                df = pd.read_csv(manual, dtype=str)
                df.columns = [c.strip().upper() for c in df.columns]
                df.to_csv(cache_file, index=False)
                logger.info("%s concordance (manual): %d rows", label, len(df))
                return df

        for url in urls:
            logger.info("Downloading %s concordance: %s", label, url)
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=60)
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("%s download failed (%s): %s", label, type(exc).__name__, exc)
                continue

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not csv_files:
                    logger.warning("No CSV found in ZIP: %s", url)
                    continue
                with zf.open(csv_files[0]) as f:
                    df = pd.read_csv(f, dtype=str)

            df.columns = [c.strip().upper() for c in df.columns]
            df.to_csv(cache_file, index=False)
            logger.info("%s concordance (downloaded): %d rows", label, len(df))
            return df

        if optional:
            logger.warning(
                "%s concordance unavailable — %s will be null.\n%s",
                label,
                cache_name.replace("sal_to_", "").replace(".csv", ""),
                fallback_instructions,
            )
            return None
        raise FileNotFoundError(fallback_instructions)

    # ------------------------------------------------------------------
    # Build the Geography Trinity
    # ------------------------------------------------------------------
    def _build(
        self,
        sal_lga: pd.DataFrame,
        sal_sa2: pd.DataFrame | None,
        sal_poa: pd.DataFrame | None,
        qualifying: dict[str, dict],
    ) -> list[dict]:
        """
        Join the three concordances and emit one record per suburb.

        M:N resolution: where a suburb spans multiple SA2s or postcodes,
        take the one with the highest RATIO_FROM_TO (dominant assignment).
        """
        # --- Identify columns ---
        sal_col = _find_col(sal_lga, ["SAL_CODE_2021", "SSC_CODE_2021", "SSC_CODE", "SAL_CODE"])
        sal_name_col = _find_col(sal_lga, ["SAL_NAME_2021", "SSC_NAME_2021", "SSC_NAME", "SAL_NAME"])
        lga_col = _find_col(sal_lga, ["LGA_CODE_2021", "LGA_CODE_2022", "LGA_CODE"])
        lga_name_col = _find_col(sal_lga, ["LGA_NAME_2021", "LGA_NAME_2022", "LGA_NAME"])

        # Filter SAL→LGA to qualifying LGAs only
        base = sal_lga[sal_lga[lga_col].isin(qualifying.keys())].copy()
        base = base[[sal_col, sal_name_col, lga_col, lga_name_col]].rename(
            columns={
                sal_col: "sal_code",
                sal_name_col: "suburb_name",
                lga_col: "lga_code",
                lga_name_col: "lga_name",
            }
        )

        # --- SA2 join (dominant per SAL) ---
        sa2_sal_col = _find_col(sal_sa2, ["SAL_CODE_2021", "SSC_CODE_2021", "SAL_CODE"], required=False) if sal_sa2 is not None else None
        sa2_code_col = _find_col(sal_sa2, ["SA2_CODE_2021", "SA2_CODE"], required=False) if sal_sa2 is not None else None
        sa2_name_col = _find_col(sal_sa2, ["SA2_NAME_2021", "SA2_NAME"], required=False) if sal_sa2 is not None else None

        if sal_sa2 is not None and sa2_sal_col and sa2_code_col:
            sa2_ratio_col = _find_col(sal_sa2, ["RATIO_FROM_TO", "RATIO"], required=False)
            sa2_sub = sal_sa2[[sa2_sal_col, sa2_code_col] + ([sa2_name_col] if sa2_name_col else []) + ([sa2_ratio_col] if sa2_ratio_col else [])].copy()
            if sa2_ratio_col:
                sa2_sub[sa2_ratio_col] = pd.to_numeric(sa2_sub[sa2_ratio_col], errors="coerce").fillna(0)
                sa2_sub = sa2_sub.sort_values(sa2_ratio_col, ascending=False).drop_duplicates(sa2_sal_col)
            else:
                sa2_sub = sa2_sub.drop_duplicates(sa2_sal_col)
            rename = {sa2_sal_col: "sal_code", sa2_code_col: "sa2_code"}
            if sa2_name_col:
                rename[sa2_name_col] = "sa2_name"
            sa2_sub = sa2_sub.rename(columns=rename)[["sal_code", "sa2_code"] + (["sa2_name"] if sa2_name_col else [])]
            base = base.merge(sa2_sub, on="sal_code", how="left")
        else:
            logger.warning("SA2 concordance columns not recognised — sa2_code will be null")
            base["sa2_code"] = None
            base["sa2_name"] = None

        # --- POA (postcode) join (dominant per SAL) ---
        poa_sal_col = _find_col(sal_poa, ["SAL_CODE_2021", "SSC_CODE_2021", "SAL_CODE"], required=False) if sal_poa is not None else None
        poa_code_col = _find_col(sal_poa, ["POA_CODE_2021", "POA_CODE"], required=False) if sal_poa is not None else None

        if sal_poa is not None and poa_sal_col and poa_code_col:
            poa_ratio_col = _find_col(sal_poa, ["RATIO_FROM_TO", "RATIO"], required=False)
            poa_sub = sal_poa[[poa_sal_col, poa_code_col] + ([poa_ratio_col] if poa_ratio_col else [])].copy()
            if poa_ratio_col:
                poa_sub[poa_ratio_col] = pd.to_numeric(poa_sub[poa_ratio_col], errors="coerce").fillna(0)
                poa_sub = poa_sub.sort_values(poa_ratio_col, ascending=False).drop_duplicates(poa_sal_col)
            else:
                poa_sub = poa_sub.drop_duplicates(poa_sal_col)
            poa_sub = poa_sub.rename(columns={poa_sal_col: "sal_code", poa_code_col: "postcode"})[["sal_code", "postcode"]]
            base = base.merge(poa_sub, on="sal_code", how="left")
        else:
            logger.warning("POA concordance columns not recognised — postcode will be null")
            base["postcode"] = None

        # --- Attach qualifying LGA metadata ---
        records = []
        for _, row in base.iterrows():
            lga_code = str(row["lga_code"]).strip()
            lga_info = qualifying.get(lga_code, {})

            suburb_name = str(row["suburb_name"]).strip()
            state = str(lga_info.get("state", "")).strip()
            postcode = str(row.get("postcode", "") or "").strip()
            sa2_code = str(row.get("sa2_code", "") or "").strip() or None
            sa2_name = str(row.get("sa2_name", "") or "").strip() or None

            records.append({
                "suburb_name": suburb_name,
                "state": state,
                "postcode": postcode,
                "sal_code": str(row["sal_code"]).strip(),
                "sa2_code": sa2_code,
                "sa2_name": sa2_name,
                "lga_code": lga_code,
                "lga_name": str(row["lga_name"]).strip(),
                "population": lga_info.get("population"),
                "abs_growth_rate": lga_info.get("growth_pct"),
                "is_tier1": True,
                "scrape_tier": None,  # set by tier_classifier
                "domain_slug": _domain_slug(suburb_name, postcode, state),
                "data_thin": False,
                "median_house_price": None,
            })

        return records

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    def _save_json(self, records: list[dict]) -> None:
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
        "ABS may have updated the concordance file format."
    )


def _domain_slug(name: str, postcode: str, state: str) -> str:
    """
    Generate the Domain suburb profile URL slug.
    Format: {suburb-kebab-case}-{state-lower}-{postcode}
    Example: "Paddington" + "QLD" + "4064" → "paddington-qld-4064"
    Verified: domain.com.au/suburb-profile/paddington-qld-4064 returns 200.

    Parenthetical disambiguation suffixes are stripped before slugifying:
      "Paddington (Qld)" → "paddington-qld-4064"   (not "paddington-qld-qld-4064")
      "Abbotsford (NSW)" → "abbotsford-nsw-2046"
    """
    # Strip ABS disambiguation parens: "Paddington (Qld)", "Alison (Central Coast - NSW)"
    clean_name = re.sub(r"\s*\(.*?\)\s*", "", name).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-")
    parts = [p for p in [slug, state.lower(), postcode] if p]
    return "-".join(parts)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    builder = GeographyBuilder()
    results = builder.run()
    print(f"\nDone. {len(results)} suburbs written to {OUTPUT_PATH}")
    sys.exit(0)
