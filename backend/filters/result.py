from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FilterResult:
    passed: bool
    reason: str
    tier: Optional[str] = None          # location tier: A/B/C/D
    detail: Optional[dict] = None       # extra structured info (e.g. years found)
