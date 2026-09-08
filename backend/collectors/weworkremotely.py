"""We Work Remotely collector. Public RSS, no key required.

WWR titles are formatted "Company: Job Title" by convention, and each <item>
usually carries a <region> element with the geographic eligibility statement
WWR asks posters to fill in - which is exactly the signal the location filter
needs, so we pull it out when present instead of relying on free-text guessing.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from backend.collectors.base import Collector, get_text, logger
from backend.models import Job

FEED_URL = "https://weworkremotely.com/remote-jobs.rss"


def _local(tag: str) -> str:
    """Strip an XML namespace, e.g. '{ns}region' -> 'region'."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


class WeWorkRemotelyCollector(Collector):
    name = "weworkremotely"

    def fetch(self):
        xml_text = get_text(FEED_URL)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("weworkremotely: could not parse RSS (%s)", exc)
            return []

        jobs = []
        for item in root.iter("item"):
            fields = {_local(child.tag): (child.text or "").strip() for child in item}
            raw_title = fields.get("title", "")
            link = fields.get("link", "")
            if not raw_title or not link:
                continue

            company, _, title = raw_title.partition(":")
            if not title:
                # title didn't follow the "Company: Title" convention
                company, title = "", raw_title
            else:
                title = title.strip()
                company = company.strip()

            region = fields.get("region", "")
            category = fields.get("category", "")
            external_id = link.rstrip("/").rsplit("/", 1)[-1]

            try:
                jobs.append(
                    Job(
                        source="weworkremotely",
                        external_id=external_id,
                        title=title or raw_title,
                        company=company or "Unknown",
                        url=link,
                        description=fields.get("description", ""),
                        location_raw=region or "Remote",
                        hires_remotely_from=region or None,
                        posted_at=fields.get("pubDate"),
                        tags=[category] if category else [],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("weworkremotely: skipping malformed item %s (%s)", link, exc)
        return jobs
