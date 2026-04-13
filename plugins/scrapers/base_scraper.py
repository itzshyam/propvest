"""
Base scraper interface.
Every scraper plugin must extend this class.

Architecture rule: Plugins communicate via event bus — never direct imports.
All business logic lives in plugins; core only orchestrates.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_PATH = Path(__file__).parents[2] / "data" / "raw" / "scrape_log.json"

# Load .env from project root if present (no-op if not found)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[2] / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed — env vars must be set in environment


def _get_supabase_client():
    """
    Return a supabase client if SUPABASE_URL + SUPABASE_ANON_KEY are set,
    otherwise return None. Failures are logged and swallowed so the file
    fallback remains active.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        logger.warning("Supabase client init failed: %s", exc)
        return None


class BaseScraper(ABC):
    source_name: str = ""  # Override in subclass, e.g. "ABS"

    @abstractmethod
    def run(self) -> list:
        """Execute the scrape/ingest. Return list of processed records."""

    def log_run(
        self,
        records_processed: int,
        error: str | None = None,
    ) -> None:
        """
        Write a run record to:
          1. Supabase scrape_log table (primary, if credentials are available)
          2. data/raw/scrape_log.json (always — offline fallback + local audit trail)

        Table schema: scrape_log(source TEXT, ran_at TIMESTAMPTZ, records_processed INT, error TEXT)
        """
        entry = {
            "source": self.source_name,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "records_processed": records_processed,
            "error": error,
        }

        # --- 1. Supabase insert ---
        client = _get_supabase_client()
        if client is not None:
            try:
                client.table("scrape_log").insert(entry).execute()
                logger.info("scrape_log → Supabase: %s", entry)
            except Exception as exc:
                logger.warning("Supabase scrape_log insert failed (falling back to file): %s", exc)

        # --- 2. File fallback (always runs) ---
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if LOG_PATH.exists():
            try:
                existing = json.loads(LOG_PATH.read_text())
            except json.JSONDecodeError:
                existing = []
        existing.append(entry)
        LOG_PATH.write_text(json.dumps(existing, indent=2))
        logger.info("scrape_log → file: %s", entry)
