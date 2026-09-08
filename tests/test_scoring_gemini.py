import json
import os
from types import SimpleNamespace

import pytest

from backend.filters.pipeline import HardFilterVerdict
from backend.matching.scoring import build_scorer
from backend.matching.scoring_gemini import GeminiScorer
from backend.models import Job

CANDIDATE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "candidate_profile.json")
PREFS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "preferences.json")


@pytest.fixture
def candidate_profile():
    with open(CANDIDATE_PATH) as f:
        return json.load(f)


@pytest.fixture
def prefs():
    with open(PREFS_PATH) as f:
        return json.load(f)


class FakeModels:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(text=json.dumps(self.payload))


def _make_scorer(candidate_profile, prefs, payload):
    scorer = GeminiScorer(candidate_profile, prefs, api_key="test-key")
    scorer.client = SimpleNamespace(models=FakeModels(payload))
    return scorer


def test_gemini_high_score_maps_to_send(candidate_profile, prefs):
    scorer = _make_scorer(candidate_profile, prefs, {
        "score": 88, "why_matches": ["a"], "gaps": [], "confidence": "high", "reasoning_summary": "good fit",
    })
    job = Job(source="s", external_id="1", title="Product Manager", company="Acme", url="https://x.com/1")
    result = scorer.score_job(job, HardFilterVerdict(True, "A_WORLDWIDE"))
    assert result.score == 88
    assert result.decision == "SEND"


def test_gemini_handles_non_json_response_gracefully(candidate_profile, prefs):
    scorer = GeminiScorer(candidate_profile, prefs, api_key="test-key")
    scorer.client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text="not json")))
    job = Job(source="s", external_id="1", title="PM", company="Acme", url="https://x.com/1")
    result = scorer.score_job(job, HardFilterVerdict(True, "A_WORLDWIDE"))
    assert result.error is not None
    assert result.decision == "REJECT"


def test_build_scorer_selects_gemini_by_default(candidate_profile, prefs, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import importlib
    import backend.matching.scoring as scoring_module
    importlib.reload(scoring_module)
    scorer = scoring_module.build_scorer(candidate_profile, prefs)
    assert scorer.__class__.__name__ == "GeminiScorer"


def test_build_scorer_selects_anthropic_when_configured(candidate_profile, prefs, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    scorer = build_scorer(candidate_profile, prefs, provider="anthropic")
    assert scorer.__class__.__name__ == "AnthropicScorer"


def test_build_scorer_rejects_unknown_provider(candidate_profile, prefs):
    with pytest.raises(ValueError):
        build_scorer(candidate_profile, prefs, provider="chatgpt")
