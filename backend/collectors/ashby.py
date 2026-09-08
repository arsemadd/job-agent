"""Ashby collector. Public per-company posting API, no key required.

API: https://api.ashbyhq.com/posting-api/job-board/{org}
Company slugs come from config/preferences.json → sources.ashby_companies.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_TMPL = "https://api.ashbyhq.com/posting-api/job-board/{org}"


class AshbyCollector(Collector):
    name = "ashby"

    def __init__(self, companies: list[str] | None = None):
        self.companies = [c.strip() for c in (companies or []) if c and c.strip()]

    def fetch(self):
        jobs = []
        for org in self.companies:
            try:
                data = get_json(API_TMPL.format(org=org), params={"includeCompensation": "true"})
            except Exception as exc:  # noqa: BLE001
                logger.debug("ashby: board %s failed (%s)", org, exc)
                continue

            for row in data.get("jobs", []) if isinstance(data, dict) else []:
                try:
                    if row.get("isListed") is False:
                        continue
                    location = row.get("location") or ""
                    secondary = row.get("secondaryLocations") or []
                    if secondary:
                        extras = ", ".join(
                            (s.get("location") if isinstance(s, dict) else str(s)) for s in secondary[:3]
                        )
                        if extras:
                            location = f"{location}; {extras}" if location else extras
                    if row.get("isRemote") and location and "remote" not in location.lower():
                        location = f"Remote · {location}"
                    elif row.get("isRemote") and not location:
                        location = "Remote"

                    jobs.append(
                        Job(
                            source=f"ashby:{org}",
                            external_id=str(row.get("id") or row.get("jobUrl")),
                            title=row.get("title", ""),
                            company=row.get("companyName") or org,
                            url=row.get("jobUrl") or row.get("applyUrl") or "",
                            description=row.get("descriptionPlain") or row.get("descriptionHtml") or "",
                            location_raw=location or "Remote",
                            job_type_raw=row.get("employmentType"),
                            posted_at=row.get("publishedAt"),
                            tags=[row.get("department")] if row.get("department") else [],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("ashby: skipping malformed row on %s (%s)", org, exc)
        return jobs
