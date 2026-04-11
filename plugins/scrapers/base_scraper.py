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
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_PATH = Path(__file__).parents[2] / "data" / "raw" / "scrape_log.json"


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
        Append a run record to scrape_log.json.
        Replace this method body with a Supabase insert once the DB is wired up.
        Table schema expected: scrape_log(source, ran_at, records_processed, error)
        """
        entry = {
            "source": self.source_name,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "records_processed": records_processed,
            "error": error,
        }

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        existing: list = []
        if LOG_PATH.exists():
            try:
                existing = json.loads(LOG_PATH.read_text())
            except json.JSONDecodeError:
                existing = []

        existing.append(entry)
        LOG_PATH.write_text(json.dumps(existing, indent=2))
        logger.info("scrape_log: %s", entry)
