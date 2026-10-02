"""Location eligibility classifier — fully-remote only for this candidate.

Hard rules (in order):
  1. Reject hybrid / on-site / in-office / office-days requirements
  2. Reject work-authorization / visa / citizenship restrictions
  3. Reject region-restricted remote (US-only, EU-only, etc.)
  4. Accept worldwide / Africa-EMEA remote
  5. Accept generic "Remote" only when a remote signal is present and no
     hybrid/auth/city-office contradiction — otherwise reject

"Remote" without eligibility is no longer a free pass to the AI when
require_fully_remote is enabled (default).
"""
from __future__ import annotations

import re

from backend.filters.result import FilterResult
from backend.models import Job

TIER_A = "A_WORLDWIDE"
TIER_B = "B_AFRICA_EMEA"
TIER_C = "C_UNCLEAR"
TIER_D = "D_REJECT"

# Hybrid / office — never "fully remote"
HYBRID_PATTERNS = [
    re.compile(r"\bhybrid\b", re.I),
    re.compile(r"\bon[- ]?site\b", re.I),
    re.compile(r"\bin[- ]office\b", re.I),
    re.compile(r"\boffice[- ]based\b", re.I),
    re.compile(r"\bdays?\s+per\s+week\s+in\s+(?:the\s+)?office\b", re.I),
    re.compile(r"\bmust\s+be\s+(?:based|located)\s+in\b", re.I),
    re.compile(r"\brelocation\s+required\b", re.I),
    re.compile(r"\bcome\s+into\s+(?:the\s+)?office\b", re.I),
]

# Work authorization / visa — candidate cannot satisfy
AUTH_PATTERNS = [
    re.compile(r"\bwork\s+authorization\b", re.I),
    re.compile(r"\bauthorized\s+to\s+work\b", re.I),
    re.compile(r"\beligible\s+to\s+work\b", re.I),
    re.compile(r"\bright\s+to\s+work\b", re.I),
    re.compile(r"\bmust\s+have\s+(?:the\s+)?right\s+to\s+work\b", re.I),
    re.compile(r"\bno\s+visa\s+sponsorship\b", re.I),
    re.compile(r"\b(?:unable|not\s+able|cannot|can'?t)\s+to\s+(?:offer\s+)?(?:visa\s+)?sponsorship\b", re.I),
    re.compile(r"\b(?:we\s+)?(?:do\s+not|don'?t)\s+(?:offer\s+)?(?:visa\s+)?sponsorship\b", re.I),
    re.compile(r"\bvisa\s+sponsorship\s+(?:is\s+)?(?:not\s+)?(?:available|provided|offered)\b", re.I),
    re.compile(r"\bmust\s+be\s+(?:a\s+)?(?:us|u\.s\.|uk|eu|canadian)\s+citizen\b", re.I),
    re.compile(r"\bus\s+citizen(?:ship)?\s+required\b", re.I),
    re.compile(r"\bgreen\s+card\b", re.I),
    re.compile(r"\bpermanent\s+resident(?:ship)?\s+required\b", re.I),
    re.compile(r"\bmust\s+reside\s+in\b", re.I),
    re.compile(r"\bmust\s+live\s+in\b", re.I),
    re.compile(r"\bmust\s+be\s+located\s+in\b", re.I),
]

REMOTE_SIGNAL = re.compile(
    r"\b(?:remote|work\s+from\s+anywhere|wfa|distributed|location[- ]independent|"
    r"fully\s+remote|100%\s+remote)\b",
    re.I,
)


def _any_keyword(text: str, keywords: list[str]) -> str | None:
    t = text.lower()
    for kw in keywords:
        if kw.lower() in t:
            return kw
    return None


def _first_regex(text: str, patterns: list[re.Pattern[str]]) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return None


