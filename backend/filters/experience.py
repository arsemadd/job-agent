"""Experience/seniority hard filter.

Deterministic, not AI-judged, per the flowchart in the brief: this runs
BEFORE the AI matcher so a model can't decide an 8-year Staff PM role is
"basically a match" on skills overlap alone.

Rule:
  - years required >= hard_reject_years (default 7)              -> REJECT
  - title carries a reject-seniority word (Senior/Lead/Principal/
    Director/VP/Head/Staff) and isn't a listed QA exception        -> REJECT
  - years required in the 5-6 zone (not >= hard_reject_years)      -> PASS,
    but flagged so the AI matcher explicitly judges whether the
    responsibilities are realistic (can come back as a lower-
    confidence SEND rather than an auto-reject)
  - otherwise                                                       -> PASS
"""
from __future__ import annotations

import re

from backend.filters.result import FilterResult

# Ordered loosely by how explicit the phrasing is; first match wins.
_YEAR_PATTERNS = [
    re.compile(r"(\d{1,2})\s*\+\s*years?", re.I),
    re.compile(r"(\d{1,2})\s*-\s*(\d{1,2})\s*years?", re.I),
    re.compile(r"(?:minimum of|at least|min\.?)\s*(\d{1,2})\s*years?", re.I),
    re.compile(r"(\d{1,2})\s*to\s*(\d{1,2})\s*years?", re.I),
    # Allows a short descriptive phrase between "X years" and "experience",
    # e.g. "5 years of B2B SaaS product management experience required" -
    # not just the tight "X years of experience" phrasing.
    re.compile(r"(\d{1,2})\+?\s*years?(?:\s+of)?(?:\s+[A-Za-z][\w&/\-]{0,20}){0,6}\s+experience", re.I),
]


def extract_min_years(text: str) -> int | None:
    """Best-effort extraction of the minimum years-of-experience requirement.
    Returns None when nothing resembling a years-of-experience statement is found -
    callers must treat that as 'unknown', not zero.

    Patterns are tried in priority order (most specific/explicit first) and
    the first pattern type that matches wins - the patterns are intentionally
    NOT merged across types, because a generic trailing pattern like
    "N years ... experience" can spuriously re-match a number that a more
    specific pattern (e.g. a "2-4 years" range) already accounted for,
    inflating the detected minimum.
    """
    if not text:
        return None
    for pattern in _YEAR_PATTERNS:
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        candidates = []
        for m in matches:
            nums = [int(g) for g in m.groups() if g and g.isdigit()]
            if nums:
                candidates.append(min(nums))
        if candidates:
            # Multiple matches of the SAME pattern type (e.g. "2-4 years for
            # this level, 5+ for senior track") - be conservative and flag
            # the higher requirement rather than under-detect it.
            return max(candidates)
    return None


def check_experience(title: str, description: str, prefs: dict) -> FilterResult:
    exp_prefs = prefs.get("experience", {})
    hard_reject_years = exp_prefs.get("hard_reject_years", 7)
    reject_titles = [t.lower() for t in exp_prefs.get("reject_seniority_titles", [])]
    exceptions = [t.lower() for t in exp_prefs.get("seniority_title_exceptions", [])]

    t = (title or "").lower()
    years = extract_min_years(f"{title}\n{description}")

    is_exception = any(exc in t for exc in exceptions)
    has_reject_title = (not is_exception) and any(
        re.search(rf"\b{re.escape(word)}\b", t) for word in reject_titles
    )

    if years is not None and years >= hard_reject_years:
        return FilterResult(
            False, f"requires {years}+ years (reject threshold is {hard_reject_years})",
            detail={"years_required": years},
        )

    if has_reject_title:
        return FilterResult(
            False, "title carries a senior/lead/principal-level qualifier",
            detail={"years_required": years},
        )

    if years is not None and years >= 5:
        return FilterResult(
            True, f"requires {years} years - not an auto-reject, flagged for AI to judge realism",
            detail={"years_required": years, "needs_realism_check": True},
        )

    return FilterResult(True, "experience requirement within target range or unstated", detail={"years_required": years})
