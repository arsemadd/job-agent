"""Thin FastAPI layer over the job store, for the dashboard.

Run locally with: uvicorn backend.app:app --reload
Serves the dashboard at / and JSON at /api/jobs, /api/stats, /api/discovery.
This process never runs the collection pipeline itself (that's backend/pipeline.py).
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.collectors.linkedin_discovery import build_discovery
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
    status: str | None = Query(None, description="Filter by status: sent, digest_sent, rejected, ..."),
    min_score: int | None = Query(None),
    limit: int = Query(200, le=1000),
):
    records = get_store().all()
    if status:
        records = [r for r in records if r.get("status") == status]
    if min_score is not None:
        records = [r for r in records if isinstance(r.get("score"), (int, float)) and r["score"] >= min_score]
    records = sorted(records, key=lambda r: (r.get("score") or -1, r.get("first_seen_at", "")), reverse=True)
    return {"count": len(records), "jobs": records[:limit]}


@app.get("/api/stats")
def stats():
    return get_store().stats()


@app.get("/api/discovery")
def discovery():
    """LinkedIn search links + curated board bookmarks (never scraped)."""
    prefs = load_prefs()
    roles = prefs.get("roles", {}).get("include") or [
        "Product Manager",
        "QA Analyst",
        "Product Owner",
    ]
    return build_discovery(roles, remote_only=True)


@app.get("/health")
def health():
    return {"ok": True}


if os.path.isdir(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

    @app.get("/")
    def dashboard():
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))
