"""Loads the candidate profile (resume + portfolio evidence) and renders it
into the compact text block the AI matcher reads for every job."""
from __future__ import annotations

import json
import os

DEFAULT_PATH = os.path.join("config", "candidate_profile.json")


def load_candidate_profile(path: str = DEFAULT_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def render_candidate_context(profile: dict) -> str:
    """Turn the structured profile into readable prose for the prompt - the
    same evidence a hiring manager would get from her resume + portfolio,
    not just a keyword bag."""
    lines = []
    lines.append(f"Name: {profile['name']}")
    lines.append(f"Location: {profile['location']}")
    lines.append(f"Total experience: ~{profile['years_experience_total']} years")
    lines.append(f"Summary: {profile['summary']}")
    lines.append("")
    lines.append("WORK HISTORY:")
    for role in profile.get("roles_held", []):
        lines.append(f"- {role['title']} @ {role['company']} ({role['dates']}, ~{role['years']}y, {role['mode']})")
        for h in role.get("highlights", []):
            lines.append(f"    * {h}")
    lines.append("")
    lines.append("EDUCATION:")
    for ed in profile.get("education", []):
        lines.append(f"- {ed['degree']}, {ed['school']} ({ed['dates']})")
    lines.append("")
    lines.append("CORE SKILLS:")
    for category, items in profile.get("core_skills", {}).items():
        if isinstance(items, list):
            lines.append(f"- {category}: {', '.join(items)}")
    lines.append("")
    lines.append("PORTFOLIO CASE-STUDY EVIDENCE (what she has actually shipped, with proof):")
    for p in profile.get("portfolio_evidence", []):
        outcome = f" | Outcome: {p['outcome']}" if p.get("outcome") else ""
        lines.append(f"- {p['project']}: demonstrates {', '.join(p['demonstrates'])}{outcome}")
    lines.append("")
    lines.append(f"Domain exposure: {', '.join(profile.get('domain_exposure', []))}")
    lines.append("")
    prefs = profile.get("career_preferences", {})
    lines.append("STATED CAREER PREFERENCES:")
    lines.append(f"- Target titles: {', '.join(prefs.get('target_titles', []))}")
    lines.append(f"- Target experience band: {prefs.get('experience_target_years')} years")
    lines.append(f"- {prefs.get('note_on_5_to_6_years', '')}")
    lines.append(f"- Location priority: {' > '.join(prefs.get('location_priority', []))}")
    lines.append(f"- Open to: {prefs.get('open_to')}")
    return "\n".join(lines)
