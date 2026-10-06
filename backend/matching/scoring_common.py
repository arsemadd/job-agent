"""Shared pieces between AI scoring backends (Anthropic, Gemini): the JSON
schema the model must fill in, the system prompt, the result type, and the
score -> decision math. Only the API call itself differs per provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RESULT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Overall match score, 0-100, weighing skills/experience evidence, role fit, and domain overlap.",
        },
        "why_matches": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short, specific bullet points citing actual resume/portfolio evidence that matches this job's requirements.",
        },
        "gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short, specific bullet points on what's missing or weak relative to the job's requirements. Empty list if genuinely none.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence in this evaluation given how much detail the posting provided.",
        },
        "reasoning_summary": {
            "type": "string",
            "description": "1-3 sentence summary of the overall verdict, in plain language.",
        },
        "recommend_reject_override": {
            "type": "boolean",
            "description": "True ONLY if you spot a disqualifying problem the deterministic pre-filters would have missed (e.g. the posting's actual text contradicts its location tier and clearly excludes the candidate, it reads as a scam/MLM, or it is unmistakably a senior/lead role mislabeled). Default false.",
        },
        "override_reason": {
            "type": "string",
            "description": "Required and specific if recommend_reject_override is true; omit or leave empty otherwise.",
        },
    },
    "required": ["score", "why_matches", "gaps", "confidence", "reasoning_summary"],
}

import re

SYSTEM_PROMPT = """You are a sharp, honest technical recruiter evaluating a SPECIFIC job posting \
against ONE SPECIFIC candidate's actual resume and portfolio evidence. You are not writing generic \
encouragement - you are deciding whether this candidate should spend her limited attention applying \
to this exact job.

Ground every claim in the evidence you were given. Do not credit the candidate with skills, tools, \
or experience that aren't stated in her work history, skills list, or portfolio case studies. \
"Worked with engineering" is not the same as "is an engineer." Shipping AI *features* as a PM is not \
the same as being an ML engineer.

Score primarily on: does the actual problem space and day-to-day responsibility of this job match \
the evidence in her resume and portfolio - not just whether keywords overlap. A job requiring "SQL" \
and a candidate who has used SQL for ad hoc product decisions is a partial match, not a full one, if \
the job wants a data analyst who writes complex queries daily.

Be honest about weak matches. A generic "product manager" posting is not automatically a 90+ just \
because the title matches - read what the role actually needs.

CRITICAL RULE — ZERO TOLERANCE FOR HYBRID, ONSITE, OR REGIONAL RESTRICTIONS:
The candidate is based in Addis Ababa, Ethiopia. She accepts ONLY 100% remote roles that allow working \
from anywhere worldwide or from Africa/EMEA.
- NEVER list location restrictions, hybrid arrangements, office days, US-remote, Canada-remote, UK-remote, \
or geographic alignment issues as a "gap" in the `gaps` list.
- If a job mentions hybrid, requires office attendance, is restricted to the US/Canada/UK/India or any \
specific region that excludes Ethiopia, or if remote eligibility from Ethiopia is doubtful:
  You MUST set `recommend_reject_override: true`, set `override_reason` describing the location/hybrid \
  disqualification, and set `score: 0`.
- Hybrid or country-restricted roles are NON-NEGOTIABLE HARD REJECTS. Do not score them and do not include \
location as a gap.

You will be told the deterministic pre-filter results (location tier, years-required) that already \
ran before you saw this job - trust those unless the posting text clearly contradicts them, in which \
case use recommend_reject_override to flag it rather than silently scoring around it.

Respond with ONLY a JSON object matching the required schema. No prose outside the JSON."""


@dataclass
class MatchEvaluation:
    score: int
    why_matches: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    confidence: str = "medium"
    reasoning_summary: str = ""
    recommend_reject_override: bool = False
    override_reason: str = ""
    decision: str = "REJECT"          # computed, not from the model
    error: str | None = None          # set if scoring failed after retries


LOCATION_HYBRID_DISQUALIFY_PATTERNS = [
    re.compile(r"\b(?:hybrid|on[- ]?site|in[- ]?office|office[- ]based)\b", re.I),
    re.compile(r"\b(?:us[- ]remote|us[- ]centric|canada[- ]centric|uk[- ]centric)\b", re.I),
    re.compile(r"\b(?:addis ababa|ethiopia)\b.*\b(?:geographic|alignment|unclear|mismatch|barrier|restricted|centric)\b", re.I),
    re.compile(r"\b(?:geographic|regional)\b.*\b(?:alignment|unclear|mismatch|barrier|restricted)\b", re.I),
    re.compile(r"\b(?:location eligibility|location is posted as|not worldwide|not remote from anywhere)\b", re.I),
]


def compute_decision(score: int, override: bool, prefs: dict) -> str:
    if override:
        return "REJECT"
    scoring_prefs = prefs.get("scoring", {})
    send_at = scoring_prefs.get("min_score_to_send_immediate", 85)
    digest_at = scoring_prefs.get("min_score_to_send_digest", 70)
    if score >= send_at:
        return "SEND"
    if score >= digest_at:
        return "DIGEST"
    return "REJECT"


def evaluation_from_dict(data: dict) -> MatchEvaluation:
    raw_gaps = list(data.get("gaps", []) or [])
    clean_gaps = []
    has_location_disqualification = False
    disqualify_reason = ""

    for g in raw_gaps:
        g_str = str(g)
        is_loc_mismatch = any(pat.search(g_str) for pat in LOCATION_HYBRID_DISQUALIFY_PATTERNS)
        if is_loc_mismatch:
            has_location_disqualification = True
            disqualify_reason = g_str
        else:
            clean_gaps.append(g_str)

    reasoning = str(data.get("reasoning_summary", "") or "")
    if any(pat.search(reasoning) for pat in LOCATION_HYBRID_DISQUALIFY_PATTERNS):
        has_location_disqualification = True
        if not disqualify_reason:
            disqualify_reason = reasoning

    override = bool(data.get("recommend_reject_override", False)) or has_location_disqualification
    override_reason = (data.get("override_reason", "") or "").strip()
    if has_location_disqualification and not override_reason:
        override_reason = f"Candidate requires 100% remote (worldwide/EMEA): rejected due to '{disqualify_reason}'"

    score = int(data.get("score", 0))
    if has_location_disqualification:
        score = 0

    return MatchEvaluation(
        score=score,
        why_matches=list(data.get("why_matches", []) or []),
        gaps=clean_gaps,
        confidence=data.get("confidence", "medium"),
        reasoning_summary=reasoning,
        recommend_reject_override=override,
        override_reason=override_reason,
    )
