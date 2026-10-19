"""Config-driven RSS board collector.

Add entries under preferences.json → sources.rss_boards:
  { "name": "justremote", "url": "https://...", "pm_filter": true }

Each feed becomes jobs with source=<name>. Failures are skipped per feed.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_text, logger
from backend.collectors.rss_common import jobs_from_rss
from backend.models import Job

PM_HINTS = (
    "product",
    "qa",
    "quality",
    "scrum",
    "test",
    "analyst",
    "owner",
    "program",
    "project",
    "delivery",
    "implementation",
    "customer success",
    "business analyst",
)


class RssBoardsCollector(Collector):
    name = "rss_boards"

    def __init__(self, feeds: list[dict] | None = None):
        self.feeds = [f for f in (feeds or []) if (f or {}).get("url") and (f or {}).get("name")]

    def fetch(self):
        jobs: list[Job] = []
        for feed in self.feeds:
            name = str(feed["name"]).strip().lower().replace(" ", "_")
            url = str(feed["url"]).strip()
            pm_filter = bool(feed.get("pm_filter", True))
            try:
                xml_text = get_text(url)
            except Exception as exc:  # noqa: BLE001
                logger.debug("rss_boards: feed %s failed (%s)", name, exc)
                continue

            def map_item(fields: dict, *, source_name: str = name, filter_pm: bool = pm_filter) -> Job | None:
                raw_title = fields.get("title") or ""
                blob = f"{raw_title} {fields.get('description', '')}".lower()
                if filter_pm and not any(h in blob for h in PM_HINTS):
                    return None
                link = fields.get("link") or ""
                title, company = raw_title, ""
                if " at " in raw_title:
                    title, _, company = raw_title.rpartition(" at ")
                elif ":" in raw_title and len(raw_title.split(":", 1)[0]) < 40:
                    company, _, title = raw_title.partition(":")
                return Job(
                    source=source_name,
                    external_id=link.rstrip("/").rsplit("/", 1)[-1] or link,
                    title=title.strip() or raw_title,
                    company=company.strip() or "Unknown",
                    url=link,
                    description=fields.get("description") or "",
                    location_raw=fields.get("category") or "Remote",
                    posted_at=fields.get("pubDate"),
                    tags=[fields["category"]] if fields.get("category") else [],
                )

            jobs.extend(jobs_from_rss(xml_text, source=name, map_item=map_item))
        return jobs
