"""Thin FastAPI layer over the job store, for the dashboard.

Run locally with: uvicorn backend.app:app --reload
Serves the dashboard at / and JSON at /api/jobs, /api/stats, /api/discovery.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from backend.collectors.linkedin_discovery import build_discovery
from backend.notifications import discord
from backend.storage.store import JobStore

app = FastAPI(title="Job Matcher Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STORE_PATH = os.environ.get("JOBS_STORE_PATH", os.path.join("data", "jobs.json"))
PREFS_PATH = os.path.join("config", "preferences.json")
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dashboard")


def get_store() -> JobStore:
    return JobStore(STORE_PATH)


def load_prefs() -> dict:
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


@app.get("/api/jobs")
def list_jobs(
    status: str | None = Query(None),
    min_score: int | None = Query(None),
    q: str | None = Query(None, description="Search title/company/source"),
    source: str | None = Query(None),
    decision: str | None = Query(None, description="SEND | DIGEST | REJECT"),
    sort: str = Query("score", description="score | newest | company"),
    limit: int = Query(200, le=1000),
):
    records = get_store().all()
    if status:
        records = [r for r in records if r.get("status") == status]
    if decision:
        records = [r for r in records if (r.get("decision") or "").upper() == decision.upper()]
    if min_score is not None:
        records = [r for r in records if isinstance(r.get("score"), (int, float)) and r["score"] >= min_score]
    if source:
        needle = source.lower()
        records = [r for r in records if needle in (r.get("source") or "").lower()]
    if q:
        needle = q.lower().strip()
        records = [
            r for r in records
            if needle in (r.get("title") or "").lower()
            or needle in (r.get("company") or "").lower()
            or needle in (r.get("source") or "").lower()
            or needle in (r.get("location_raw") or "").lower()
        ]

    if sort == "newest":
        records = sorted(records, key=lambda r: r.get("first_seen_at") or "", reverse=True)
    elif sort == "company":
        records = sorted(records, key=lambda r: (r.get("company") or "").lower())
    else:
        records = sorted(records, key=lambda r: (r.get("score") or -1, r.get("first_seen_at", "")), reverse=True)

    return {"count": len(records), "jobs": records[:limit]}


@app.get("/api/stats")
def stats():
    data = get_store().stats()
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        data["store_updated_at"] = raw.get("updated_at")
    except OSError:
        data["store_updated_at"] = None
    data["server_time"] = datetime.now(timezone.utc).isoformat()
    return data


@app.get("/api/discovery")
def discovery():
    prefs = load_prefs()
    roles = prefs.get("roles", {}).get("include") or [
        "Product Manager",
        "QA Analyst",
        "Product Owner",
    ]
    return build_discovery(roles, remote_only=True)


@app.post("/api/discord/retry-failed")
def retry_failed_discord():
    """Retry notify_failed rows and post a short status message."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return {"ok": False, "error": "DISCORD_WEBHOOK_URL not set"}

    store = get_store()
    failed = [r for r in store.all() if r.get("status") == "notify_failed"]
    sent_immediate = 0
    digest_sent = 0

    for record in [r for r in failed if r.get("decision") == "SEND"]:
        ok = discord.send_immediate(record, webhook)
        store.upsert(
            record["dedup_key"],
            {
                "status": "sent" if ok else "notify_failed",
                "notified_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if ok:
            sent_immediate += 1

    digest_rows = [r for r in failed if r.get("decision") == "DIGEST"]
    # also include any still-pending digests
    digest_rows.extend([r for r in store.all() if r.get("status") == "digest_pending"])
    # dedupe by key
    seen = set()
    digest_unique = []
    for r in digest_rows:
        key = r.get("dedup_key")
        if key and key not in seen:
            seen.add(key)
            digest_unique.append(r)

    if digest_unique:
        ok = discord.send_digest(digest_unique, webhook)
        status = "digest_sent" if ok else "notify_failed"
        for r in digest_unique:
            store.upsert(
                r["dedup_key"],
                {"status": status, "notified_at": datetime.now(timezone.utc).isoformat()},
            )
        if ok:
            digest_sent = len(digest_unique)

    store.save()
    summary = {
        "sent_immediate": sent_immediate,
        "digest_sent": digest_sent,
        "retried": len(failed),
        "new_postings": 0,
        "passed_hard_filters": 0,
        "scored": 0,
        "total_in_store": len(store.all()),
    }
    discord.send_run_summary(
        {
            **summary,
            "sent_immediate": sent_immediate,
            "digest_sent": digest_sent,
        },
        webhook,
    )
    return {"ok": True, **summary}


@app.post("/api/discord/test")
def test_discord():
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return {"ok": False, "error": "DISCORD_WEBHOOK_URL not set"}
    ok = discord.send_run_summary(
        {
            "sent_immediate": 0,
            "digest_sent": 0,
            "new_postings": 0,
            "passed_hard_filters": 0,
            "scored": 0,
            "total_in_store": len(get_store().all()),
        },
        webhook,
    )
    return {"ok": ok}


@app.get("/health")
def health():
    return {"ok": True}


if os.path.isdir(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

    @app.get("/")
    def dashboard():
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))
