"""Re-score jobs stuck in scoring_error (e.g. empty GEMINI_MODEL from Actions), then notify Discord."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from backend.filters.pipeline import HardFilterVerdict, run_hard_filters
from backend.matching.candidate import load_candidate_profile
from backend.matching.scoring import build_scorer
from backend.models import Job
from backend.notifications import discord
from backend.storage.store import JobStore

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("job_agent.rescore")

MAX_SCORE = int(os.environ.get("MAX_SCORE_PER_RUN", "40") or "40")


def main() -> None:
    prefs = json.load(open("config/preferences.json", encoding="utf-8"))
    profile = load_candidate_profile("config/candidate_profile.json")
    store = JobStore("data/jobs.json")
    scorer = build_scorer(profile, prefs)
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    targets = [r for r in store.all() if r.get("status") == "scoring_error"]
    logger.info("found %d scoring_error jobs; will rescore up to %d", len(targets), MAX_SCORE)

    scored = 0
    rejected = 0
    immediate_keys: list[str] = []

    for record in targets:
        if scored >= MAX_SCORE:
            break
        job = Job.from_dict(record)
        verdict = run_hard_filters(job, prefs)
        key = job.dedup_key

        if not verdict.passed:
            store.upsert(
                key,
                {
                    "hard_filter_passed": False,
                    "hard_filter_reasons": verdict.reasons,
                    "location_tier": verdict.location_tier,
                    "status": "rejected",
                    "decision": "REJECT",
                    "score": None,
                    "scoring_error": None,
                },
            )
            rejected += 1
            continue

        evaluation = scorer.score_job(job, verdict)
        scored += 1
        update = {
            "hard_filter_passed": True,
            "hard_filter_reasons": verdict.reasons,
            "location_tier": verdict.location_tier,
            "years_required_display": (
                f"{verdict.years_required}+ years (stated)" if verdict.years_required is not None else "not clearly stated"
            ),
            "score": evaluation.score,
            "why_matches": evaluation.why_matches,
            "gaps": evaluation.gaps,
            "confidence": evaluation.confidence,
            "reasoning_summary": evaluation.reasoning_summary,
            "decision": evaluation.decision,
            "scoring_error": evaluation.error,
        }
        if evaluation.error:
            update["status"] = "scoring_error"
        elif evaluation.decision == "SEND":
            update["status"] = "pending_immediate"
            immediate_keys.append(key)
        elif evaluation.decision == "DIGEST":
            update["status"] = "digest_pending"
        else:
            update["status"] = "rejected"
        store.upsert(key, update)
        logger.info(
            "scored %s @ %s -> %s score=%s",
            job.title,
            job.company,
            update["status"],
            evaluation.score,
        )
        time.sleep(1.2)

    sent_immediate = 0
    if webhook:
        for key in immediate_keys:
            record = store.get(key)
            if not record:
                continue
            ok = discord.send_immediate(record, webhook)
            store.upsert(
                key,
                {
                    "status": "sent" if ok else "notify_failed",
                    "notified_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            if ok:
                sent_immediate += 1
            time.sleep(0.8)

        pending_digest = [r for r in store.all() if r.get("status") == "digest_pending"]
        digest_sent = 0
        if pending_digest:
            ok = discord.send_digest(pending_digest, webhook)
            status = "digest_sent" if ok else "notify_failed"
            for r in pending_digest:
                store.upsert(
                    r["dedup_key"],
                    {"status": status, "notified_at": datetime.now(timezone.utc).isoformat()},
                )
            if ok:
                digest_sent = len(pending_digest)
        else:
            digest_sent = 0
    else:
        digest_sent = 0
        logger.warning("DISCORD_WEBHOOK_URL missing - skipped notify")

    store.save()
    summary = {
        "rescored": scored,
        "re_rejected_by_filters": rejected,
        "sent_immediate": sent_immediate,
        "digest_sent": digest_sent,
    }
    logger.info("rescore summary: %s", json.dumps(summary))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
