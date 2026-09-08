"""Remotive collector. Public JSON API, no key required.

API: https://remotive.com/api/remote-jobs?category=<slug>
Docs: https://remotive.com/api/remote-jobs (category filter narrows server-side
so we don't have to page through every remote job on the site).
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://remotive.com/api/remote-jobs"

# Remotive's own category taxonomy - the slugs that plausibly hold PM/QA/Scrum roles.
CATEGORIES = ["product", "project-management", "qa", "customer-support", "all-others"]


class RemotiveCollector(Collector):
    name = "remotive"

    def fetch(self):
        seen_ids = set()
        jobs = []
        for category in CATEGORIES:
            try:
                data = get_json(API_URL, params={"category": category})
            except Exception as exc:  # noqa: BLE001
                logger.debug("remotive: category %s failed (%s)", category, exc)
                continue

            for row in data.get("jobs", []):
                rid = row.get("id")
                if rid is None or rid in seen_ids:
                    continue
                seen_ids.add(rid)
                try:
                    jobs.append(
                        Job(
                            source="remotive",
                            external_id=str(rid),
                            title=row.get("title", ""),
                            company=row.get("company_name", ""),
                            url=row.get("url", ""),
                            description=row.get("description", ""),
                            location_raw=row.get("candidate_required_location", "") or "Remote",
                            salary_raw=row.get("salary") or None,
                            job_type_raw=row.get("job_type"),
                            posted_at=row.get("publication_date"),
                            tags=row.get("tags", []) or [],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("remotive: skipping malformed row %s (%s)", rid, exc)
        return jobs
