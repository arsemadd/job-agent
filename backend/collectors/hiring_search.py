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

# Prefer worldwide / work-from-anywhere; exclude US-only and senior/10yr noise in the query.
_EXCLUDE = (
    '-"US only" -"USA only" -"United States only" -"remote US" -"US remote" '
    '-"UK only" -"Canada only" -"EU only" -"10+ years" -"10 years" -"Senior Product Manager"'
)

DEFAULT_GOOGLE_QUERIES = [
    f'site:linkedin.com/posts "Product Manager" hiring (worldwide OR "work from anywhere" OR "remote worldwide") {_EXCLUDE}',
    f'site:linkedin.com/posts "Technical Product Manager" hiring (remote OR worldwide) {_EXCLUDE}',
    f'site:linkedin.com/posts "Product Owner" ("we are hiring" OR hiring) (remote OR worldwide) {_EXCLUDE}',
    f'site:linkedin.com/posts "Founder" "hiring Product Manager" (remote OR worldwide) {_EXCLUDE}',
    f'site:linkedin.com/posts "CEO" "Product Manager" (hiring OR "looking for") (remote OR worldwide) {_EXCLUDE}',
    f'site:linkedin.com/posts "CTO" "Product Manager" hiring remote {_EXCLUDE}',
    f'site:linkedin.com/posts "Startup" "hiring" "Product Manager" worldwide {_EXCLUDE}',
    f'site:linkedin.com/posts "freelance Product Manager" OR "fractional product manager" {_EXCLUDE}',
    f'site:linkedin.com/posts ("QA Analyst" OR "Product Analyst") hiring remote {_EXCLUDE}',
    f'site:linkedin.com/posts "we\'re hiring" "Product Manager" ("worldwide" OR "work from anywhere") {_EXCLUDE}',
]

DEFAULT_LINKEDIN_POST_QUERIES = [
    "Founder hiring Product Manager worldwide remote",
    "CEO looking for Product Manager work from anywhere",
    "CTO hiring remote Product Manager worldwide",
    "Startup hiring Product Manager remote worldwide",
    "Looking for a freelance Product Manager remote worldwide",
    "hiring Technical Product Manager remote worldwide",
    "hiring Product Owner remote worldwide",
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

COUNTRY_RESTRICT_RE = re.compile(
    r"\b(?:"
    r"us only|u\.s\. only|usa only|united states only|"
    r"remote[- ](?:us|usa|u\.s\.|united states|uk|canada|eu|europe|latam|apac|india)|"
    r"(?:us|usa|u\.s\.|uk|canada|eu|europe)[- ]remote|"
    r"uk only|canada only|eu only|europe only|latam only|apac only|"
    r"must be (?:in|based in|located in) the (?:us|u\.s\.|united states|uk|canada)|"
    r"based in the (?:us|u\.s\.|united states|uk|canada)|"
    r"us/canada|canada/us|us or canada|"
    r"authorized to work in the (?:us|u\.s\.|united states|uk)|"
    r"no visa sponsorship"
    r")\b",
    re.I,
)
HYBRID_RE = re.compile(r"\b(?:hybrid|on[- ]?site|in[- ]office)\b", re.I)
# Strict worldwide signal — plain "remote" alone is not enough for LinkedIn leads
WORLDWIDE_RE = re.compile(
    r"\b(?:"
    r"worldwide|work from anywhere|anywhere in the world|remote worldwide|"
    r"worldwide remote|global remote|remote[- ]global|location independent|"
    r"100%\s*remote(?:\s+worldwide)?|hire(?:s)?\s+anywhere|open (?:to )?all countries|"
    r"remote[- ]anywhere|from anywhere"
    r")\b",
    re.I,
)
REMOTE_RE = re.compile(r"\b(?:remote|worldwide|work from anywhere|distributed|global)\b", re.I)
YEARS_RE = re.compile(
    r"(\d+)\s*[+\-]?\s*(?:to\s*)?(\d+)?\s*\+?\s*years?(?:\s+of)?(?:\s+(?:experience|exp))?",
    re.I,
)
SENIOR_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|vp|head of|10\+|10 years|eight years|nine years)\b",
    re.I,
)
PM_RE = re.compile(
    r"\b(?:product manager|technical product manager|product owner|tpm|product analyst|"
    r"qa (?:analyst|engineer)|scrum master|program manager)\b",
    re.I,
)
HIRING_RE = re.compile(
    r"\b(?:hiring|we(?:'re| are) hiring|looking for|join (?:our|my) team|open role|now hiring)\b",
    re.I,
)

