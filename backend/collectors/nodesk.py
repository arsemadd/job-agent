"""NoDesk collector — public remote-jobs RSS."""
from __future__ import annotations

from backend.collectors.base import Collector, get_text
from backend.collectors.rss_common import jobs_from_rss
from backend.models import Job

FEED_URL = "https://nodesk.co/remote-jobs/index.xml"
PM_HINTS = ("product", "qa", "quality", "scrum", "test", "analyst", "owner", "program", "project")


class NoDeskCollector(Collector):
    name = "nodesk"

    def fetch(self):
        xml_text = get_text(FEED_URL)

        def map_item(fields: dict) -> Job | None:
            title = fields.get("title") or ""
            if not any(h in title.lower() for h in PM_HINTS):
                return None
            link = fields.get("link") or ""
            return Job(
                source="nodesk",
                external_id=link.rstrip("/").rsplit("/", 1)[-1] or link,
                title=title,
                company="Unknown",
                url=link,
                description=fields.get("description") or "",
                location_raw="Remote",
                posted_at=fields.get("pubDate"),
            )

        return jobs_from_rss(xml_text, source="nodesk", map_item=map_item)
