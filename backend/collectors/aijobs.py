"""AI Jobs board (theaijobboard.com) — RSS when published, else empty."""
from __future__ import annotations

from backend.collectors.base import Collector, get_text, logger
from backend.collectors.rss_common import jobs_from_rss

FEED_CANDIDATES = [
    "https://theaijobboard.com/jobs.rss",
    "https://theaijobboard.com/feed",
    "https://theaijobboard.com/rss.xml",
]


class AIJobsCollector(Collector):
    name = "aijobs"

    def fetch(self):
        last_err = None
        for url in FEED_CANDIDATES:
            try:
                xml = get_text(url)
                jobs = jobs_from_rss(xml, source="aijobs")
                if jobs:
                    return jobs
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.debug("aijobs: feed %s failed (%s)", url, exc)
        if last_err:
            raise last_err
        return []
