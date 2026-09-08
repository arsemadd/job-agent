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
    return MatchEvaluation(
        score=int(data.get("score", 0)),
        why_matches=list(data.get("why_matches", []) or []),
        gaps=list(data.get("gaps", []) or []),
        confidence=data.get("confidence", "medium"),
        reasoning_summary=data.get("reasoning_summary", ""),
        recommend_reject_override=bool(data.get("recommend_reject_override", False)),
        override_reason=data.get("override_reason", "") or "",
    )
