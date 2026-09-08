"""Arbeitnow collector. Public job-board API, no key required.

API: https://www.arbeitnow.com/api/job-board-api
European / remote-friendly listings with tags and location fields.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 3

# Prefer product / QA-ish tags when filtering server-side isn't available —
# we still ingest broadly and let hard filters drop noise.
PM_HINTS = ("product", "qa", "quality", "scrum", "analyst", "program", "project", "test")


class ArbeitnowCollector(Collector):
    name = "arbeitnow"

    def fetch(self):
        jobs = []
        for page in range(1, MAX_PAGES + 1):
            try:
                data = get_json(API_URL, params={"page": page})
            except Exception as exc:  # noqa: BLE001
                logger.debug("arbeitnow: page %s failed (%s)", page, exc)
                break

            rows = data.get("data", []) if isinstance(data, dict) else []
            if not rows:
                break

            for row in rows:
                try:
                    title = row.get("title") or ""
                    tags = [str(t).lower() for t in (row.get("tags") or [])]
                    blob = f"{title} {' '.join(tags)}".lower()
                    if not any(h in blob for h in PM_HINTS):
                        continue

                    location = row.get("location") or ""
                    remote = bool(row.get("remote"))
                    location_raw = "Remote" if remote and not location else (location or ("Remote" if remote else ""))

                    jobs.append(
                        Job(
                            source="arbeitnow",
                            external_id=str(row.get("slug") or row.get("url") or title),
                            title=title,
                            company=row.get("company_name") or "Unknown",
                            url=row.get("url") or "",
                            description=row.get("description") or "",
                            location_raw=location_raw or "Remote",
                            job_type_raw=(row.get("job_types") or [None])[0] if row.get("job_types") else None,
                            posted_at=row.get("created_at"),
                            tags=row.get("tags") or [],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("arbeitnow: skipping malformed row (%s)", exc)

            links = (data.get("links") or {}) if isinstance(data, dict) else {}
            if not links.get("next"):
                break
        return jobs
