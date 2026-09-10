"""Generic manual-import collector for boards without a public API.

Drop a JSON list into `data/<name>_manual.json` with objects shaped like:
  {title, company, url, location, hires_remotely_from, description, salary, job_type, posted_at, tags, id}

Used for Wellfound, The SaaS Jobs, Startup Jobs, and other discovery-only boards
you want to fold into scoring without scraping.
"""
from __future__ import annotations

import json
import os

from backend.collectors.base import Collector, logger
from backend.models import Job


class ManualImportCollector(Collector):
    def __init__(self, name: str, manual_file: str):
        self.name = name
        self.manual_file = manual_file

    def fetch(self):
        if not os.path.exists(self.manual_file):
            logger.debug("%s: no manual import file at %s (skipping)", self.name, self.manual_file)
            return []
        try:
            with open(self.manual_file, "r", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: could not read %s (%s)", self.name, self.manual_file, exc)
            return []

        if not isinstance(rows, list):
            logger.warning("%s: expected a JSON list in %s", self.name, self.manual_file)
            return []

        jobs = []
        for row in rows:
            try:
                jobs.append(
                    Job(
                        source=self.name,
                        external_id=str(row.get("id") or row.get("url")),
                        title=row.get("title", ""),
                        company=row.get("company", ""),
                        url=row.get("url", ""),
                        description=row.get("description", ""),
                        location_raw=row.get("location", ""),
                        hires_remotely_from=row.get("hires_remotely_from"),
                        salary_raw=row.get("salary"),
                        job_type_raw=row.get("job_type"),
                        posted_at=row.get("posted_at"),
                        tags=row.get("tags", []) or [],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s: skipping malformed manual row (%s)", self.name, exc)
        return jobs
