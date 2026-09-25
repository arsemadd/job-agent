"""Shared data model for a normalized job posting used across the pipeline."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def identity_key(company: str, title: str) -> str:
    """Stable company+title fingerprint — used to block re-alerts across URL churn."""
    basis = f"{(company or '').lower().strip()}|{(title or '').lower().strip()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


@dataclass
class Job:
    """A normalized job posting. Every collector must produce one of these."""

    source: str                      # e.g. "remoteok", "greenhouse:stripe"
    external_id: str                 # id/slug from the source system
    title: str
    company: str
    url: str
    description: str = ""
    location_raw: str = ""           # whatever the source says about location/remote policy
    hires_remotely_from: Optional[str] = None  # explicit eligibility field, e.g. Wellfound
    salary_raw: Optional[str] = None
    job_type_raw: Optional[str] = None   # full-time / contract / part-time as stated
    posted_at: Optional[str] = None      # ISO string if known
    tags: list = field(default_factory=list)
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        self.title = _clean(self.title)
        self.company = _clean(self.company)
        self.description = _clean(self.description)
        self.location_raw = _clean(self.location_raw)

    @property
    def identity_key(self) -> str:
        """Company+title only — same role from any URL/source shares this key."""
        return identity_key(self.company, self.title)

    @property
    def dedup_key(self) -> str:
        """Primary store key: company+title (URL no longer creates duplicate alerts).

        Different locations at the same company with the exact same title still
        collapse — preferred over daily re-alerts from URL ID churn.
        """
        return self.identity_key

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dedup_key"] = self.dedup_key
        d["identity_key"] = self.identity_key
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        d = dict(d)
        d.pop("dedup_key", None)
        d.pop("identity_key", None)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