def is_remote_from_anywhere(job: Job | dict) -> tuple[bool, str]:
    """Strictly verify if a job allows remote work from anywhere in the world.
    
    Used specifically for Discord alerts to ensure no US-only, Canada-only,
    or region-restricted jobs are ever alerted.
    """
    def _extract_tags_str(raw_tags) -> str:
        if isinstance(raw_tags, list):
            parts = []
            for t in raw_tags:
                if isinstance(t, dict):
                    parts.append(str(t.get("name") or t.get("slug") or ""))
                else:
                    parts.append(str(t))
            return " ".join(parts)
        return str(raw_tags or "")

    if isinstance(job, dict):
        loc_raw = (job.get("location_raw") or "").strip()
        explicit = (job.get("hires_remotely_from") or "").strip()
        desc = (job.get("description") or "")[:4000]
        title = (job.get("title") or "")
        tags = _extract_tags_str(job.get("tags"))
        source = (job.get("source") or "")
    else:
        loc_raw = (job.location_raw or "").strip()
        explicit = (job.hires_remotely_from or "").strip()
        desc = (job.description or "")[:4000]
        title = job.title or ""
        tags = _extract_tags_str(job.tags)
        source = job.source or ""

    loc_combined = f"{loc_raw} | {explicit} | {tags}".lower()
    full_text = f"{title} | {loc_raw} | {explicit} | {tags} | {desc}".lower()

    # 1. Hard check: hybrid or onsite
    for pat in HYBRID_PATTERNS:
        if pat.search(full_text):
            return False, f"Hybrid/onsite detected: {pat.pattern}"

    # 2. Hard check: work authorization or visa restriction
    for pat in AUTH_PATTERNS:
        if pat.search(full_text):
            return False, f"Work authorization or residency restriction detected: {pat.pattern}"

    # 3. Explicit Country/Region Rejections in location or text
    country_rejects = [
        "us only", "u.s. only", "usa only", "united states only", "canada only",
        "uk only", "united kingdom only", "eu only", "europe only", "latam only", "apac only",
        "(us)", "(usa)", "(u.s.)", "(canada)", "(uk)", "(united states)", "(north america)",
        "[us]", "[usa]", "[u.s.]", "[canada]", "[uk]", "[united states]", "[north america]",
        "- us", "- usa", "- canada", "- uk",
        "remote - us", "remote (us)", "remote, us", "us remote", "remote us",
        "remote - usa", "remote, usa", "remote (usa)", "usa remote",
        "remote - united states", "remote, united states", "united states remote",
        "remote - canada", "remote (canada)", "remote, canada", "canada remote", "remote canada",
        "remote - north america", "north america remote", "us/canada", "canada/us", "us or canada", "canada or us",
        "remote - uk", "remote (uk)", "remote, uk", "uk remote", "remote uk",
        "london, united kingdom", "london, uk", "london",
        "remote - europe", "remote (europe)", "remote, europe", "within europe", "within the eu",
        "remote - germany", "remote (germany)", "remote, germany", "berlin, germany",
        "remote - france", "remote, france", "remote - netherlands", "remote, netherlands",
        "remote - australia", "remote, australia", "remote - latam", "remote - apac",
        "must be located in", "must reside in", "within the united states", "within canada"
    ]
    for kw in country_rejects:
        if kw in loc_combined or kw in full_text:
            return False, f"Restricted to specific country/region: '{kw}'"

    # 4. Check for explicit Worldwide / Anywhere in the World / Africa / EMEA signal
    worldwide_keywords = [
        "worldwide", "remote - worldwide", "remote-worldwide", "worldwide remote",
        "anywhere", "remote - anywhere", "remote-anywhere", "anywhere in the world",
        "work from anywhere", "remote global", "remote - global", "global remote",
        "location independent", "100% remote anywhere", "open globally", "all countries",
        "remote (worldwide)", "remote (anywhere)", "remote (global)",
        "remote - emea", "remote (emea)", "remote, emea", "emea remote",
        "remote - africa", "remote (africa)", "africa remote"
    ]
    for kw in worldwide_keywords:
        if kw in loc_combined:
            return True, f"Explicitly remote from anywhere / EMEA ('{kw}')"

    for kw in ["anywhere in the world", "work from anywhere in the world", "work from anywhere", "hire anywhere", "100% remote worldwide"]:
        if kw in full_text:
            return True, f"Worldwide remote confirmed in description ('{kw}')"

    # 5. If it's a specific city/country location without remote worldwide, reject
    if loc_raw and not re.search(r"\b(remote|telecommute|distributed|anywhere|global)\b", loc_raw, re.I):
        return False, f"Location is a specific physical city/country: '{loc_raw}'"

    # 6. If explicitly remote with NO country restrictions, accept
    if re.search(r"\b(remote|telecommute|distributed|fully remote|100% remote)\b", loc_raw, re.I):
        return True, "Fully remote role with no country restrictions"

    # 7. Source-level remote board signal
    if source in ("remoteok", "weworkremotely", "jobgether", "himalayas", "jobicy", "nodesk", "remotive"):
        return True, "Verified remote board posting with no country restrictions"

    return False, "Not confirmed as Remote from Anywhere / Worldwide"


