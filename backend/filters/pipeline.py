"""Runs every deterministic hard filter on a job and returns one combined verdict.

This is the "Hard eligibility" box in the brief's flowchart - everything here
runs BEFORE the AI matcher, and a REJECT here means the job never reaches the
AI (and never costs an API call). Order matters a little for the reason
string shown in the dashboard, but any failing filter short-circuits the rest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.filters.company_quality import check_company_quality
from backend.filters.experience import check_experience
from backend.filters.job_type import check_job_type
from backend.filters.location import classify_location
from backend.filters.role import check_role
from backend.models import Job


@dataclass
class HardFilterVerdict:
    passed: bool
    location_tier: str
    reasons: list[str] = field(default_factory=list)
    needs_realism_check: bool = False   # 5-6 yrs required - AI should judge explicitly
    years_required: int | None = None


def run_hard_filters(job: Job, prefs: dict) -> HardFilterVerdict:
    reasons = []

    company_res = check_company_quality(job.company, job.url, prefs)
    reasons.append(f"company_quality: {company_res.reason}")
    if not company_res.passed:
        return HardFilterVerdict(False, "N/A", reasons)

    role_res = check_role(job.title, prefs)
    reasons.append(f"role: {role_res.reason}")
    if not role_res.passed:
        return HardFilterVerdict(False, "N/A", reasons)

    loc_res = classify_location(job, prefs)
    reasons.append(f"location[{loc_res.tier}]: {loc_res.reason}")
    if not loc_res.passed:
        return HardFilterVerdict(False, loc_res.tier or "D_REJECT", reasons)

    jt_res = check_job_type(job.job_type_raw, job.title, job.description, prefs)
    reasons.append(f"job_type: {jt_res.reason}")
    if not jt_res.passed:
        return HardFilterVerdict(False, loc_res.tier, reasons)

    exp_res = check_experience(job.title, job.description, prefs)
    reasons.append(f"experience: {exp_res.reason}")
    if not exp_res.passed:
        return HardFilterVerdict(False, loc_res.tier, reasons, years_required=(exp_res.detail or {}).get("years_required"))

    needs_realism = bool((exp_res.detail or {}).get("needs_realism_check"))
    years_required = (exp_res.detail or {}).get("years_required")

    return HardFilterVerdict(True, loc_res.tier, reasons, needs_realism_check=needs_realism, years_required=years_required)
