"""LinkedIn discovery helper.

By design this never scrapes LinkedIn. It only builds LinkedIn's own public
search URLs for your target roles so you (or the dashboard) can open the real
listing yourself - discovery, not a bot copying LinkedIn's data. It returns
plain search-link dicts, not Job objects, and is not wired into the AI-scoring
pipeline: there is nothing to score until a human opens the link and reads a
real posting.
"""
from __future__ import annotations

from urllib.parse import urlencode

BASE_URL = "https://www.linkedin.com/jobs/search/"


def build_search_links(roles: list[str], remote_only: bool = True) -> list[dict]:
    """One LinkedIn job-search URL per role, for quick manual browsing."""
    links = []
    for role in roles:
        params = {"keywords": role}
        if remote_only:
            params["f_WT"] = "2"  # LinkedIn's own "Remote" work-type filter
        links.append({"role": role, "url": f"{BASE_URL}?{urlencode(params)}"})
    return links
