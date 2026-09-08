"""Wellfound collector.

Wellfound (AngelList Talent) has no public jobs API, and its listings are
gated behind a logged-in session with anti-scraping protections - so this
collector deliberately does NOT scrape wellfound.com. Automated, unauthorized
scraping of a site that disallows it isn't something this project takes on,
even though Wellfound's "Hires Remotely From" field would otherwise be exactly
the eligibility signal this pipeline wants.

Instead this is a manual-import collector: periodically export or copy the
postings you care about into `data/wellfound_manual.json` (a list of objects
matching the schema below - title, company, url, location, hires_remotely_from,
description) and this collector will fold them into the normal pipeline
(hard filters + AI scoring + Discord), same as any other source. It is a
no-op, not an error, when that file doesn't exist yet.
"""
from __future__ import annotations

import json
import os

from backend.collectors.base import Collector, logger
from backend.models import Job

MANUAL_FILE = os.path.join("data", "wellfound_manual.json")


class WellfoundCollector(Collector):
    name = "wellfound"

    def __init__(self, manual_file: str = MANUAL_FILE):
        self.manual_file = manual_file

    def fetch(self):
        if not os.path.exists(self.manual_file):
            logger.debug("wellfound: no manual import file at %s (skipping, not an error)", self.manual_file)
            return []

        try:
            with open(self.manual_file, "r", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("wellfound: could not read %s (%s)", self.manual_file, exc)
            return []

        jobs = []
        for row in rows:
            try:
                jobs.append(
                    Job(
                        source="wellfound",
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
                logger.debug("wellfound: skipping malformed manual row (%s)", exc)
        return jobs
