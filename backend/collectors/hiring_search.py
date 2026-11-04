"""Automated hiring-signal search (LinkedIn posts via Google — never scrape LinkedIn).

What this does
--------------
1. Builds ready-to-open Google / LinkedIn Posts / People search URLs for the
   candidate's daily job-search routine (PM hiring posts, founders, recruiters).
2. When SERPER_API_KEY (or SERPAPI_KEY) is set, runs those Google queries and
   turns fresh organic hits into Job leads the pipeline can alert on.

LinkedIn itself is never scraped (ToS + brittle). Google `site:linkedin.com/posts`
is the reliable automation path.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any
from urllib.parse import quote_plus, urlencode

import requests

from backend.collectors.base import Collector, USER_AGENT, DEFAULT_TIMEOUT, logger
from backend.models import Job

# ---------------------------------------------------------------------------
# Default search packs (overridable via preferences.json → hiring_search)
# ---------------------------------------------------------------------------

DEFAULT_GOOGLE_QUERIES = [
    'site:linkedin.com/posts "Product Manager" "hiring" remote',
    'site:linkedin.com/posts "Technical Product Manager" hiring',
    'site:linkedin.com/posts "Product Owner" "we are hiring"',
    'site:linkedin.com/posts "fractional product manager"',
    'site:linkedin.com/posts "Founder" "hiring Product Manager"',
    'site:linkedin.com/posts "CEO" "looking for Product Manager"',
    'site:linkedin.com/posts "CTO" "hiring" "remote" "Product Manager"',
    'site:linkedin.com/posts "Startup" "hiring product team"',
    'site:linkedin.com/posts "Looking for a freelance Product Manager"',
    'site:linkedin.com/posts "QA" OR "Product Analyst" "hiring" remote',
    'site:linkedin.com/posts "Head of Product" "hiring" remote',
    'site:linkedin.com/posts "we\'re hiring" "Product Manager" "remote" -"US only" -"United States only"',
]

DEFAULT_LINKEDIN_POST_QUERIES = [
    "Founder hiring Product Manager",
    "CEO looking for Product Manager",
    "CTO hiring remote PM",
    "Startup hiring product team",
    "Looking for a freelance Product Manager",
    "hiring Technical Product Manager remote",
    "hiring Product Owner remote",
    "we're hiring Product Manager worldwide",
]

DEFAULT_PEOPLE_QUERIES = [
    "Startup founder hiring product",
    "Head of Product",
    "VP of Product",
    "Talent Acquisition Manager product",
    "Technical Recruiter Product Manager remote",
    "Founder B2B SaaS",
    "Founder AI product company",
]

DEFAULT_INDUSTRIES = [
    "B2B SaaS startups",
    "AI product companies",
    "ERP and business software companies",
    "Developer tools companies",
    "Healthcare technology startups",
    "Remote-first startups hiring internationally",
]

US_ONLY_RE = re.compile(
    r"\b(?:us only|u\.s\. only|usa only|united states only|must be (?:in|based in) the (?:us|u\.s\.|united states))\b",
    re.I,
)
HYBRID_RE = re.compile(r"\b(?:hybrid|on[- ]?site|in[- ]office)\b", re.I)
REMOTE_RE = re.compile(r"\b(?:remote|worldwide|work from anywhere|distributed|global)\b", re.I)
PM_RE = re.compile(
    r"\b(?:product manager|technical product manager|product owner|tpm|product analyst|"
    r"qa (?:analyst|engineer)|scrum master|program manager)\b",
    re.I,
)
HIRING_RE = re.compile(
    r"\b(?:hiring|we(?:'re| are) hiring|looking for|join (?:our|my) team|open role|now hiring)\b",
    re.I,
)


def google_search_url(query: str) -> str:
    return f"https://www.google.com/search?{urlencode({'q': query, 'tbs': 'qdr:w'})}"


def linkedin_posts_search_url(query: str) -> str:
    # LinkedIn content search — opens Posts tab when possible
    return f"https://www.linkedin.com/search/results/content/?{urlencode({'keywords': query, 'origin': 'GLOBAL_SEARCH_HEADER'})}"


def linkedin_people_search_url(query: str) -> str:
    return f"https://www.linkedin.com/search/results/people/?{urlencode({'keywords': query, 'origin': 'GLOBAL_SEARCH_HEADER'})}"


def linkedin_jobs_search_url(query: str, remote_only: bool = True) -> str:
    params: dict[str, str] = {"keywords": query}
    if remote_only:
        params["f_WT"] = "2"
    return f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"


def build_hiring_search_pack(prefs: dict | None = None) -> dict[str, Any]:
    """Structured search pack for dashboard + Discord (no API key required)."""
    hs = (prefs or {}).get("hiring_search", {}) if prefs else {}
    google_q = hs.get("google_queries") or DEFAULT_GOOGLE_QUERIES
    post_q = hs.get("linkedin_post_queries") or DEFAULT_LINKEDIN_POST_QUERIES
    people_q = hs.get("people_queries") or DEFAULT_PEOPLE_QUERIES
    industries = hs.get("industries") or DEFAULT_INDUSTRIES
    formal_roles = hs.get("formal_vacancy_queries") or [
        "Product Manager remote",
        "Technical Product Manager remote",
        "Product Owner remote",
        "QA Analyst remote",
    ]

    return {
        "industries_monitored": industries,
        "routine_minutes": {
            "linkedin_posts": 15,
            "formal_vacancies": 10,
            "founders_hiring_managers": 10,
            "company_career_pages": 10,
            "apply_or_contact": 15,
        },
        "google_searches": [
            {"query": q, "url": google_search_url(q), "note": "Past week · LinkedIn posts via Google"}
            for q in google_q
        ],
        "linkedin_post_searches": [
            {"query": q, "url": linkedin_posts_search_url(q)}
            for q in post_q
        ],
        "people_searches": [
            {"query": q, "url": linkedin_people_search_url(q), "note": "Founders / HoP / TA / recruiters"}
            for q in people_q
        ],
        "formal_vacancy_searches": [
            {"query": q, "url": linkedin_jobs_search_url(q, remote_only=True)}
            for q in formal_roles
        ],
        "automation": {
            "live_fetch": bool(
                (os.environ.get("SERPER_API_KEY") or os.environ.get("SERPAPI_KEY") or "").strip()
            ),
            "provider": (
                "serper" if (os.environ.get("SERPER_API_KEY") or "").strip()
                else ("serpapi" if (os.environ.get("SERPAPI_KEY") or "").strip() else None)
            ),
            "note": (
                "Set SERPER_API_KEY (serper.dev) or SERPAPI_KEY to auto-fetch Google results "
                "into Discord. Without a key, searches are generated as clickable packs only."
            ),
        },
    }


def score_hiring_lead(title: str, snippet: str) -> tuple[int, list[str], list[str]]:
    """Cheap keyword score for hiring posts (no AI). Returns score, why, gaps."""
    text = f"{title}\n{snippet}"
    why: list[str] = []
    gaps: list[str] = []
    score = 0

    if HYBRID_RE.search(text) or US_ONLY_RE.search(text):
        return 0, [], ["Hybrid or country-restricted — skip"]

    if PM_RE.search(text):
        score += 40
        why.append("Mentions a PM / Product / QA-style role")
    if HIRING_RE.search(text):
        score += 25
        why.append("Hiring / looking-for language")
    if REMOTE_RE.search(text):
        score += 20
        why.append("Remote / global signal")
    else:
        gaps.append("Remote eligibility not clear from snippet — verify before applying")
        score += 5

    if re.search(r"\b(?:founder|ceo|cto|head of product|vp of product)\b", text, re.I):
        score += 10
        why.append("Posted by / mentions founder or product leadership")

    score = min(100, score)
    if not why:
        gaps.append("Weak PM/hiring signal in snippet")
    return score, why, gaps


def _serper_search(query: str, api_key: str, num: int = 8) -> list[dict]:
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json", "User-Agent": USER_AGENT},
        json={"q": query, "num": num, "tbs": "qdr:w"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return list(data.get("organic") or [])


def _serpapi_search(query: str, api_key: str, num: int = 8) -> list[dict]:
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "api_key": api_key, "num": num, "tbs": "qdr:w"},
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return list(data.get("organic_results") or [])


def _row_to_job(row: dict, query: str) -> Job | None:
    title = (row.get("title") or "").strip()
    link = (row.get("link") or row.get("url") or "").strip()
    snippet = (row.get("snippet") or row.get("description") or "").strip()
    if not title or not link:
        return None
    # Prefer LinkedIn post / company URLs; skip pure Google junk
    if "linkedin.com" not in link.lower() and "jobs." not in link.lower():
        # Still keep strong hiring hits from company blogs / news
        if not HIRING_RE.search(f"{title} {snippet}"):
            return None

    company = "LinkedIn hiring post"
    # "Jane Doe - Founder at Acme | ..." patterns
    m = re.search(r"\bat\s+([A-Z][\w.&'\- ]{1,40})(?:\s*[|\-–]|$)", title)
    if m:
        company = m.group(1).strip()

    external_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
    loc = "Remote" if REMOTE_RE.search(f"{title} {snippet}") else "Unclear — verify"
    return Job(
        source="hiring_search",
        external_id=external_id,
        title=title[:180],
        company=company[:80],
        url=link,
        description=f"Search query: {query}\n\n{snippet}",
        location_raw=loc,
        tags=["hiring_signal", "linkedin_post"],
    )


class HiringSearchCollector(Collector):
    """Fetches Google results for LinkedIn hiring-post queries when an API key is set."""

    name = "hiring_search"

    def __init__(self, prefs: dict | None = None):
        self.prefs = prefs or {}

    def fetch(self):
        hs = self.prefs.get("hiring_search", {})
        if hs.get("enabled", True) is False:
            return []

        serper = (os.environ.get("SERPER_API_KEY") or "").strip()
        serpapi = (os.environ.get("SERPAPI_KEY") or "").strip()
        if not serper and not serpapi:
            logger.info(
                "hiring_search: no SERPER_API_KEY/SERPAPI_KEY — skipping live fetch "
                "(search pack still available via /api/discovery)"
            )
            return []

        queries = list(hs.get("google_queries") or DEFAULT_GOOGLE_QUERIES)
        max_queries = int(hs.get("max_queries_per_run", 8) or 8)
        queries = queries[:max_queries]
        per_query = int(hs.get("results_per_query", 6) or 6)

        jobs: list[Job] = []
        seen_urls: set[str] = set()
        for q in queries:
            try:
                rows = (
                    _serper_search(q, serper, num=per_query)
                    if serper
                    else _serpapi_search(q, serpapi, num=per_query)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("hiring_search: query failed (%s): %s", q[:60], exc)
                continue
            for row in rows:
                job = _row_to_job(row, q)
                if not job or job.url in seen_urls:
                    continue
                seen_urls.add(job.url)
                jobs.append(job)
        return jobs
