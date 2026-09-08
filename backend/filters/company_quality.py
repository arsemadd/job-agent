"""Lightweight company/posting quality checks.

Deliberately cheap (no outbound calls per job - that would be slow and easy
to rate-limit) - just the checks from the brief that don't require hitting
the company's own website: does the posting name a real company, and does it
have somewhere to apply.
"""
from __future__ import annotations

from backend.filters.result import FilterResult


def check_company_quality(company: str, url: str, prefs: dict) -> FilterResult:
    cq = prefs.get("company_quality", {})
    generic = [g.lower() for g in cq.get("reject_generic_company_names", [])]
    require_link = cq.get("require_apply_link", True)

    c = (company or "").strip().lower()
    if not c:
        return FilterResult(False, "no company name on posting")
    if c in generic:
        return FilterResult(False, f"generic/placeholder company name ('{company}')")
    if require_link and not (url or "").strip():
        return FilterResult(False, "no application link on posting")
    return FilterResult(True, "company/posting looks legitimate")
