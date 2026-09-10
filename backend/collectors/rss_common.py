"""Shared RSS → Job helpers used by several board collectors."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable

from backend.collectors.base import logger
from backend.models import Job


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_rss_items(xml_text: str) -> list[dict]:
    # ElementTree rejects many HTML entities found in real-world feeds.
    cleaned = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", xml_text)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        logger.warning("rss: could not parse feed (%s)", exc)
        return []

    items = []
    for item in root.iter("item"):
        fields = {_local(child.tag): (child.text or "").strip() for child in item}
        # Atom-style link href fallback
        if not fields.get("link"):
            for child in item:
                if _local(child.tag) == "link" and child.attrib.get("href"):
                    fields["link"] = child.attrib["href"].strip()
                    break
        if fields.get("title") and fields.get("link"):
            items.append(fields)
    return items


def jobs_from_rss(
    xml_text: str,
    *,
    source: str,
    company_title_split: bool = False,
    map_item: Callable[[dict], Job | None] | None = None,
) -> list[Job]:
    jobs: list[Job] = []
    for fields in parse_rss_items(xml_text):
        try:
            if map_item:
                job = map_item(fields)
                if job:
                    jobs.append(job)
                continue

            raw_title = fields.get("title", "")
            link = fields.get("link", "")
            company, title = "", raw_title
            if company_title_split and ":" in raw_title:
                company, _, title = raw_title.partition(":")
                company, title = company.strip(), title.strip()
            elif " at " in raw_title:
                title, _, company = raw_title.rpartition(" at ")
                title, company = title.strip(), company.strip()

            external_id = link.rstrip("/").rsplit("/", 1)[-1] or link
            jobs.append(
                Job(
                    source=source,
                    external_id=external_id,
                    title=title or raw_title,
                    company=company or "Unknown",
                    url=link,
                    description=fields.get("description", "") or fields.get("content", ""),
                    location_raw=fields.get("category") or "Remote",
                    posted_at=fields.get("pubDate"),
                    tags=[fields["category"]] if fields.get("category") else [],
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s: skipping malformed RSS item (%s)", source, exc)
    return jobs
