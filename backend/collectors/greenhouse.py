"""Greenhouse collector. Public per-company job-board API, no key required.

API: https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true

Greenhouse has no cross-company search - you have to know a company's board
token (usually visible in their careers page URL, e.g.
boards.greenhouse.io/stripe -> token "stripe"). Populate
config/preferences.json -> sources.greenhouse_boards with the tokens you want
tracked; this collector is a no-op if that list is empty.
"""
from __future__ import annotations

from backend.collectors.base import Collector, get_json, logger
from backend.models import Job

API_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


class GreenhouseCollector(Collector):
    name = "greenhouse"

    def __init__(self, board_tokens: list[str] | None = None):
        self.board_tokens = board_tokens or []

    def fetch(self):
        jobs = []
        for board in self.board_tokens:
            try:
                data = get_json(API_URL.format(board=board), params={"content": "true"})
            except Exception as exc:  # noqa: BLE001
                logger.debug("greenhouse: board %s failed (%s)", board, exc)
                continue

            for row in data.get("jobs", []):
                try:
                    location = (row.get("location") or {}).get("name", "")
                    jobs.append(
                        Job(
                            source=f"greenhouse:{board}",
                            external_id=str(row.get("id")),
                            title=row.get("title", ""),
                            company=board,
                            url=row.get("absolute_url", ""),
                            description=row.get("content", ""),
                            location_raw=location,
                            posted_at=row.get("updated_at"),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("greenhouse: skipping malformed row on board %s (%s)", board, exc)
        return jobs
