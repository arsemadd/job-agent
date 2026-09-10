"""Working Nomads collector — public JSON feed, no key required.

API: https://www.workingnomads.com/api/exposed_jobs/
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://www.workingnomads.com/api/exposed_jobs/"
PM_HINTS = (
    "product", "qa", "quality", "scrum", "agile", "test", "analyst",
    "program manager", "project manager", "owner", "delivery",
)


class WorkingNomadsCollector(Collector):
    name = "workingnomads"

    def fetch(self):
        data = get_json(API_URL)
        rows = data if isinstance(data, list) else []
        jobs = []
        for row in rows:
            try:
                title = row.get("title") or ""
                category = (row.get("category_name") or "").lower()
                tags = [str(t).lower() for t in (row.get("tags") or [])]
                blob = f"{title} {category} {' '.join(tags)}".lower()
                if not any(h in blob for h in PM_HINTS):
                    continue
                jobs.append(
                    Job(
                        source="workingnomads",
                        external_id=str(row.get("url") or title),
                        title=title,
                        company=row.get("company_name") or "Unknown",
                        url=row.get("url") or "",
                        description=row.get("description") or "",
                        location_raw=row.get("location") or "Remote",
                        posted_at=row.get("pub_date"),
                        tags=(row.get("tags") or []) + ([row["category_name"]] if row.get("category_name") else []),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("workingnomads: skipping malformed row (%s)", exc)
        return jobs
