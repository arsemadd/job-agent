"""Mind the Product jobs collector.

Public JSON list endpoint used by their Next.js board (no API key):
  GET https://www.mindtheproduct.com/api/jobs/list?page=&pageSize=

Product-management focused board — titles skew PM / product design / growth.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://www.mindtheproduct.com/api/jobs/list"
LISTING_BASE = "https://www.mindtheproduct.com/jobs/listing"
PAGE_SIZE = 50
MAX_PAGES = 5


class MindTheProductCollector(Collector):
    name = "mindtheproduct"

    def fetch(self):
        jobs = []
        for page in range(1, MAX_PAGES + 1):
            try:
                data = get_json(API_URL, params={"page": page, "pageSize": PAGE_SIZE})
            except Exception as exc:  # noqa: BLE001
                logger.debug("mindtheproduct: page %s failed (%s)", page, exc)
                break

            rows = data.get("jobs", []) if isinstance(data, dict) else []
            if not rows:
                break

            for row in rows:
                try:
                    slug = row.get("slug") or row.get("id")
                    if not slug:
                        continue
                    remote = bool(row.get("remote"))
                    location = (row.get("location") or "").strip()
                    if remote and location and "remote" not in location.lower():
                        location_raw = f"Remote · {location}"
                    elif remote:
                        location_raw = location or "Remote"
                    else:
                        location_raw = location or "Not specified"

                    salary = row.get("salary")
                    if not salary and (row.get("salaryMin") or row.get("salaryMax")):
                        currency = row.get("salaryCurrency") or ""
                        lo, hi = row.get("salaryMin"), row.get("salaryMax")
                        salary = f"{currency} {lo or '?'}-{hi or '?'}".strip()

                    url = row.get("applicationUrl") or f"{LISTING_BASE}/{slug}/"
                    tags = list(row.get("tags") or [])
                    if row.get("seniority"):
                        tags.append(str(row["seniority"]))

                    jobs.append(
                        Job(
                            source="mindtheproduct",
                            external_id=str(row.get("id") or slug),
                            title=row.get("title", ""),
                            company=row.get("company", "") or "Unknown",
                            url=url,
                            description=row.get("description", "") or "",
                            location_raw=location_raw,
                            salary_raw=salary or None,
                            job_type_raw=row.get("type"),
                            posted_at=row.get("publishedAt"),
                            tags=tags,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("mindtheproduct: skipping malformed row (%s)", exc)

            if not data.get("hasMore"):
                break
        return jobs
