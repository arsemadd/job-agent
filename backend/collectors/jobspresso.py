"""Jobspresso collector — public WP job_listing RSS."""
from __future__ import annotations

from backend.collectors.base import Collector, get_text
from backend.collectors.rss_common import jobs_from_rss
from backend.models import Job

FEED_URL = "https://www.jobspresso.co/feed/?post_type=job_listing"
PM_HINTS = ("product", "qa", "quality", "scrum", "test", "analyst", "owner", "program", "project")


class JobspressoCollector(Collector):
    name = "jobspresso"

    def fetch(self):
        xml_text = get_text(FEED_URL)

        def map_item(fields: dict) -> Job | None:
            raw_title = fields.get("title") or ""
            blob = f"{raw_title} {fields.get('description', '')}".lower()
            if not any(h in blob for h in PM_HINTS):
                return None
            link = fields.get("link") or ""
            title, company = raw_title, ""
            if " at " in raw_title:
                title, _, company = raw_title.rpartition(" at ")
            return Job(
                source="jobspresso",
                external_id=link.rstrip("/").rsplit("/", 1)[-1] or link,
                title=title.strip(),
                company=company.strip() or "Unknown",
                url=link,
                description=fields.get("description") or "",
                location_raw="Remote",
                posted_at=fields.get("pubDate"),
            )

        return jobs_from_rss(xml_text, source="jobspresso", map_item=map_item)
