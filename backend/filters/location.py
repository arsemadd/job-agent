"""Location eligibility classifier.

Classifies every job into one of four tiers, in priority order:
  A - Worldwide / Anywhere / Global remote
  B - Africa / EMEA remote (candidate is explicitly eligible)
  C - "Remote" but eligibility isn't stated clearly enough to know
  D - Restricted to a region that excludes the candidate -> hard reject

This is the filter the brief calls out as most important: "remote" does not
mean "remote from anywhere." When a source exposes an explicit eligibility
field (Wellfound's "Hires Remotely From", Himalayas' locationRestrictions,
WWR's <region> tag - captured as Job.hires_remotely_from by the collectors),
that field is authoritative and is checked first, before falling back to
keyword matching over the free-text location/description.
"""
from __future__ import annotations

import re

from backend.filters.result import FilterResult
from backend.models import Job

TIER_A = "A_WORLDWIDE"
TIER_B = "B_AFRICA_EMEA"
TIER_C = "C_UNCLEAR"
TIER_D = "D_REJECT"


def _any_keyword(text: str, keywords: list[str]) -> str | None:
    t = text.lower()
    for kw in keywords:
        if kw.lower() in t:
            return kw
    return None


def classify_location(job: Job, prefs: dict) -> FilterResult:
    loc_prefs = prefs.get("location", {})
    tier_a_kw = loc_prefs.get("tier_a_worldwide_keywords", [])
    tier_b_kw = loc_prefs.get("tier_b_africa_emea_keywords", [])
    tier_d_kw = loc_prefs.get("tier_d_reject_keywords", [])

    explicit = (job.hires_remotely_from or "").strip()
    # Check restriction phrases anywhere: location field, explicit eligibility
    # field, and the first part of the description (where "must be located in..."
    # clauses often live even when the location line just says "Remote").
    combined = " | ".join(
        filter(None, [job.location_raw, explicit, (job.description or "")[:3000]])
    )

    d_hit = _any_keyword(combined, tier_d_kw)
    if d_hit:
        return FilterResult(
            False, f"location-restricted (matched '{d_hit}')", tier=TIER_D,
            detail={"matched_keyword": d_hit, "source_field": "explicit" if explicit else "text"},
        )

    a_hit = _any_keyword(explicit or job.location_raw, tier_a_kw)
    if a_hit:
        return FilterResult(True, f"worldwide-eligible (matched '{a_hit}')", tier=TIER_A)

    b_hit = _any_keyword(explicit or job.location_raw, tier_b_kw)
    if b_hit:
        return FilterResult(True, f"Africa/EMEA-eligible (matched '{b_hit}')", tier=TIER_B)

    if explicit:
        # Source gave an explicit eligibility list/string but it didn't match
        # worldwide, Africa/EMEA, or a reject phrase - e.g. "US, UK, Canada, Germany"
        # from Himalayas' locationRestrictions. Treat an explicit-but-non-matching
        # list as a soft reject (tier D) since the source is telling us specific
        # eligible countries and Ethiopia/Africa isn't among them - but only
        # when it reads like an enumerated country list, not a vague phrase.
        looks_like_country_list = bool(re.search(r",", explicit)) or len(explicit.split()) <= 4
        if looks_like_country_list:
            return FilterResult(
                False, f"explicit eligibility list ('{explicit}') doesn't include candidate's region",
                tier=TIER_D, detail={"source_field": "explicit"},
            )
        return FilterResult(True, "explicit eligibility field present but unclear - passing to AI", tier=TIER_C)

    # No explicit field, no keyword hit either way - genuinely unclear.
    return FilterResult(True, "no explicit eligibility statement found", tier=TIER_C)
