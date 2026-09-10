"""Remote First Jobs collector — public category RSS feeds."""
from __future__ import annotations

from backend.collectors.base import Collector, get_text, logger
from backend.collectors.rss_common import jobs_from_rss

FEED_TMPL = "https://remotefirstjobs.com/rss/jobs/{slug}.rss"
SLUGS = ("product", "qa", "project-management", "business-analyst")


class RemoteFirstJobsCollector(Collector):
    name = "remotefirstjobs"

    def fetch(self):
        jobs = []
        seen = set()
        for slug in SLUGS:
            try:
                xml_text = get_text(FEED_TMPL.format(slug=slug))
            except Exception as exc:  # noqa: BLE001
                logger.debug("remotefirstjobs: feed %s failed (%s)", slug, exc)
                continue
            for job in jobs_from_rss(xml_text, source="remotefirstjobs"):
                if job.external_id in seen:
                    continue
                seen.add(job.external_id)
                job.tags = list(job.tags or []) + [slug]
                jobs.append(job)
        return jobs
