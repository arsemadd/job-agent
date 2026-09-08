"""RemoteOK collector. Public JSON API, no key required.

API: https://remoteok.com/api -> JSON array. The first element is a legal/metadata
notice (no 'id' field) and must be skipped.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://remoteok.com/api"


class RemoteOKCollector(Collector):
    name = "remoteok"

    def fetch(self):
        data = get_json(API_URL)
        if not isinstance(data, list):
            logger.warning("remoteok: unexpected response shape")
            return []

        jobs = []
        for row in data:
            if not isinstance(row, dict) or "id" not in row or not row.get("position"):
                continue  # skip the legal-notice row and any malformed entries
            try:
                salary = None
                if row.get("salary_min") or row.get("salary_max"):
                    salary = f"{row.get('salary_min', '')}-{row.get('salary_max', '')}".strip("-")

                jobs.append(
                    Job(
                        source="remoteok",
                        external_id=str(row["id"]),
                        title=row.get("position", ""),
                        company=row.get("company", ""),
                        url=row.get("url") or row.get("apply_url") or f"https://remoteok.com/remote-jobs/{row['id']}",
                        description=row.get("description", ""),
                        location_raw=row.get("location", "") or "Remote",
                        salary_raw=salary,
                        posted_at=row.get("date"),
                        tags=row.get("tags", []) or [],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("remoteok: skipping malformed row %s (%s)", row.get("id"), exc)
        return jobs
