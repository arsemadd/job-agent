"""Remote Woman collector — remote roles from remotewoman.com RSS/Atom when available."""
from __future__ import annotations

from backend.collectors.base import Collector, get_text, logger
from backend.collectors.rss_common import jobs_from_rss

FEED_CANDIDATES = [
    "https://remotewoman.com/feed",
    "https://remotewoman.com/jobs/feed",
    "https://remotewoman.com/rss",
]


class RemoteWomanCollector(Collector):
    name = "remotewoman"

    def fetch(self):
        last_err = None
        for url in FEED_CANDIDATES:
            try:
                xml = get_text(url)
                jobs = jobs_from_rss(xml, source="remotewoman", company_title_split=False)
                if jobs:
                    return jobs
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.debug("remotewoman: feed %s failed (%s)", url, exc)
        if last_err:
            raise last_err
        return []
