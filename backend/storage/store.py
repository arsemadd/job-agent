"""Persistence + dedup for the pipeline.

Everything lives in a single JSON file (data/jobs.json) keyed by each job's
dedup_key (company+title hash). Compact saves + aggressive prune keep the file
under GitHub's 100 MB push limit so Actions can persist "already sent" state.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.models import identity_key as make_identity_key

DEFAULT_PATH = os.path.join("data", "jobs.json")

# Keep rejected rows briefly; keep notified/scored rows longer.
REJECTED_RETENTION_DAYS = 14
KEEP_REJECTED_MAX = 2500
DESCRIPTION_MAX_CHARS_PASSED = 4000
DESCRIPTION_MAX_CHARS_REJECTED = 0  # drop bodies for rejects — biggest size win

NOTIFIED_STATUSES = frozenset({"sent", "digest_sent", "notify_failed", "pending_immediate", "digest_pending"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class JobStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._records: dict[str, dict] = {}
        self._identity_index: dict[str, str] = {}  # identity_key -> dedup_key
        self._load()

    def _rebuild_identity_index(self):
        self._identity_index = {}
        for key, rec in self._records.items():
            ident = rec.get("identity_key") or make_identity_key(
                rec.get("company", ""), rec.get("title", "")
            )
            rec["identity_key"] = ident
            # Prefer keeping a notified record as the canonical identity hit
            existing = self._identity_index.get(ident)
            if existing is None:
                self._identity_index[ident] = key
                continue
            existing_rec = self._records.get(existing) or {}
            if existing_rec.get("status") not in NOTIFIED_STATUSES and rec.get("status") in NOTIFIED_STATUSES:
                self._identity_index[ident] = key

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = {r["dedup_key"]: r for r in data.get("jobs", []) if r.get("dedup_key")}
            except (json.JSONDecodeError, KeyError):
                if os.path.exists(self.path):
                    shutil.copy(self.path, self.path + f".corrupt-{int(datetime.now().timestamp())}")
                self._records = {}
        else:
            self._records = {}
        self._rebuild_identity_index()

    def _compact_record(self, rec: dict) -> dict:
        """Strip heavy fields so the store stays pushable to GitHub."""
        out = dict(rec)
        status = out.get("status")
        desc = out.get("description") or ""
        if status == "rejected" or out.get("decision") == "REJECT" or not out.get("hard_filter_passed"):
            out["description"] = ""
        elif len(desc) > DESCRIPTION_MAX_CHARS_PASSED:
            out["description"] = desc[:DESCRIPTION_MAX_CHARS_PASSED]
        # Drop bulky AI prose on old rejects
        if status == "rejected":
            out.pop("why_matches", None)
            out.pop("gaps", None)
            out.pop("reasoning_summary", None)
            out.pop("scoring_error", None)
        return out

    def prune(
        self,
        *,
        rejected_retention_days: int = REJECTED_RETENTION_DAYS,
        keep_rejected_max: int = KEEP_REJECTED_MAX,
    ) -> int:
        """Drop old rejected rows. Never prune notified / pending notify rows."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=rejected_retention_days)
        rejected = []
        keep: dict[str, dict] = {}
        for key, rec in self._records.items():
            status = rec.get("status")
            if status in NOTIFIED_STATUSES or status in ("scoring_error", "queued_for_scoring", "dry_run_not_scored"):
                keep[key] = rec
                continue
            if status != "rejected" and rec.get("hard_filter_passed"):
                keep[key] = rec
                continue
            rejected.append((key, rec))

        rejected.sort(key=lambda kr: kr[1].get("last_seen_at") or kr[1].get("first_seen_at") or "", reverse=True)
        kept_rejected = 0
        for key, rec in rejected:
            seen_at = _parse_iso(rec.get("last_seen_at") or rec.get("first_seen_at"))
            if kept_rejected >= keep_rejected_max:
                continue
            if seen_at and seen_at < cutoff and kept_rejected >= min(500, keep_rejected_max):
                continue
            keep[key] = rec
            kept_rejected += 1

        removed = len(self._records) - len(keep)
        self._records = keep
        self._rebuild_identity_index()
        return removed

    def save(self, *, prune_first: bool = True):
        if prune_first:
            removed = self.prune()
            if removed:
                # Logged by caller if needed; keep this layer quiet.
                pass
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "updated_at": _now(),
            "jobs": [
                self._compact_record(r)
                for r in sorted(self._records.values(), key=lambda r: r.get("first_seen_at", ""), reverse=True)
            ],
        }
        tmp_path = self.path + ".tmp"
        # Compact JSON (no indent) — critical for staying under GitHub's 100 MB limit
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        try:
            os.replace(tmp_path, self.path)
        except PermissionError:
            shutil.copyfile(tmp_path, self.path)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def seen(self, dedup_key: str) -> bool:
        return dedup_key in self._records

    def seen_identity(self, company: str, title: str) -> bool:
        """True if we already stored this company+title under any dedup key."""
        return make_identity_key(company, title) in self._identity_index

    def already_notified_identity(self, company: str, title: str) -> bool:
        """True if this company+title was already sent / digest-sent / pending notify."""
        ident = make_identity_key(company, title)
        key = self._identity_index.get(ident)
        if not key:
            return False
        rec = self._records.get(key) or {}
        return rec.get("status") in NOTIFIED_STATUSES or rec.get("notified_at")

    def get(self, dedup_key: str) -> Optional[dict]:
        return self._records.get(dedup_key)

    def upsert(self, dedup_key: str, fields: dict):
        existing = self._records.get(dedup_key)
        if existing:
            existing.update(fields)
            existing["last_seen_at"] = _now()
            if "company" in fields or "title" in fields or "identity_key" not in existing:
                existing["identity_key"] = existing.get("identity_key") or make_identity_key(
                    existing.get("company", ""), existing.get("title", "")
                )
            self._identity_index[existing["identity_key"]] = dedup_key
        else:
            fields = dict(fields)
            fields["dedup_key"] = dedup_key
            fields.setdefault("first_seen_at", _now())
            fields["last_seen_at"] = _now()
            fields["identity_key"] = fields.get("identity_key") or make_identity_key(
                fields.get("company", ""), fields.get("title", "")
            )
            self._records[dedup_key] = fields
            self._identity_index[fields["identity_key"]] = dedup_key

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
        scored = [
            r.get("score")
            for r in records
            if isinstance(r.get("score"), (int, float)) and r.get("hard_filter_passed")
        ]
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
