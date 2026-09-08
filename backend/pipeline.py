"""Orchestrates one end-to-end run: collect -> dedupe -> hard filters -> AI
scoring -> storage -> Discord notification.

Run directly (`python -m backend.pipeline`) or imported by backend/app.py /
GitHub Actions. Every stage is defensive: one bad source, one bad job, or one
failed AI call should never take down the whole run - the brief cares more
about a reliable daily signal than a perfect one.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from backend.collectors.arbeitnow import ArbeitnowCollector
from backend.collectors.ashby import AshbyCollector
from backend.collectors.base import Collector
from backend.collectors.greenhouse import GreenhouseCollector
from backend.collectors.himalayas import HimalayasCollector
from backend.collectors.jobicy import JobicyCollector
from backend.collectors.lever import LeverCollector
from backend.collectors.mindtheproduct import MindTheProductCollector
from backend.collectors.remoteok import RemoteOKCollector
from backend.collectors.remotive import RemotiveCollector
from backend.collectors.wellfound import WellfoundCollector
from backend.collectors.weworkremotely import WeWorkRemotelyCollector
from backend.filters.pipeline import run_hard_filters
from backend.matching.candidate import load_candidate_profile
from backend.matching.scoring import build_scorer
from backend.notifications import discord
from backend.storage.store import JobStore

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("job_agent.pipeline")

PREFS_PATH = os.path.join("config", "preferences.json")
CANDIDATE_PATH = os.path.join("config", "candidate_profile.json")


def load_prefs(path: str = PREFS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_collectors(prefs: dict) -> list[Collector]:
    enabled = set(prefs.get("sources", {}).get("enabled", []))
    boards = prefs.get("sources", {}).get("greenhouse_boards", [])
    companies = prefs.get("sources", {}).get("lever_companies", [])
    ashby_companies = prefs.get("sources", {}).get("ashby_companies", [])

    all_collectors: list[Collector] = [
        RemoteOKCollector(),
        RemotiveCollector(),
        WeWorkRemotelyCollector(),
        HimalayasCollector(),
        MindTheProductCollector(),
        ArbeitnowCollector(),
        JobicyCollector(),
        GreenhouseCollector(boards),
        LeverCollector(companies),
        AshbyCollector(ashby_companies),
        WellfoundCollector(),
    ]
    return [c for c in all_collectors if c.name in enabled or c.name == "wellfound"]


def run(dry_run: bool = False, skip_notify: bool = False, store_path: str | None = None) -> dict:
    prefs = load_prefs()
    candidate_profile = load_candidate_profile(CANDIDATE_PATH)
    store = JobStore(store_path or os.path.join("data", "jobs.json"))

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not skip_notify and not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set - jobs will be scored and stored but NOT sent to Discord")
        skip_notify = True

    scorer = None
    if not dry_run:
        try:
            scorer = build_scorer(candidate_profile, prefs)
        except RuntimeError as exc:
            logger.error(str(exc))
            if not dry_run:
                raise

    collectors = build_collectors(prefs)
    logger.info("running %d collectors: %s", len(collectors), [c.name for c in collectors])

    raw_jobs = []
    for collector in collectors:
        raw_jobs.extend(collector.safe_fetch())
    logger.info("collected %d raw postings before dedup", len(raw_jobs))

    new_count = 0
    passed_filter_count = 0
    scored_count = 0
    immediate_sent = []
    run_started = datetime.now(timezone.utc).isoformat()

    for job in raw_jobs:
        key = job.dedup_key
        if store.seen(key):
            store.upsert(key, {})  # just bumps last_seen_at
            continue
        new_count += 1

        verdict = run_hard_filters(job, prefs)
        record = job.to_dict()
        record.update(
            {
                "hard_filter_passed": verdict.passed,
                "hard_filter_reasons": verdict.reasons,
                "location_tier": verdict.location_tier,
                "years_required_display": (
                    f"{verdict.years_required}+ years (stated)" if verdict.years_required is not None else "not clearly stated"
                ),
            }
        )

        if not verdict.passed:
            record.update({"status": "rejected", "decision": "REJECT", "score": None})
            store.upsert(key, record)
            continue

        passed_filter_count += 1

        if dry_run:
            record.update({"status": "dry_run_not_scored", "decision": None, "score": None})
            store.upsert(key, record)
            continue

        max_score = int(os.environ.get("MAX_SCORE_PER_RUN", "0") or "0")
        if max_score and scored_count >= max_score:
            record.update({"status": "queued_for_scoring", "decision": None, "score": None})
            store.upsert(key, record)
            continue

        evaluation = scorer.score_job(job, verdict)
        scored_count += 1
        record.update(
            {
                "score": evaluation.score,
                "why_matches": evaluation.why_matches,
                "gaps": evaluation.gaps,
                "confidence": evaluation.confidence,
                "reasoning_summary": evaluation.reasoning_summary,
                "decision": evaluation.decision,
                "scoring_error": evaluation.error,
            }
        )

        if evaluation.error:
            record["status"] = "scoring_error"
        elif evaluation.decision == "SEND":
            record["status"] = "pending_immediate"
        elif evaluation.decision == "DIGEST":
            record["status"] = "digest_pending"
        else:
            record["status"] = "rejected"

        store.upsert(key, record)

        if record["status"] == "pending_immediate":
            immediate_sent.append(key)

    # Send immediate (SEND-tier) notifications for jobs found this run.
    sent_immediate = 0
    if not skip_notify:
        for key in immediate_sent:
            record = store.get(key)
            if not record:
                continue
            ok = discord.send_immediate(record, webhook_url)
            store.upsert(key, {"status": "sent" if ok else "notify_failed", "notified_at": datetime.now(timezone.utc).isoformat()})
            if ok:
                sent_immediate += 1

    # Send one batched digest covering every DIGEST-tier job not yet digested,
    # from this run or any prior run that hasn't been flushed yet.
    digest_sent = 0
    if not skip_notify:
        pending_digest = [r for r in store.all() if r.get("status") == "digest_pending"]
        if pending_digest:
            ok = discord.send_digest(pending_digest, webhook_url)
            status = "digest_sent" if ok else "notify_failed"
            for r in pending_digest:
                store.upsert(r["dedup_key"], {"status": status, "notified_at": datetime.now(timezone.utc).isoformat()})
            if ok:
                digest_sent = len(pending_digest)

    store.save()

    summary = {
        "run_started": run_started,
        "sources_run": [c.name for c in collectors],
        "raw_postings": len(raw_jobs),
        "new_postings": new_count,
        "passed_hard_filters": passed_filter_count,
        "scored": scored_count,
        "sent_immediate": sent_immediate,
        "digest_sent": digest_sent,
        "total_in_store": len(store.all()),
    }
    logger.info("run summary: %s", json.dumps(summary))
    return summary


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    no_notify = "--skip-notify" in sys.argv or dry
    run(dry_run=dry, skip_notify=no_notify)
