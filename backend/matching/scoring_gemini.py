"""Google Gemini scoring backend - the $0 option (Gemini API free tier via
Google AI Studio, no billing required to start: aistudio.google.com/apikey).

Uses Gemini's native JSON mode (response_mime_type + response_json_schema)
for structured output instead of Anthropic-style tool use - same schema,
same downstream MatchEvaluation shape, so the rest of the pipeline doesn't
care which provider actually scored the job.

Free-tier rate limits are lower than a paid plan (requests/minute and
requests/day caps that vary by model) - the retry loop backs off harder on
429s than the Anthropic backend does for that reason.
"""
from __future__ import annotations

import json
import logging
import os
import time

from google import genai
from google.genai import errors, types

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

logger = logging.getLogger("job_agent.scoring.gemini")

# gemini-3.5-flash-lite has the highest free-tier daily quota among current
# Flash models; override via GEMINI_MODEL if you prefer gemini-3.6-flash (paid
# or higher free-tier allowance). See https://ai.google.dev/gemini-api/docs/pricing
DEFAULT_MODEL = "gemini-3.5-flash-lite"
MAX_RETRIES = 4


class GeminiScorer:
    def __init__(self, candidate_profile: dict, prefs: dict, api_key: str | None = None, model: str | None = None):
        self.candidate_context = render_candidate_context(candidate_profile)
        self.prefs = prefs
        # Empty env vars (common when GitHub Actions maps an unset repo variable) must not win over the default.
        self.model = (model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL).strip()
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
                "and export it or put it in .env before running the pipeline."
            )
        if not self.model:
            raise RuntimeError("GEMINI_MODEL resolved empty - set GEMINI_MODEL or use the default.")
        self.client = genai.Client(api_key=api_key)

    def score_job(self, job: Job, verdict: HardFilterVerdict) -> MatchEvaluation:
        job_context = render_job_context(job, verdict)
        user_message = (
            f"CANDIDATE PROFILE:\n{self.candidate_context}\n\n"
            f"---\n\nJOB POSTING TO EVALUATE:\n{job_context}"
        )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_json_schema=RESULT_JSON_SCHEMA,
            max_output_tokens=1500,
            temperature=0.2,
        )

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=user_message,
                    config=config,
                )
                data = self._parse_response(resp)
                if data is not None:
                    result = evaluation_from_dict(data)
                    result.decision = compute_decision(result.score, result.recommend_reject_override, self.prefs)
                    return result
                last_error = "no parseable JSON in response"
            except errors.APIError as exc:
                last_error = f"API error {exc.code}: {exc.message}"
                if exc.code == 429:
                    # free-tier rate limits reset per minute/day - back off harder than a paid API would need
                    time.sleep(min(60, 5 * attempt))
                    continue
                if exc.code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(1)

        logger.warning("scoring failed for '%s' @ %s after %d attempts: %s", job.title, job.company, MAX_RETRIES, last_error)
        return MatchEvaluation(score=0, decision="REJECT", error=last_error, reasoning_summary="Scoring failed - not sent, needs manual review.")

    @staticmethod
    def _parse_response(resp) -> dict | None:
        text = getattr(resp, "text", None)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("gemini: response was not valid JSON: %s", text[:200])
            return None