def classify_location(job: Job, prefs: dict) -> FilterResult:
    loc_prefs = prefs.get("location", {})
    tier_a_kw = loc_prefs.get("tier_a_worldwide_keywords", [])
    tier_b_kw = loc_prefs.get("tier_b_africa_emea_keywords", [])
    tier_d_kw = loc_prefs.get("tier_d_reject_keywords", [])
    require_fully_remote = loc_prefs.get("require_fully_remote", True)
    reject_hybrid = loc_prefs.get("reject_hybrid_onsite", True)
    reject_auth = loc_prefs.get("reject_work_authorization", True)

    explicit = (job.hires_remotely_from or "").strip()
    combined = " | ".join(
        filter(None, [job.location_raw, explicit, (job.description or "")[:5000]])
    )

    if reject_hybrid:
        hybrid_hit = _first_regex(combined, HYBRID_PATTERNS)
        if hybrid_hit:
            return FilterResult(
                False,
                f"not fully remote (matched '{hybrid_hit}')",
                tier=TIER_D,
                detail={"matched": hybrid_hit, "rule": "hybrid_onsite"},
            )

    if reject_auth:
        auth_hit = _first_regex(combined, AUTH_PATTERNS)
        if auth_hit:
            return FilterResult(
                False,
                f"work authorization / visa restriction (matched '{auth_hit}')",
                tier=TIER_D,
                detail={"matched": auth_hit, "rule": "authorization"},
            )

    d_hit = _any_keyword(combined, tier_d_kw)
    if d_hit:
        return FilterResult(
            False,
            f"location-restricted (matched '{d_hit}')",
            tier=TIER_D,
            detail={"matched_keyword": d_hit, "source_field": "explicit" if explicit else "text"},
        )

    a_hit = _any_keyword(explicit or job.location_raw, tier_a_kw)
    if a_hit:
        return FilterResult(True, f"worldwide-eligible (matched '{a_hit}')", tier=TIER_A)

    b_hit = _any_keyword(explicit or job.location_raw, tier_b_kw)
    if b_hit:
        return FilterResult(True, f"Africa/EMEA-eligible (matched '{b_hit}')", tier=TIER_B)

    if explicit:
        looks_like_country_list = bool(re.search(r",", explicit)) or len(explicit.split()) <= 4
        if looks_like_country_list:
            return FilterResult(
                False,
                f"explicit eligibility list ('{explicit}') doesn't include candidate's region",
                tier=TIER_D,
                detail={"source_field": "explicit"},
            )
        if require_fully_remote and not REMOTE_SIGNAL.search(explicit):
            return FilterResult(
                False,
                f"explicit field ('{explicit}') is not fully remote",
                tier=TIER_D,
            )
        return FilterResult(True, "explicit eligibility field present but unclear - passing to AI", tier=TIER_C)

    has_remote = bool(REMOTE_SIGNAL.search(job.location_raw or "") or REMOTE_SIGNAL.search(combined))

    if require_fully_remote and not has_remote:
        loc = (job.location_raw or "").strip() or "unspecified"
        return FilterResult(
            False,
            f"not fully remote (no remote signal in '{loc}')",
            tier=TIER_D,
            detail={"rule": "require_fully_remote"},
        )

    # Generic remote with no worldwide/Africa signal — still pass to AI as unclear,
    # but only when require_fully_remote already confirmed a remote keyword.
    return FilterResult(True, "remote with unclear geographic eligibility - passing to AI", tier=TIER_C)
