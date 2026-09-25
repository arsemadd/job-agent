"""One-shot: prune + compact data/jobs.json under GitHub's 100 MB limit."""
from __future__ import annotations

import os
import sys

from backend.storage.store import JobStore

PATH = os.path.join("data", "jobs.json")


def main() -> int:
    if not os.path.exists(PATH):
        print("no jobs.json")
        return 0
    before = os.path.getsize(PATH) / (1024 * 1024)
    store = JobStore(PATH)
    before_count = len(store.all())
    removed = store.prune(rejected_retention_days=14, keep_rejected_max=2000)
    # Merge duplicate identities: keep notified row, drop sibling rejects
    by_ident: dict[str, list[str]] = {}
    for rec in store.all():
        ident = rec.get("identity_key") or ""
        by_ident.setdefault(ident, []).append(rec["dedup_key"])
    drop = []
    for ident, keys in by_ident.items():
        if len(keys) < 2:
            continue
        notified = [
            k for k in keys
            if (store.get(k) or {}).get("status") in ("sent", "digest_sent", "notify_failed", "pending_immediate", "digest_pending")
        ]
        keep = notified[0] if notified else keys[0]
        for k in keys:
            if k != keep:
                drop.append(k)
    for k in drop:
        store._records.pop(k, None)
    store._rebuild_identity_index()
    store.save(prune_first=False)
    after = os.path.getsize(PATH) / (1024 * 1024)
    print(f"before={before:.2f}MB/{before_count} removed={removed} dupes={len(drop)} after={after:.2f}MB/{len(store.all())}")
    if after >= 95:
        print("WARNING: still near GitHub limit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
