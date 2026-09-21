"""Reject jobs that require any spoken language other than English.

English-only candidate: fluency/basic/native requirements for German, Spanish,
French, etc. are hard rejects before AI scoring. Pure English requirements pass.
Mentions of a language with no proficiency/requirement signal are ignored to
limit false positives (e.g. company names, office locations).
"""
from __future__ import annotations

import re

from backend.filters.result import FilterResult

# Spoken / written human languages only — not programming languages.
NON_ENGLISH_LANGUAGES = [
    "german", "deutsch", "spanish", "español", "espanol", "castilian",
    "french", "français", "francais", "portuguese", "português", "portugues",
    "italian", "italiano", "dutch", "nederlands", "flemish",
    "polish", "swedish", "norwegian", "danish", "finnish", "icelandic",
    "russian", "ukrainian", "czech", "slovak", "romanian", "hungarian",
    "greek", "turkish", "arabic", "hebrew", "hindi", "urdu", "bengali",
    "chinese", "mandarin", "cantonese", "japanese", "korean",
    "vietnamese", "thai", "indonesian", "malay", "tagalog", "filipino",
    "swahili", "amharic", "catalan", "basque", "galician", "croatian",
    "serbian", "bosnian", "bulgarian", "slovenian", "lithuanian",
    "latvian", "estonian", "georgian", "persian", "farsi", "pashto",
    "afrikaans", "zulu", "xhosa", "yoruba", "igbo", "hausa",
]

PROFICIENCY = (
    r"(?:fluent|fluency|native|bilingual|mother[- ]tongue|"
    r"proficient|proficiency|basic|conversational|intermediate|advanced|"
    r"spoken|written|speaking|writing|speaker|kenntnisse|"
    r"required|mandatory|must[- ]have|nice[- ]to[- ]have|preferred)"
)

CEFR = r"(?:a1|a2|b1|b2|c1|c2)"

LANG_ALT = "|".join(re.escape(lang) for lang in sorted(NON_ENGLISH_LANGUAGES, key=len, reverse=True))


def _patterns() -> list[re.Pattern[str]]:
    lang = rf"(?:{LANG_ALT})"
    return [
        # fluent in German / basic Spanish / native French
        re.compile(rf"\b{PROFICIENCY}\s+(?:in\s+)?{lang}\b", re.I),
        # German fluency / Spanish speaker / French language skills
        re.compile(
            rf"\b{lang}\s*(?:language\s+)?(?:{PROFICIENCY}|skills?|level)\b",
            re.I,
        ),
        # German (B2) / Spanish B1
        re.compile(rf"\b{lang}\s*\(?\s*{CEFR}\b", re.I),
        re.compile(rf"\b{CEFR}\s+(?:in\s+)?{lang}\b", re.I),
        # must speak German / knowledge of Spanish
        re.compile(rf"\b(?:must\s+speak|knowledge\s+of|command\s+of)\s+{lang}\b", re.I),
        # bilingual German/English or English and German
        re.compile(rf"\bbilingual\b[^.\\n]{{0,40}}\b{lang}\b", re.I),
        re.compile(rf"\b(?:english\s+and|and\s+english)\s+{lang}\b", re.I),
        re.compile(rf"\b{lang}\s+and\s+english\b", re.I),
        # German-speaking / Spanish-speaking
        re.compile(rf"\b{lang}[- ]speaking\b", re.I),
        # Deutschkenntnisse / Spanish required (short forms)
        re.compile(rf"\bdeutschkenntnisse\b", re.I),
        re.compile(rf"\b{lang}\s+required\b", re.I),
    ]


_COMPILED = _patterns()


def check_language(title: str, description: str, prefs: dict) -> FilterResult:
    """Hard-reject when a non-English language is required at any proficiency."""
    lang_prefs = prefs.get("language", {})
    if lang_prefs.get("reject_non_english_requirements", True) is False:
        return FilterResult(True, "non-English language filter disabled")

    text = f"{title or ''}\n{description or ''}"
    if not text.strip():
        return FilterResult(True, "no language requirement detected")

    for pattern in _COMPILED:
        match = pattern.search(text)
        if not match:
            continue
        snippet = re.sub(r"\s+", " ", match.group(0)).strip()
        return FilterResult(
            False,
            f"requires non-English language ('{snippet}') — English-only candidate",
            detail={"matched": snippet},
        )

    return FilterResult(True, "no non-English language requirement detected")
