"""4 Day Week collector — public JSON API, no key required.

Docs: https://4dayweek.io/developers
Uses v2 when available, falls back to v1 `/api/jobs`.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

V2_URL = "https://4dayweek.io/api/v2/jobs"
V1_URL = "https://4dayweek.io/api/jobs"
QUERIES = [
    {"q": "product", "work_arrangement": "remote"},
    {"q": "qa", "work_arrangement": "remote"},
    {"q": "scrum", "work_arrangement": "remote"},
    {"q": "analyst", "work_arrangement": "remote"},
]


class FourDayWeekCollector(Collector):
    name = "fourdayweek"

    def fetch(self):
        seen = set()
        jobs = []
        for params in QUERIES:
            try:
                data = get_json(V2_URL, params={**params, "limit": 50, "page": 1})
                rows = data.get("data") if isinstance(data, dict) else []
                if not rows:
                    data = get_json(V1_URL, params={"page": 1, "q": params.get("q")})
                    rows = data.get("jobs") if isinstance(data, dict) else []
            except Exception as exc:  # noqa: BLE001
                logger.debug("fourdayweek: query %s failed (%s)", params, exc)
                continue

            for row in rows or []:
                try:
                    jid = str(row.get("id") or row.get("slug") or row.get("url") or "")
                    if not jid or jid in seen:
                        continue
                    seen.add(jid)
                    company = row.get("company")
                    if isinstance(company, dict):
                        company_name = company.get("name") or "Unknown"
                    else:
                        company_name = company or row.get("company_name") or "Unknown"
                    location = row.get("location") or row.get("locations") or "Remote"
                    if isinstance(location, list):
                        location = ", ".join(str(x) for x in location[:3]) or "Remote"
                    url = row.get("url") or row.get("job_url") or (
                        f"https://4dayweek.io/jobs/{row.get('slug')}" if row.get("slug") else ""
                    )
                    jobs.append(
                        Job(
                            source="fourdayweek",
                            external_id=jid,
                            title=row.get("title") or "",
                            company=company_name,
                            url=url,
                            description=row.get("description") or row.get("description_text") or "",
                            location_raw=str(location),
                            job_type_raw=row.get("schedule_type") or row.get("employment_type"),
                            posted_at=row.get("posted_at") or row.get("created_at"),
                            tags=row.get("skills") if isinstance(row.get("skills"), list) else [],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("fourdayweek: skipping malformed row (%s)", exc)
        return jobs
