"""Shared helpers for collectors: a small requests wrapper and the common interface."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Iterable

import requests

logger = logging.getLogger("job_agent.collectors")

USER_AGENT = (
    "job-agent/1.0 (+personal job-matching agent; contact: arsemadoji7@gmail.com)"
)

DEFAULT_TIMEOUT = 20


def get_json(url: str, params: dict | None = None, headers: dict | None = None):
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        h.update(headers)
    resp = requests.get(url, params=params, headers=h, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_text(url: str, headers: dict | None = None) -> str:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    resp = requests.get(url, headers=h, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.text


class Collector(ABC):
    """Base class every job source implements."""

    name: str = "base"

    @abstractmethod
    def fetch(self) -> Iterable["Job"]:  # noqa: F821 - Job imported lazily to avoid cycles
        """Return an iterable of backend.models.Job. Must never raise on a single
        bad record — log and skip it so one malformed posting doesn't kill the run."""
        raise NotImplementedError

    def safe_fetch(self):
        """Wrapper the pipeline calls: never lets one source's failure kill the run."""
        try:
            jobs = list(self.fetch())
            logger.info("%s: collected %d jobs", self.name, len(jobs))
            return jobs
        except Exception as exc:  # noqa: BLE001 - collectors must be resilient
            logger.warning("%s: collector failed (%s) - skipping this source for this run", self.name, exc)
            return []
