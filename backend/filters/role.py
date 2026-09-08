"""Soft role pre-filter.

This exists purely to avoid burning AI calls on titles that are obviously
unrelated (e.g. "Backend Engineer", "Account Executive"). It is deliberately
permissive: a title not on the include list still PASSES unless it hits an
exclude keyword, because the real judgment call ("is this actually a
PM/QA-adjacent role the AI should evaluate") belongs to the AI matcher, not a
keyword list. This filter only removes near-certain noise.
"""
from __future__ import annotations

from backend.filters.result import FilterResult


def check_role(title: str, prefs: dict) -> FilterResult:
    role_prefs = prefs.get("roles", {})
    include = [r.lower() for r in role_prefs.get("include", [])]
    exclude = [r.lower() for r in role_prefs.get("exclude_keywords", [])]
    t = (title or "").lower()

    for kw in exclude:
        if kw in t:
            # a title can contain both an include and exclude term
            # (e.g. "Software Engineer in Test" vs "Software Engineer") -
            # if any include keyword also matches, let it through to the AI.
            if any(inc in t for inc in include):
                continue
            return FilterResult(False, f"title matches exclude keyword '{kw}'")

    if any(inc in t for inc in include):
        return FilterResult(True, "title matches an included role keyword")

    # Not an obvious match either way - don't hard-reject on title alone.
    # Let it through so the AI can judge titles the keyword list didn't anticipate
    # (the brief explicitly wants "related titles the AI identifies as relevant").
    return FilterResult(True, "title not on include list, but not excluded - deferring to AI judgment")