# Prefer mid-level: reject posts asking for more than this many years (default 5)
DEFAULT_MAX_YEARS = 5
DEFAULT_HARD_REJECT_YEARS = 7


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


def _extract_min_years(text: str) -> int | None:
    """Best-effort years ask from snippet. Uses high end when range is clearly senior (8+)."""
    found: list[int] = []
    for match in YEARS_RE.finditer(text or ""):
        lo = int(match.group(1))
        hi = int(match.group(2)) if match.group(2) else lo
        found.append(max(lo, hi) if hi >= 8 else lo)
    return max(found) if found else None


def score_hiring_lead(
    title: str,
    snippet: str,
    *,
    max_years: int = DEFAULT_MAX_YEARS,
    hard_reject_years: int = DEFAULT_HARD_REJECT_YEARS,
) -> tuple[int, list[str], list[str]]:
    """Score LinkedIn hiring posts. Worldwide remote only; reject ~10yr / senior asks."""
    text = f"{title}\n{snippet}"
    why: list[str] = []
    gaps: list[str] = []

    if HYBRID_RE.search(text):
        return 0, [], ["Hybrid / on-site — skip"]
    if COUNTRY_RESTRICT_RE.search(text):
        return 0, [], ["Country-restricted remote (US/UK/Canada/EU/etc.) — need worldwide"]

    if SENIOR_RE.search(title) and not re.search(r"\bsenior qa\b", title, re.I):
        return 0, [], ["Senior / staff / 10-year signal in title — skip"]

    years = _extract_min_years(text)
    if years is not None and years >= hard_reject_years:
        return 0, [], [f"Asks for {years}+ years (cap is under {hard_reject_years}; prefer ≤{max_years})"]
    if years is not None and years > max_years:
        return 0, [], [f"Asks for {years}+ years — prefer ≤{max_years} years, not 10-year senior roles"]

    # Must look worldwide — plain "remote" without global signal is not enough
    if not WORLDWIDE_RE.search(text):
        if REMOTE_RE.search(text):
            return 0, [], ["Says remote but not worldwide/global — skip US/region remote"]
        return 0, [], ["No worldwide / work-from-anywhere signal — skip"]

    score = 0
    if PM_RE.search(text):
        score += 40
        why.append("Mentions a PM / Product / QA-style role")
    if HIRING_RE.search(text):
        score += 25
        why.append("Hiring / looking-for language")
    score += 25
    why.append("Worldwide / work-from-anywhere remote")

    if years is not None:
        why.append(f"Experience stated around {years} years (≤{max_years} ok)")
        score += 5
    else:
        gaps.append("Years not stated in snippet — confirm ≤5 years on the post")

    if re.search(r"\b(?:founder|ceo|cto)\b", text, re.I):
        score += 5
        why.append("Posted by / mentions founder or exec")

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

    blob = f"{title} {snippet}"
    # Drop country-restricted / non-worldwide posts before they enter the store
    if COUNTRY_RESTRICT_RE.search(blob) or HYBRID_RE.search(blob):
        return None
    if not WORLDWIDE_RE.search(blob):
        return None
    years = _extract_min_years(blob)
    if years is not None and years > DEFAULT_MAX_YEARS:
        return None
    if SENIOR_RE.search(title) and not re.search(r"\bsenior qa\b", title, re.I):
        return None

    external_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
    return Job(
        source="hiring_search",
        external_id=external_id,
        title=title[:180],
        company=company[:80],
        url=link,
        description=f"Search query: {query}\n\n{snippet}",
        location_raw="Remote - Worldwide",
        tags=["hiring_signal", "linkedin_post", "worldwide"],
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
