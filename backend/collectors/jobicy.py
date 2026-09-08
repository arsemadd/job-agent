"""Jobicy collector. Public remote-jobs API, no key required.

API: https://jobicy.com/api/v2/remote-jobs
Supports industry / tag filters — we query product and QA-adjacent industries.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://jobicy.com/api/v2/remote-jobs"
# Jobicy industry / tag query params (documented on jobicy.com/jobs-api)
QUERIES = [
    {"tag": "product"},
    {"tag": "qa"},
    {"industry": "business"},
]


class JobicyCollector(Collector):
    name = "jobicy"

    def fetch(self):
        seen = set()
        jobs = []
        for params in QUERIES:
            try:
                data = get_json(API_URL, params={**params, "count": 50})
            except Exception as exc:  # noqa: BLE001
                logger.debug("jobicy: query %s failed (%s)", params, exc)
                continue

            rows = data.get("jobs", []) if isinstance(data, dict) else []
            for row in rows:
                try:
                    jid = str(row.get("id") or row.get("url") or "")
                    if not jid or jid in seen:
                        continue
                    seen.add(jid)

                    jobs.append(
                        Job(
                            source="jobicy",
                            external_id=jid,
                            title=row.get("jobTitle") or row.get("title") or "",
                            company=row.get("companyName") or "Unknown",
                            url=row.get("url") or row.get("jobUrl") or "",
                            description=row.get("jobDescription") or row.get("jobExcerpt") or "",
                            location_raw=row.get("jobGeo") or "Remote",
                            salary_raw=row.get("annualSalaryMin") and (
                                f"{row.get('salaryCurrency', '')} {row.get('annualSalaryMin')}-{row.get('annualSalaryMax')}"
                            ).strip() or None,
                            job_type_raw=row.get("jobType")[0] if isinstance(row.get("jobType"), list) and row.get("jobType") else row.get("jobType"),
                            posted_at=row.get("pubDate"),
                            tags=row.get("jobIndustry") if isinstance(row.get("jobIndustry"), list) else [],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("jobicy: skipping malformed row (%s)", exc)
        return jobs
