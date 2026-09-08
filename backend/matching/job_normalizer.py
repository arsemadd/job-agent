"""Renders a Job + its hard-filter context into the compact text block the
AI matcher reads. Keeps prompts small and consistent across sources whose
descriptions range from a few lines to several thousand words of HTML-turned-text."""
from __future__ import annotations

from backend.filters.pipeline import HardFilterVerdict
from backend.models import Job

MAX_DESCRIPTION_CHARS = 6000


def render_job_context(job: Job, verdict: HardFilterVerdict) -> str:
    lines = []
    lines.append(f"Title: {job.title}")
    lines.append(f"Company: {job.company}")
    lines.append(f"Source: {job.source}")
    lines.append(f"Location as posted: {job.location_raw or 'not stated'}")
    if job.hires_remotely_from:
        lines.append(f"Explicit hiring-eligibility field: {job.hires_remotely_from}")
    lines.append(f"Location eligibility tier (pre-computed, deterministic): {verdict.location_tier}")
    if verdict.years_required is not None:
        lines.append(f"Years of experience required (pre-computed from posting text): {verdict.years_required}")
    else:
        lines.append("Years of experience required: not clearly stated in posting")
    if verdict.needs_realism_check:
        lines.append(
            "FLAG: this posting states 5-6 years required, which is above the candidate's target "
            "band but not an automatic reject. Judge explicitly whether the actual responsibilities "
            "described are realistic for ~3.5 years of relevant experience, and say so in your reasoning."
        )
    if job.job_type_raw:
        lines.append(f"Job type: {job.job_type_raw}")
    if job.salary_raw:
        lines.append(f"Salary as posted: {job.salary_raw}")
    if job.tags:
        lines.append(f"Tags: {', '.join(str(t) for t in job.tags)}")
    lines.append("")
    lines.append("Full posting text:")
    desc = job.description or "(no description text provided by source)"
    if len(desc) > MAX_DESCRIPTION_CHARS:
        desc = desc[:MAX_DESCRIPTION_CHARS] + "\n...[truncated]"
    lines.append(desc)
    return "\n".join(lines)
