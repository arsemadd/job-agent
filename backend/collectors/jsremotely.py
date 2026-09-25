"""JS Remotely / javascript.jobs — remote JS roles listing."""
from __future__ import annotations

import re

from backend.collectors.base import Collector, get_text, logger
from backend.collectors.rss_common import jobs_from_rss
from backend.models import Job

FEED_CANDIDATES = [
    "https://javascript.jobs/remote/feed",
    "https://javascript.jobs/feed",
    "https://jsremotely.com/feed",
]
LISTING_URLS = [
    "https://javascript.jobs/remote",
    "https://jsremotely.com/",
]


class JSRemotelyCollector(Collector):
    name = "jsremotely"

    def fetch(self):
        for url in FEED_CANDIDATES:
            try:
                xml = get_text(url)
                if "<item" not in xml.lower() and "<entry" not in xml.lower():
                    continue
                jobs = jobs_from_rss(xml, source="jsremotely")
                if jobs:
                    return jobs
            except Exception as exc:  # noqa: BLE001
                logger.debug("jsremotely: feed %s failed (%s)", url, exc)

        jobs = []
        seen = set()
        for listing in LISTING_URLS:
            try:
                html = get_text(listing)
            except Exception as exc:  # noqa: BLE001
                logger.debug("jsremotely: listing %s failed (%s)", listing, exc)
                continue
            for match in re.finditer(
                r'href="(https?://(?:javascript\.jobs|jsremotely\.com)/[^"]+)"[^>]*>\s*([^<]{3,120})',
                html,
                re.I,
            ):
                url, title = match.group(1), re.sub(r"\s+", " ", match.group(2)).strip()
                if "/job" not in url.lower() and "/remote/" not in url.lower():
                    continue
                if url in seen or not title or "<" in title:
                    continue
                seen.add(url)
                jobs.append(
                    Job(
                        source="jsremotely",
                        external_id=url.rstrip("/").rsplit("/", 1)[-1],
                        title=title,
                        company="Unknown",
                        url=url,
                        location_raw="Remote",
                    )
                )
            if jobs:
                break
        return jobs
