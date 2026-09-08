from __future__ import annotations

from backend.filters.result import FilterResult


def check_job_type(job_type_raw: str | None, title: str, description: str, prefs: dict) -> FilterResult:
    jt_prefs = prefs.get("job_type", {})
    reject = [r.lower() for r in jt_prefs.get("reject", [])]
    text = f"{job_type_raw or ''} {title or ''}".lower()

    for kw in reject:
        if kw in text:
            return FilterResult(False, f"job type excluded ('{kw}')")
    return FilterResult(True, "job type acceptable or unstated")
