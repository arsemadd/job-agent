"""Public entrypoint for AI scoring. Picks a backend (Anthropic or Gemini) at
runtime via the AI_PROVIDER env var so the rest of the pipeline never needs
to know which one is in use - both return the same MatchEvaluation shape and
go through the same compute_decision() thresholds.

AI_PROVIDER=gemini (default)  - Google's free-tier API, $0 to run
AI_PROVIDER=anthropic         - Claude, paid but very cheap at this volume
"""
from __future__ import annotations

import os

from backend.matching.scoring_common import MatchEvaluation, compute_decision  # noqa: F401 - re-exported

DEFAULT_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()


def build_scorer(candidate_profile: dict, prefs: dict, provider: str | None = None):
    """Factory: returns an AnthropicScorer or GeminiScorer instance depending
    on AI_PROVIDER (or the explicit `provider` argument). Both classes expose
    the same .score_job(job, verdict) -> MatchEvaluation interface."""
    provider = (provider or DEFAULT_PROVIDER).strip().lower()

    if provider == "anthropic":
        from backend.matching.scoring_anthropic import AnthropicScorer
        return AnthropicScorer(candidate_profile, prefs)

    if provider == "gemini":
        from backend.matching.scoring_gemini import GeminiScorer
        return GeminiScorer(candidate_profile, prefs)

    raise ValueError(f"Unknown AI_PROVIDER '{provider}' - expected 'anthropic' or 'gemini'.")


# Backward-compatible direct import (also used by tests): AnthropicScorer
# under its original name.
from backend.matching.scoring_anthropic import AnthropicScorer as MatchScorer  # noqa: E402,F401
