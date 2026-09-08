"""LinkedIn + board discovery helpers.

By design this never scrapes LinkedIn. It only builds LinkedIn's own public
search URLs for target roles so you can open real listings yourself —
discovery, not a bot copying LinkedIn's data.

Also returns curated public board links (Mind the Product, Remotive, etc.)
for the dashboard Discovery panel.
"""
from __future__ import annotations

from urllib.parse import urlencode

LINKEDIN_BASE = "https://www.linkedin.com/jobs/search/"

BOARD_LINKS = [
    {
        "name": "Mind the Product",
        "url": "https://www.mindtheproduct.com/jobs/",
        "note": "Product management roles, refreshed daily",
    },
    {
        "name": "Remotive",
        "url": "https://remotive.com/remote-jobs/product",
        "note": "Remote product / PM category",
    },
    {
        "name": "We Work Remotely",
        "url": "https://weworkremotely.com/categories/remote-product-jobs",
        "note": "Remote product category",
    },
    {
        "name": "Himalayas",
        "url": "https://himalayas.app/jobs/product-manager",
        "note": "Remote PM listings with location restrictions",
    },
    {
        "name": "RemoteOK",
        "url": "https://remoteok.com/remote-product-jobs",
        "note": "Remote product-tagged jobs",
    },
    {
        "name": "Arbeitnow",
        "url": "https://www.arbeitnow.com/jobs?keywords=product+manager",
        "note": "EU / remote-friendly product search",
    },
    {
        "name": "Jobicy",
        "url": "https://jobicy.com/?remote_job_category=product",
        "note": "Remote product category",
    },
]


def build_search_links(roles: list[str], remote_only: bool = True, limit: int = 12) -> list[dict]:
    """One LinkedIn job-search URL per role, for quick manual browsing."""
    links = []
    for role in roles[:limit]:
        params: dict[str, str] = {"keywords": role}
        if remote_only:
            params["f_WT"] = "2"  # LinkedIn's own "Remote" work-type filter
        links.append({"role": role, "url": f"{LINKEDIN_BASE}?{urlencode(params)}"})
    return links


def build_discovery(roles: list[str], remote_only: bool = True) -> dict:
    return {
        "linkedin": build_search_links(roles, remote_only=remote_only),
        "boards": BOARD_LINKS,
    }
