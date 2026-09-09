"""Retry notify_failed Discord deliveries against the live webhook."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from backend.notifications import discord
from backend.storage.store import JobStore


def main() -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        raise SystemExit("DISCORD_WEBHOOK_URL missing")

    store = JobStore("data/jobs.json")
    failed = [r for r in store.all() if r.get("status") == "notify_failed"]
    print("failed", len(failed))

    sent_immediate = 0
    for record in [r for r in failed if r.get("decision") == "SEND"]:
        ok = discord.send_immediate(record, webhook)
        store.upsert(
            record["dedup_key"],
            {
                "status": "sent" if ok else "notify_failed",
                "notified_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        print("immediate", ok, record.get("score"), record.get("title"))
        if ok:
            sent_immediate += 1

    digest_rows = [r for r in failed if r.get("decision") == "DIGEST"]
    digest_rows.extend([r for r in store.all() if r.get("status") == "digest_pending"])
    seen = set()
    unique = []
    for r in digest_rows:
        key = r.get("dedup_key")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    digest_sent = 0
    if unique:
        ok = discord.send_digest(unique, webhook)
        status = "digest_sent" if ok else "notify_failed"
        for r in unique:
            store.upsert(
                r["dedup_key"],
                {"status": status, "notified_at": datetime.now(timezone.utc).isoformat()},
            )
        digest_sent = len(unique) if ok else 0
        print("digest", ok, digest_sent)

    store.save()
    summary = {
        "sent_immediate": sent_immediate,
        "digest_sent": digest_sent,
        "new_postings": 0,
        "passed_hard_filters": 0,
        "scored": 0,
        "total_in_store": len(store.all()),
    }
    ok = discord.send_run_summary(summary, webhook)
    print("summary", ok, summary)


if __name__ == "__main__":
    main()
