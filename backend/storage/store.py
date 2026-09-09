"""Persistence + dedup for the pipeline.

Everything lives in a single JSON file (data/jobs.json) keyed by each job's
dedup_key (company+title+url hash - see backend/models.py). This is
deliberately simple: the brief's own architecture diagram calls for
`storage/jobs.json`, and a GitHub Actions runner just needs something it can
read, update, and commit back on every scheduled run - no database server to
provision.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

DEFAULT_PATH = os.path.join("data", "jobs.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._records: dict[str, dict] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = {r["dedup_key"]: r for r in data.get("jobs", [])}
            except (json.JSONDecodeError, KeyError):
                # Corrupt file shouldn't take down the whole run - back it up and start fresh.
                if os.path.exists(self.path):
                    shutil.copy(self.path, self.path + f".corrupt-{int(datetime.now().timestamp())}")
                self._records = {}
        else:
            self._records = {}

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "updated_at": _now(),
            "jobs": sorted(self._records.values(), key=lambda r: r.get("first_seen_at", ""), reverse=True),
        }
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        try:
            os.replace(tmp_path, self.path)
        except PermissionError:
            # Windows occasionally locks the destination (antivirus / editor).
            shutil.copyfile(tmp_path, self.path)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def seen(self, dedup_key: str) -> bool:
        return dedup_key in self._records

    def get(self, dedup_key: str) -> Optional[dict]:
        return self._records.get(dedup_key)

    def upsert(self, dedup_key: str, fields: dict):
        existing = self._records.get(dedup_key)
        if existing:
            existing.update(fields)
            existing["last_seen_at"] = _now()
        else:
            fields = dict(fields)
            fields["dedup_key"] = dedup_key
            fields.setdefault("first_seen_at", _now())
            fields["last_seen_at"] = _now()
            self._records[dedup_key] = fields

    def all(self) -> list[dict]:
        return list(self._records.values())

    def stats(self, since_iso: Optional[str] = None) -> dict:
        records = self.all()
        if since_iso:
            records = [r for r in records if r.get("first_seen_at", "") >= since_iso]

        found = len(records)
        passed_filters = len([r for r in records if r.get("hard_filter_passed")])
        strong = len([r for r in records if r.get("decision") == "SEND"])
        digest = len([r for r in records if r.get("decision") == "DIGEST"])
        sent_to_discord = len([r for r in records if r.get("status") in ("sent", "digest_sent")])
        notify_failed = len([r for r in records if r.get("status") == "notify_failed"])
        scored = [r.get("score") for r in records if isinstance(r.get("score"), (int, float)) and r.get("hard_filter_passed")]
        avg_score = round(sum(scored) / len(scored), 1) if scored else None

        by_source: dict[str, int] = {}
        for r in records:
            src = (r.get("source") or "unknown").split(":")[0]
            by_source[src] = by_source.get(src, 0) + 1

        return {
            "jobs_found": found,
            "passed_filters": passed_filters,
            "strong_matches": strong,
            "digest_matches": digest,
            "sent_to_discord": sent_to_discord,
            "notify_failed": notify_failed,
            "average_match": avg_score,
            "updated_at": max((r.get("last_seen_at") or "" for r in records), default=None) or None,
            "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        }
