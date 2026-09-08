"""Himalayas collector. Public JSON API, no key required.

API: https://himalayas.app/jobs/api?limit=&offset=
Each job can carry a `locationRestrictions` list naming eligible
countries/regions - when present this is a strong, explicit eligibility
signal (similar in spirit to Wellfound's "Hires Remotely From").

Himalayas' response shape has shifted over the product's life; this collector
is defensive about missing/renamed fields so a schema tweak degrades to fewer
fields captured rather than a hard failure (safe_fetch also catches anything
that still slips through).
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://himalayas.app/jobs/api"
PAGE_SIZE = 20
MAX_PAGES = 5


class HimalayasCollector(Collector):
    name = "himalayas"

    def fetch(self):
        jobs = []
        offset = 0
        for _ in range(MAX_PAGES):
            data = get_json(API_URL, params={"limit": PAGE_SIZE, "offset": offset})
            rows = data.get("jobs", []) if isinstance(data, dict) else []
            if not rows:
                break

            for row in rows:
                try:
                    restrictions = row.get("locationRestrictions") or []
                    hires_from = ", ".join(restrictions) if restrictions else None
                    company = (row.get("companyName") or (row.get("company") or {}).get("name") or "")
                    jobs.append(
                        Job(
                            source="himalayas",
                            external_id=str(row.get("id") or row.get("guid") or row.get("slug") or row.get("applicationLink")),
                            title=row.get("title", ""),
                            company=company,
                            url=row.get("applicationLink") or row.get("url", ""),
                            description=row.get("description", "") or row.get("excerpt", ""),
                            location_raw=", ".join(restrictions) if restrictions else "Remote",
                            hires_remotely_from=hires_from,
                            job_type_raw=row.get("employmentType"),
                            posted_at=row.get("publishedAt") or row.get("pubDate"),
                            tags=row.get("categories", []) or [],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("himalayas: skipping malformed row (%s)", exc)

            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return jobs
