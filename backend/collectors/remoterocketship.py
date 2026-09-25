"""Remote Rocketship — optional API key collector.

Set REMOTE_ROCKETSHIP_API_KEY to enable live fetch. Without a key the collector
returns [] so the pipeline stays green; the board still appears in Discovery.
Docs: https://www.remoterocketship.com/api-docs/
"""
from __future__ import annotations

import os

import requests

from backend.collectors.base import Collector, USER_AGENT, DEFAULT_TIMEOUT, logger
from backend.models import Job

API_URL = "https://www.remoterocketship.com/api/openclaw/jobs"

TITLE_FILTERS = [
    "Product Manager",
    "Product Owner",
    "QA",
    "Quality Assurance",
    "Scrum Master",
    "Program Manager",
    "Business Analyst",
]


class RemoteRocketshipCollector(Collector):
    name = "remoterocketship"

    def fetch(self):
        api_key = (os.environ.get("REMOTE_ROCKETSHIP_API_KEY") or "").strip()
        if not api_key:
            logger.info("remoterocketship: no REMOTE_ROCKETSHIP_API_KEY — skipping live fetch")
            return []

        payload = {
            "filters": {
                "page": 1,
                "itemsPerPage": 50,
                "jobTitleFilters": TITLE_FILTERS,
                "showRemoteJobs": True,
                "showHybridJobs": False,
                "showOnsiteJobs": False,
                "sortBy": "DateAdded",
            },
            "includeJobDescription": True,
        }
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("jobs") or data.get("data") or data.get("results") or []
        if isinstance(data, list):
            rows = data

        jobs = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = row.get("title") or row.get("jobTitle") or ""
            company = row.get("company") or row.get("companyName") or "Unknown"
            url = row.get("url") or row.get("applyUrl") or row.get("link") or ""
            if not title or not url:
                continue
            rid = str(row.get("id") or url.rstrip("/").rsplit("/", 1)[-1])
            location = (
                row.get("location")
                or row.get("locations")
                or row.get("candidateLocation")
                or "Remote"
            )
            if isinstance(location, list):
                location = ", ".join(str(x) for x in location)
            jobs.append(
                Job(
                    source="remoterocketship",
                    external_id=rid,
                    title=title,
                    company=company if isinstance(company, str) else str(company),
                    url=url,
                    description=row.get("description") or row.get("jobDescription") or "",
                    location_raw=str(location) or "Remote",
                    salary_raw=row.get("salary") or None,
                    job_type_raw=row.get("employmentType") or row.get("jobType"),
                    posted_at=row.get("dateAdded") or row.get("postedAt"),
                    tags=row.get("tags") or [],
                )
            )
        return jobs
