"""Lever collector. Public per-company postings API, no key required.

API: https://api.lever.co/v0/postings/<company>?mode=json

Like Greenhouse, Lever has no cross-company search. Populate
config/preferences.json -> sources.lever_companies with the company slugs
you want tracked (visible in jobs.lever.co/<slug>); a no-op if empty.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://api.lever.co/v0/postings/{company}"


class LeverCollector(Collector):
    name = "lever"

    def __init__(self, companies: list[str] | None = None):
        self.companies = companies or []

    def fetch(self):
        jobs = []
        for company in self.companies:
            try:
                data = get_json(API_URL.format(company=company), params={"mode": "json"})
            except Exception as exc:  # noqa: BLE001
                logger.debug("lever: company %s failed (%s)", company, exc)
                continue

            if not isinstance(data, list):
                continue

            for row in data:
                try:
                    categories = row.get("categories", {}) or {}
                    jobs.append(
                        Job(
                            source=f"lever:{company}",
                            external_id=str(row.get("id")),
                            title=row.get("text", ""),
                            company=company,
                            url=row.get("hostedUrl", ""),
                            description=row.get("descriptionPlain", "") or row.get("description", ""),
                            location_raw=categories.get("location", ""),
                            job_type_raw=categories.get("commitment"),
                            posted_at=str(row.get("createdAt")) if row.get("createdAt") else None,
                            tags=[t for t in [categories.get("team"), categories.get("department")] if t],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("lever: skipping malformed row for %s (%s)", company, exc)
        return jobs
