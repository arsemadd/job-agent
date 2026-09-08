"""Thin FastAPI layer over the job store, for the dashboard.

Run locally with: uvicorn backend.app:app --reload
Serves the dashboard at / and JSON at /api/jobs and /api/stats. This process
never runs the collection pipeline itself (that's backend/pipeline.py, run on
a schedule by GitHub Actions or manually) - it only reads data/jobs.json.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.storage.store import JobStore

app = FastAPI(title="Job Matcher Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STORE_PATH = os.environ.get("JOBS_STORE_PATH", os.path.join("data", "jobs.json"))
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dashboard")


def get_store() -> JobStore:
    # Re-instantiate per request: cheap for a JSON file this size, and means
    # the dashboard always reflects the latest committed data.jobs.json
    # without needing a server restart after each scheduled run.
    return JobStore(STORE_PATH)


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


@app.get("/health")
def health():
    return {"ok": True}


if os.path.isdir(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

    @app.get("/")
    def dashboard():
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))
