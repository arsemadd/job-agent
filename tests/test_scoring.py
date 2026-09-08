import json
import os
from types import SimpleNamespace

import pytest

from backend.filters.pipeline import HardFilterVerdict
from backend.matching.scoring import MatchScorer, compute_decision
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


def _fake_tool_response(payload: dict):
    block = SimpleNamespace(type="tool_use", name="submit_match_evaluation", input=payload)
    return SimpleNamespace(content=[block])


class FakeMessages:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _fake_tool_response(self.payload)


def _make_scorer(candidate_profile, prefs, payload):
    scorer = MatchScorer(candidate_profile, prefs, api_key="test-key")
    scorer.client = SimpleNamespace(messages=FakeMessages(payload))
    return scorer


def test_high_score_maps_to_send_decision(candidate_profile, prefs):
    scorer = _make_scorer(candidate_profile, prefs, {
        "score": 91, "why_matches": ["a"], "gaps": [], "confidence": "high",
        "reasoning_summary": "great fit",
    })
    job = Job(source="s", external_id="1", title="Product Manager", company="Acme", url="https://x.com/1")
    verdict = HardFilterVerdict(True, "A_WORLDWIDE")
    result = scorer.score_job(job, verdict)
    assert result.score == 91
    assert result.decision == "SEND"


def test_mid_score_maps_to_digest_decision(candidate_profile, prefs):
    scorer = _make_scorer(candidate_profile, prefs, {
        "score": 76, "why_matches": ["a"], "gaps": ["b"], "confidence": "medium",
        "reasoning_summary": "decent fit",
    })
    job = Job(source="s", external_id="1", title="Product Manager", company="Acme", url="https://x.com/1")
    result = scorer.score_job(job, HardFilterVerdict(True, "B_AFRICA_EMEA"))
    assert result.decision == "DIGEST"


def test_low_score_maps_to_reject_decision(candidate_profile, prefs):
    scorer = _make_scorer(candidate_profile, prefs, {
        "score": 40, "why_matches": [], "gaps": ["c"], "confidence": "low",
        "reasoning_summary": "weak fit",
    })
    job = Job(source="s", external_id="1", title="Product Manager", company="Acme", url="https://x.com/1")
    result = scorer.score_job(job, HardFilterVerdict(True, "C_UNCLEAR"))
    assert result.decision == "REJECT"


def test_reject_override_forces_reject_regardless_of_score(candidate_profile, prefs):
    """The AI shouldn't be able to send a job on score alone once it flags a
    disqualifying issue the deterministic filters missed."""
    scorer = _make_scorer(candidate_profile, prefs, {
        "score": 95, "why_matches": ["a"], "gaps": [], "confidence": "high",
        "reasoning_summary": "looks great but...",
        "recommend_reject_override": True,
        "override_reason": "posting text explicitly contradicts the location tier",
    })
    job = Job(source="s", external_id="1", title="Product Manager", company="Acme", url="https://x.com/1")
    result = scorer.score_job(job, HardFilterVerdict(True, "A_WORLDWIDE"))
    assert result.decision == "REJECT"
    assert result.recommend_reject_override is True


def test_compute_decision_thresholds_directly(prefs):
    assert compute_decision(85, False, prefs) == "SEND"
    assert compute_decision(84, False, prefs) == "DIGEST"
    assert compute_decision(70, False, prefs) == "DIGEST"
    assert compute_decision(69, False, prefs) == "REJECT"
    assert compute_decision(99, True, prefs) == "REJECT"
