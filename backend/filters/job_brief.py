"""Extract short requirement / "what they look for" briefs from a posting.

Used in Discord alerts so the candidate sees experience, location eligibility,
and key asks without opening the full JD.
"""
from __future__ import annotations

import re
from typing import Any


def _clean(text: str, limit: int = 280) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _years_phrase(record: dict[str, Any]) -> str:
    display = (record.get("years_required_display") or "").strip()
    if display and display.lower() not in {"not clearly stated", "not specified"}:
        return display
    desc = record.get("description") or ""
    m = re.search(
        r"(\d+)\s*[+\-–]?\s*(?:to\s*)?(\d+)?\s*\+?\s*years?(?:\s+of)?(?:\s+experience)?",
        desc,
        re.I,
    )
    if m:
        lo, hi = m.group(1), m.group(2)
        return f"{lo}-{hi} years" if hi else f"{lo}+ years"
    return "not clearly stated"


def _location_phrase(record: dict[str, Any]) -> str:
    loc = (record.get("location_raw") or "").strip() or "Remote"
    tier = (record.get("location_tier") or "").strip()
    explicit = (record.get("hires_remotely_from") or "").strip()
    parts = [loc]
    if explicit and explicit.lower() not in loc.lower():
        parts.append(f"hires from: {explicit}")
    if tier:
        parts.append(f"tier {tier}")
    return " · ".join(parts)


def _section_snip(text: str, headers: tuple[str, ...], limit: int = 320) -> str:
    if not text:
        return ""
    lower = text.lower()
    for header in headers:
        idx = lower.find(header)
        if idx < 0:
            continue
        chunk = text[idx : idx + 900]
        # Stop at next ALL-CAPS-ish header if present
        stop = re.search(r"\n[A-Z][A-Z /&]{4,}\n", chunk[len(header) :])
        if stop:
            chunk = chunk[: len(header) + stop.start()]
        return _clean(chunk, limit)
    return ""


def build_look_for_brief(record: dict[str, Any]) -> str:
    """What the role is asking for (skills / focus) — prefer AI field, else heuristics."""
    ai = (record.get("look_for_summary") or "").strip()
    if ai:
        return _clean(ai, 360)
    why = record.get("why_matches") or []
    if why:
        return _clean(" · ".join(str(x) for x in why[:3]), 360)
    desc = record.get("description") or ""
    snip = _section_snip(
        desc,
        (
            "what you'll do",
            "what you will do",
            "the role",
            "about the role",
            "responsibilities",
            "you will",
        ),
    )
    if snip:
        return snip
    summary = (record.get("reasoning_summary") or "").strip()
    if summary:
        return _clean(summary, 360)
    return _clean(desc[:320] or "See job post for details.", 320)


def build_requirements_brief(record: dict[str, Any]) -> str:
    """Requirements: years, must-be-based, hard skills — prefer AI field, else heuristics."""
    ai = (record.get("requirements_summary") or "").strip()
    if ai:
        return _clean(ai, 400)
    parts: list[str] = []
    years = _years_phrase(record)
    parts.append(f"Experience: {years}")
    parts.append(f"Location: {_location_phrase(record)}")
    desc = record.get("description") or ""
    req = _section_snip(
        desc,
        (
            "requirements",
            "you have",
            "what you'll need",
            "what you need",
            "qualifications",
            "must have",
            "must-have",
            "about you",
        ),
        limit=220,
    )
    if req:
        parts.append(req)
    gaps = record.get("gaps") or []
    if gaps:
        parts.append("Watch-outs: " + " · ".join(str(g) for g in gaps[:2]))
    return _clean(" | ".join(parts), 420)
