"""Anthropic (Claude) scoring backend. Forces structured output via tool use
so parsing never depends on the model's free-text formatting."""
from __future__ import annotations

import json
import logging
import os
import time

import anthropic

from backend.filters.pipeline import HardFilterVerdict
from backend.matching.candidate import render_candidate_context
from backend.matching.job_normalizer import render_job_context
from backend.matching.scoring_common import (
    RESULT_JSON_SCHEMA,
    SYSTEM_PROMPT,
    MatchEvaluation,
    compute_decision,
    evaluation_from_dict,
)
from backend.models import Job

logger = logging.getLogger("job_agent.scoring.anthropic")

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_RETRIES = 3

TOOL_SCHEMA = {
    "name": "submit_match_evaluation",
    "description": "Submit the structured evaluation of how well this job matches the candidate.",
    "input_schema": RESULT_JSON_SCHEMA,
}


class AnthropicScorer:
    def __init__(self, candidate_profile: dict, prefs: dict, api_key: str | None = None, model: str | None = None):
        self.candidate_context = render_candidate_context(candidate_profile)
        self.prefs = prefs
        self.model = (model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip()
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it or put it in .env before running the pipeline."
            )
        if not self.model:
            raise RuntimeError("ANTHROPIC_MODEL resolved empty - set ANTHROPIC_MODEL or use the default.")
        self.client = anthropic.Anthropic(api_key=api_key)

    def score_job(self, job: Job, verdict: HardFilterVerdict) -> MatchEvaluation:
        job_context = render_job_context(job, verdict)
        user_message = (
            f"CANDIDATE PROFILE:\n{self.candidate_context}\n\n"
            f"---\n\nJOB POSTING TO EVALUATE:\n{job_context}"
        )

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=1500,
                    system=SYSTEM_PROMPT,
                    tools=[TOOL_SCHEMA],
                    tool_choice={"type": "tool", "name": "submit_match_evaluation"},
                    messages=[{"role": "user", "content": user_message}],
                )
                result = self._parse_tool_result(resp)
                if result is not None:
                    result.decision = compute_decision(result.score, result.recommend_reject_override, self.prefs)
                    return result
                last_error = "no tool_use block in response"
            except anthropic.APIStatusError as exc:
                last_error = f"API error {exc.status_code}: {exc.message}"
                if exc.status_code == 429 or exc.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(1)

        logger.warning("scoring failed for '%s' @ %s after %d attempts: %s", job.title, job.company, MAX_RETRIES, last_error)
        return MatchEvaluation(score=0, decision="REJECT", error=last_error, reasoning_summary="Scoring failed - not sent, needs manual review.")

    @staticmethod
    def _parse_tool_result(resp) -> MatchEvaluation | None:
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "submit_match_evaluation":
                data = block.input
                if isinstance(data, str):
                    data = json.loads(data)
                return evaluation_from_dict(data)
        return None
