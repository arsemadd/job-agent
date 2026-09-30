"""CareerOS Backend API.

End-to-end Job Search Operating System API powering:
- 10 Navigation views (Dashboard, Jobs, Applications, Interviews, Documents, Companies, Tasks, Analytics, AI Assistant, Settings)
- 7-Tab Application Record details
- Full lifecycle state machine (DISCOVERED -> SHORTLISTED -> SAVED -> PREPARING -> APPLIED -> SCREENING -> INTERVIEW -> OFFER -> ACCEPTED / REJECTED / WITHDRAWN)
- Cover letter versioning & visual diff computation
- AI application strategy & tailoring generator
- Analytics & learning engine
- Sourcing pipeline trigger across 20+ live collectors and 31+ discovery boards
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from backend.collectors.linkedin_discovery import build_discovery, BOARD_LINKS
from backend.database import get_db, init_db, migrate_from_json, compute_diff, DB_PATH
from backend.strategy import generate_application_strategy, load_candidate_profile

app = FastAPI(title="CareerOS API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dashboard")
PREFS_PATH = os.path.join("config", "preferences.json")
PROFILE_PATH = os.path.join("config", "candidate_profile.json")

from backend.scheduler import start_scheduler

# Ensure database is initialized on startup
@app.on_event("startup")
def on_startup():
    init_db()
    migrate_from_json()
    start_scheduler()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def log_activity(conn: sqlite3.Connection, action_type: str, description: str, job_id: Optional[str] = None, application_id: Optional[str] = None):
    conn.execute("""
    INSERT INTO activity_log (id, job_id, application_id, action_type, description, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), job_id, application_id, action_type, description, datetime.now(timezone.utc).isoformat()))


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# 1. Dashboard & General Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def get_stats():
    with get_db() as conn:
        total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        high_matches = conn.execute("SELECT COUNT(*) FROM jobs WHERE score >= 85").fetchone()[0]
        shortlisted = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'SHORTLISTED'").fetchone()[0]
        saved = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'SAVED'").fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'APPLIED'").fetchone()[0]
        screening = conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'SCREENING'").fetchone()[0]
        interviewing = conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'INTERVIEW'").fetchone()[0]
        offers = conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'OFFER'").fetchone()[0]
        pending_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE is_completed = 0").fetchone()[0]

        upcoming_interviews = [row_to_dict(r) for r in conn.execute("""
            SELECT i.*, j.title as job_title, j.company as job_company
            FROM interviews i
            JOIN applications a ON i.application_id = a.id
            JOIN jobs j ON a.job_id = j.id
            WHERE i.completed_at IS NULL
            ORDER BY i.scheduled_at ASC LIMIT 5
        """).fetchall()]

        recent_activity = [row_to_dict(r) for r in conn.execute("""
            SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 8
        """).fetchall()]

    return {
        "total_jobs": total_jobs,
        "high_matches": high_matches,
        "shortlisted": shortlisted,
        "saved": saved,
        "applied": applied,
        "screening": screening,
        "interviewing": interviewing,
        "offers": offers,
        "pending_tasks": pending_tasks,
        "upcoming_interviews": upcoming_interviews,
        "recent_activity": recent_activity,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 2. Jobs Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
def list_jobs(
    status: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    max_score: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort: str = Query("score", description="score | newest | company"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    query = "SELECT * FROM jobs WHERE 1=1"
    params: List[Any] = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if min_score is not None:
        query += " AND score >= ?"
        params.append(min_score)
    if max_score is not None:
        query += " AND score <= ?"
        params.append(max_score)
    if source:
        query += " AND lower(source) LIKE ?"
        params.append(f"%{source.lower()}%")
    if q:
        needle = f"%{q.lower().strip()}%"
        query += " AND (lower(title) LIKE ? OR lower(company) LIKE ? OR lower(description) LIKE ? OR lower(location_raw) LIKE ?)"
        params.extend([needle, needle, needle, needle])

    if sort == "newest":
        query += " ORDER BY posted_at DESC, fetched_at DESC"
    elif sort == "company":
        query += " ORDER BY company ASC"
    else:
        query += " ORDER BY score DESC, fetched_at DESC"

    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        jobs = []
        for r in rows:
            d = row_to_dict(r)
            try:
                d["tags"] = json.loads(d.get("tags_json") or "[]")
            except Exception:
                d["tags"] = []
            jobs.append(d)

        count_query = "SELECT COUNT(*) FROM jobs"
        total = conn.execute(count_query).fetchone()[0]

    return {"count": len(jobs), "total": total, "jobs": jobs}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with get_db() as conn:
        job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        job = row_to_dict(job_row)
        try:
            job["tags"] = json.loads(job.get("tags_json") or "[]")
        except Exception:
            job["tags"] = []

        # Find linked application if exists
        app_row = conn.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        application = None
        cover_letters = []
        interviews = []
        tasks = []
        activities = []

        if app_row:
            application = row_to_dict(app_row)
            try:
                application["qa_answers"] = json.loads(application.get("qa_answers_json") or "[]")
                application["portfolio_projects"] = json.loads(application.get("portfolio_projects_json") or "[]")
                application["submitted_links"] = json.loads(application.get("submitted_links_json") or "{}")
                application["strategy"] = json.loads(application.get("strategy_json") or "{}")
            except Exception:
                pass

            app_id = application["id"]
            cover_letters = [row_to_dict(r) for r in conn.execute(
                "SELECT * FROM cover_letters WHERE application_id = ? ORDER BY version_number ASC", (app_id,)
            ).fetchall()]

            interviews = [row_to_dict(r) for r in conn.execute(
                "SELECT * FROM interviews WHERE application_id = ? ORDER BY scheduled_at ASC", (app_id,)
            ).fetchall()]

            tasks = [row_to_dict(r) for r in conn.execute(
                "SELECT * FROM tasks WHERE application_id = ? ORDER BY due_date ASC", (app_id,)
            ).fetchall()]

            activities = [row_to_dict(r) for r in conn.execute(
                "SELECT * FROM activity_log WHERE application_id = ? OR job_id = ? ORDER BY created_at DESC", (app_id, job_id)
            ).fetchall()]
        else:
            activities = [row_to_dict(r) for r in conn.execute(
                "SELECT * FROM activity_log WHERE job_id = ? ORDER BY created_at DESC", (job_id,)
            ).fetchall()]

        # Get available resume versions
        resumes = [row_to_dict(r) for r in conn.execute("SELECT * FROM resume_versions ORDER BY created_at DESC").fetchall()]

    return {
        "job": job,
        "application": application,
        "cover_letters": cover_letters,
        "interviews": interviews,
        "tasks": tasks,
        "activities": activities,
        "resume_versions": resumes,
    }


class JobStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


@app.patch("/api/jobs/{job_id}/status")
def update_job_status(job_id: str, payload: JobStatusUpdate):
    now_iso = datetime.now(timezone.utc).isoformat()
    valid_statuses = [
        "DISCOVERED", "SHORTLISTED", "SAVED", "PREPARING", "APPLIED",
        "SCREENING", "INTERVIEW", "OFFER", "ACCEPTED", "REJECTED", "WITHDRAWN", "DISMISSED"
    ]
    status = payload.status.upper()
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    with get_db() as conn:
        job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        old_status = job_row["status"]
        conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso, job_id))

        # Check if an application already exists for this job
        app_row = conn.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        app_id = None

        if status in ["SHORTLISTED", "SAVED", "PREPARING", "APPLIED", "SCREENING", "INTERVIEW", "OFFER"]:
            if not app_row:
                app_id = str(uuid.uuid4())
                conn.execute("""
                INSERT INTO applications (id, job_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """, (app_id, job_id, status, now_iso, now_iso))
            else:
                app_id = app_row["id"]
                conn.execute("UPDATE applications SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso, app_id))

        log_activity(conn, "STATUS_CHANGE", f"Status changed from {old_status} to {status}. {payload.notes or ''}".strip(), job_id, app_id)

    return {"success": True, "job_id": job_id, "status": status}


# ---------------------------------------------------------------------------
# 3. Applications & Kanban Pipeline Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/applications")
def list_applications():
    """Retrieve all applications in the pipeline joined with job details."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                a.*,
                j.title as job_title,
                j.company as job_company,
                j.url as job_url,
                j.location_raw as job_location,
                j.remote_tier as job_remote_tier,
                j.score as job_score,
                j.source as job_source,
                j.salary_raw as job_salary,
                r.name as resume_version_name,
                (SELECT COUNT(*) FROM interviews WHERE application_id = a.id) as interview_count,
                (SELECT COUNT(*) FROM cover_letters WHERE application_id = a.id) as cover_letter_count
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            LEFT JOIN resume_versions r ON a.resume_version_id = r.id
            ORDER BY a.updated_at DESC
        """).fetchall()

        applications = []
        for r in rows:
            d = row_to_dict(r)
            try:
                d["qa_answers"] = json.loads(d.get("qa_answers_json") or "[]")
                d["portfolio_projects"] = json.loads(d.get("portfolio_projects_json") or "[]")
                d["submitted_links"] = json.loads(d.get("submitted_links_json") or "{}")
            except Exception:
                pass
            applications.append(d)

    return {"count": len(applications), "applications": applications}


class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    applied_at: Optional[str] = None
    resume_version_id: Optional[str] = None
    cover_letter_version_id: Optional[str] = None
    qa_answers: Optional[List[Dict[str, str]]] = None
    portfolio_projects: Optional[List[str]] = None
    submitted_links: Optional[Dict[str, str]] = None
    notes: Optional[str] = None
    follow_up_date: Optional[str] = None
    salary_offered: Optional[str] = None
    outcome_reason: Optional[str] = None


@app.patch("/api/applications/{app_id}")
def update_application(app_id: str, payload: ApplicationUpdate):
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        app_row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not app_row:
            raise HTTPException(status_code=404, detail="Application not found")

        updates = []
        params = []

        if payload.status is not None:
            updates.append("status = ?")
            params.append(payload.status.upper())
            # also sync job status
            conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (payload.status.upper(), now_iso, app_row["job_id"]))
            log_activity(conn, "STATUS_CHANGE", f"Application moved to {payload.status.upper()}", app_row["job_id"], app_id)

        if payload.applied_at is not None:
            updates.append("applied_at = ?")
            params.append(payload.applied_at)

        if payload.resume_version_id is not None:
            updates.append("resume_version_id = ?")
            params.append(payload.resume_version_id)

        if payload.cover_letter_version_id is not None:
            updates.append("cover_letter_version_id = ?")
            params.append(payload.cover_letter_version_id)

        if payload.qa_answers is not None:
            updates.append("qa_answers_json = ?")
            params.append(json.dumps(payload.qa_answers))

        if payload.portfolio_projects is not None:
            updates.append("portfolio_projects_json = ?")
            params.append(json.dumps(payload.portfolio_projects))

        if payload.submitted_links is not None:
            updates.append("submitted_links_json = ?")
            params.append(json.dumps(payload.submitted_links))

        if payload.notes is not None:
            updates.append("notes = ?")
            params.append(payload.notes)

        if payload.follow_up_date is not None:
            updates.append("follow_up_date = ?")
            params.append(payload.follow_up_date)

        if payload.salary_offered is not None:
            updates.append("salary_offered = ?")
            params.append(payload.salary_offered)

        if payload.outcome_reason is not None:
            updates.append("outcome_reason = ?")
            params.append(payload.outcome_reason)

        updates.append("updated_at = ?")
        params.append(now_iso)
        params.append(app_id)

        conn.execute(f"UPDATE applications SET {', '.join(updates)} WHERE id = ?", params)

    return {"success": True, "application_id": app_id}


class ApplicationSubmissionRecord(BaseModel):
    resume_version_id: str
    cover_letter_text: Optional[str] = None
    cover_letter_angle: Optional[str] = "Technical PM + Delivery"
    qa_answers: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    portfolio_projects: Optional[List[str]] = Field(default_factory=list)
    submitted_links: Optional[Dict[str, str]] = Field(default_factory=dict)
    notes: Optional[str] = None


@app.post("/api/applications/{app_id}/submit")
def record_application_submission(app_id: str, payload: ApplicationSubmissionRecord):
    """Records an application as formally submitted with exact document and answer snapshots."""
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        app_row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not app_row:
            raise HTTPException(status_code=404, detail="Application not found")

        job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (app_row["job_id"],)).fetchone()
        company = job_row["company"] if job_row else "Company"

        # Create submitted cover letter version if text provided
        cl_id = None
        if payload.cover_letter_text:
            cl_id = str(uuid.uuid4())
            existing_versions = conn.execute("SELECT COUNT(*) FROM cover_letters WHERE application_id = ?", (app_id,)).fetchone()[0]
            v_num = existing_versions + 1
            conn.execute("""
            INSERT INTO cover_letters (id, application_id, version_number, version_label, angle_tag, content, is_ai_assisted, is_manually_edited, is_submitted, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1, ?)
            """, (cl_id, app_id, v_num, f"v{v_num} (Submitted)", payload.cover_letter_angle, payload.cover_letter_text, now_iso))

        # Update application record
        conn.execute("""
        UPDATE applications SET
            status = 'APPLIED',
            applied_at = ?,
            resume_version_id = ?,
            cover_letter_version_id = COALESCE(?, cover_letter_version_id),
            qa_answers_json = ?,
            portfolio_projects_json = ?,
            submitted_links_json = ?,
            notes = COALESCE(?, notes),
            updated_at = ?
        WHERE id = ?
        """, (
            now_iso,
            payload.resume_version_id,
            cl_id,
            json.dumps(payload.qa_answers or []),
            json.dumps(payload.portfolio_projects or []),
            json.dumps(payload.submitted_links or {}),
            payload.notes,
            now_iso,
            app_id
        ))

        # Update job status
        conn.execute("UPDATE jobs SET status = 'APPLIED', updated_at = ? WHERE id = ?", (now_iso, app_row["job_id"]))

        # Create automatic follow-up task 7 days out
        task_id = str(uuid.uuid4())
        due_7d = datetime.fromtimestamp(datetime.now().timestamp() + 7 * 86400).strftime("%Y-%m-%d")
        conn.execute("""
        INSERT INTO tasks (id, application_id, title, description, due_date, priority, is_completed, created_at)
        VALUES (?, ?, ?, ?, ?, 'HIGH', 0, ?)
        """, (task_id, app_id, f"Follow up on application with {company}", "Check application status or connect with hiring team on LinkedIn", due_7d, now_iso))

        log_activity(conn, "APPLICATION_SUBMITTED", f"Submitted application to {company} using {payload.resume_version_id}", app_row["job_id"], app_id)

    return {"success": True, "application_id": app_id, "status": "APPLIED"}


# ---------------------------------------------------------------------------
# 4. Cover Letter Versioning & Diffing Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/applications/{app_id}/cover-letters")
def list_cover_letters(app_id: str):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM cover_letters WHERE application_id = ? ORDER BY version_number ASC
        """, (app_id,)).fetchall()
        versions = [row_to_dict(r) for r in rows]
    return {"count": len(versions), "versions": versions}


class CreateCoverLetterVersion(BaseModel):
    version_label: str
    angle_tag: Optional[str] = "General"
    content: str
    is_ai_assisted: bool = True
    is_manually_edited: bool = False
    is_submitted: bool = False


@app.post("/api/applications/{app_id}/cover-letters")
def create_cover_letter_version(app_id: str, payload: CreateCoverLetterVersion):
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM cover_letters WHERE application_id = ?", (app_id,)).fetchone()[0]
        v_num = count + 1
        cl_id = str(uuid.uuid4())

        conn.execute("""
        INSERT INTO cover_letters (id, application_id, version_number, version_label, angle_tag, content, is_ai_assisted, is_manually_edited, is_submitted, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cl_id, app_id, v_num, payload.version_label or f"v{v_num}",
            payload.angle_tag or "General", payload.content,
            1 if payload.is_ai_assisted else 0,
            1 if payload.is_manually_edited else 0,
            1 if payload.is_submitted else 0,
            now_iso
        ))

        # update application pointer to latest version
        conn.execute("UPDATE applications SET cover_letter_version_id = ?, updated_at = ? WHERE id = ?", (cl_id, now_iso, app_id))

        log_activity(conn, "COVER_LETTER_CREATED", f"Created cover letter {payload.version_label} (v{v_num})", application_id=app_id)

    return {"success": True, "id": cl_id, "version_number": v_num}


@app.get("/api/applications/{app_id}/cover-letters/diff")
def diff_cover_letters(
    app_id: str,
    v_from: int = Query(..., description="Source version number"),
    v_to: int = Query(..., description="Target version number"),
):
    with get_db() as conn:
        row_a = conn.execute("SELECT * FROM cover_letters WHERE application_id = ? AND version_number = ?", (app_id, v_from)).fetchone()
        row_b = conn.execute("SELECT * FROM cover_letters WHERE application_id = ? AND version_number = ?", (app_id, v_to)).fetchone()

        if not row_a or not row_b:
            raise HTTPException(status_code=404, detail="One or both versions not found for diff")

        text_a = row_a["content"]
        text_b = row_b["content"]
        diff_result = compute_diff(text_a, text_b)
        diff_result["from_version"] = {"number": row_a["version_number"], "label": row_a["version_label"], "angle": row_a["angle_tag"]}
        diff_result["to_version"] = {"number": row_b["version_number"], "label": row_b["version_label"], "angle": row_b["angle_tag"]}

    return diff_result


# ---------------------------------------------------------------------------
# 5. AI Application Strategy & Tailoring
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/strategy")
def generate_strategy_for_job(job_id: str):
    """Generates a tailored application strategy and saves it to the application record."""
    with get_db() as conn:
        job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        title = job_row["title"]
        company = job_row["company"]
        description = job_row["description"] or ""

        strategy = generate_application_strategy(title, company, description)

        # Store strategy in application if exists, or create application in SHORTLISTED status
        app_row = conn.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        now_iso = datetime.now(timezone.utc).isoformat()

        if not app_row:
            app_id = str(uuid.uuid4())
            conn.execute("""
            INSERT INTO applications (id, job_id, status, strategy_json, created_at, updated_at)
            VALUES (?, ?, 'SHORTLISTED', ?, ?, ?)
            """, (app_id, job_id, json.dumps(strategy), now_iso, now_iso))
            conn.execute("UPDATE jobs SET status = 'SHORTLISTED', updated_at = ? WHERE id = ?", (now_iso, job_id))
        else:
            app_id = app_row["id"]
            conn.execute("""
            UPDATE applications SET strategy_json = ?, updated_at = ? WHERE id = ?
            """, (json.dumps(strategy), now_iso, app_id))

        # Check if cover letter already exists, if not create v1 draft automatically
        cl_exists = conn.execute("SELECT COUNT(*) FROM cover_letters WHERE application_id = ?", (app_id,)).fetchone()[0]
        if cl_exists == 0 and strategy.get("draft_cover_letter"):
            cl_id = str(uuid.uuid4())
            conn.execute("""
            INSERT INTO cover_letters (id, application_id, version_number, version_label, angle_tag, content, is_ai_assisted, is_manually_edited, is_submitted, created_at)
            VALUES (?, ?, 1, 'v1 (AI Strategy Draft)', ?, ?, 1, 0, 0, ?)
            """, (cl_id, app_id, strategy.get("cover_letter_angle", "Strategy Draft"), strategy["draft_cover_letter"], now_iso))
            conn.execute("UPDATE applications SET cover_letter_version_id = ? WHERE id = ?", (cl_id, app_id))

        log_activity(conn, "STRATEGY_GENERATED", f"Generated AI application strategy for {title} at {company}", job_id, app_id)

    return {"success": True, "job_id": job_id, "application_id": app_id, "strategy": strategy}


# ---------------------------------------------------------------------------
# 6. Interviews Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/interviews")
def list_interviews():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT i.*, j.title as job_title, j.company as job_company, j.url as job_url, a.status as app_status
            FROM interviews i
            JOIN applications a ON i.application_id = a.id
            JOIN jobs j ON a.job_id = j.id
            ORDER BY i.scheduled_at ASC
        """).fetchall()
        return {"interviews": [row_to_dict(r) for r in rows]}


class CreateInterview(BaseModel):
    application_id: str
    round_name: str
    scheduled_at: str
    interviewer_name: Optional[str] = None
    interviewer_title: Optional[str] = None
    interviewer_linkedin: Optional[str] = None
    prep_notes: Optional[str] = None


@app.post("/api/interviews")
def create_interview(payload: CreateInterview):
    now_iso = datetime.now(timezone.utc).isoformat()
    interview_id = str(uuid.uuid4())
    with get_db() as conn:
        app_row = conn.execute("SELECT * FROM applications WHERE id = ?", (payload.application_id,)).fetchone()
        if not app_row:
            raise HTTPException(status_code=404, detail="Application not found")

        conn.execute("""
        INSERT INTO interviews (id, application_id, round_name, scheduled_at, interviewer_name, interviewer_title, interviewer_linkedin, prep_notes, outcome, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """, (
            interview_id, payload.application_id, payload.round_name, payload.scheduled_at,
            payload.interviewer_name, payload.interviewer_title, payload.interviewer_linkedin,
            payload.prep_notes or "", now_iso
        ))

        # Advance status to INTERVIEW if not already
        conn.execute("UPDATE applications SET status = 'INTERVIEW', updated_at = ? WHERE id = ?", (now_iso, payload.application_id))
        conn.execute("UPDATE jobs SET status = 'INTERVIEW', updated_at = ? WHERE id = ?", (now_iso, app_row["job_id"]))

        log_activity(conn, "INTERVIEW_SCHEDULED", f"Scheduled {payload.round_name} for {payload.scheduled_at}", app_row["job_id"], payload.application_id)

    return {"success": True, "interview_id": interview_id}


class UpdateInterview(BaseModel):
    completed_at: Optional[str] = None
    questions_asked: Optional[List[str]] = None
    debrief_notes: Optional[str] = None
    outcome: Optional[str] = None


@app.patch("/api/interviews/{interview_id}")
def update_interview(interview_id: str, payload: UpdateInterview):
    with get_db() as conn:
        int_row = conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone()
        if not int_row:
            raise HTTPException(status_code=404, detail="Interview not found")

        updates = []
        params = []
        if payload.completed_at is not None:
            updates.append("completed_at = ?")
            params.append(payload.completed_at)
        if payload.questions_asked is not None:
            updates.append("questions_asked_json = ?")
            params.append(json.dumps(payload.questions_asked))
        if payload.debrief_notes is not None:
            updates.append("debrief_notes = ?")
            params.append(payload.debrief_notes)
        if payload.outcome is not None:
            updates.append("outcome = ?")
            params.append(payload.outcome.upper())

        if updates:
            params.append(interview_id)
            conn.execute(f"UPDATE interviews SET {', '.join(updates)} WHERE id = ?", params)

    return {"success": True, "interview_id": interview_id}


# ---------------------------------------------------------------------------
# 7. Tasks Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/tasks")
def list_tasks():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT t.*, j.title as job_title, j.company as job_company
            FROM tasks t
            LEFT JOIN applications a ON t.application_id = a.id
            LEFT JOIN jobs j ON a.job_id = j.id
            ORDER BY t.is_completed ASC, t.due_date ASC
        """).fetchall()
        return {"tasks": [row_to_dict(r) for r in rows]}


class CreateTask(BaseModel):
    application_id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    due_date: Optional[str] = None
    priority: Optional[str] = "MEDIUM"


@app.post("/api/tasks")
def create_task(payload: CreateTask):
    task_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
        INSERT INTO tasks (id, application_id, title, description, due_date, priority, is_completed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """, (task_id, payload.application_id, payload.title, payload.description, payload.due_date, payload.priority, now_iso))
    return {"success": True, "task_id": task_id}


@app.patch("/api/tasks/{task_id}/toggle")
def toggle_task(task_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT is_completed FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        new_val = 0 if row["is_completed"] else 1
        conn.execute("UPDATE tasks SET is_completed = ? WHERE id = ?", (new_val, task_id))
    return {"success": True, "is_completed": bool(new_val)}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return {"success": True}


# ---------------------------------------------------------------------------
# 8. Learning & Analytics Engine
# ---------------------------------------------------------------------------

@app.get("/api/analytics")
def get_analytics():
    """Calculates conversion funnel, score-to-outcome correlation, and source ROI."""
    with get_db() as conn:
        # Funnel counts
        discovered = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        shortlisted = conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('SHORTLISTED', 'SAVED', 'PREPARING', 'APPLIED', 'SCREENING', 'INTERVIEW', 'OFFER', 'ACCEPTED', 'REJECTED')").fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('APPLIED', 'SCREENING', 'INTERVIEW', 'OFFER', 'ACCEPTED')").fetchone()[0]
        screened = conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('SCREENING', 'INTERVIEW', 'OFFER', 'ACCEPTED')").fetchone()[0]
        interviewed = conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('INTERVIEW', 'OFFER', 'ACCEPTED')").fetchone()[0]
        offered = conn.execute("SELECT COUNT(*) FROM applications WHERE status IN ('OFFER', 'ACCEPTED')").fetchone()[0]
        accepted = conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'ACCEPTED'").fetchone()[0]

        # Score brackets correlation
        brackets = [
            {"bracket": "90–100", "min": 90, "max": 100},
            {"bracket": "80–89", "min": 80, "max": 89},
            {"bracket": "70–79", "min": 70, "max": 79},
            {"bracket": "60–69", "min": 60, "max": 69},
        ]
        score_performance = []
        for b in brackets:
            total_in_b = conn.execute("SELECT COUNT(*) FROM jobs WHERE score BETWEEN ? AND ?", (b["min"], b["max"])).fetchone()[0]
            applied_in_b = conn.execute("""
                SELECT COUNT(*) FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE j.score BETWEEN ? AND ? AND a.status IN ('APPLIED', 'SCREENING', 'INTERVIEW', 'OFFER', 'ACCEPTED')
            """, (b["min"], b["max"])).fetchone()[0]
            interview_in_b = conn.execute("""
                SELECT COUNT(*) FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE j.score BETWEEN ? AND ? AND a.status IN ('INTERVIEW', 'OFFER', 'ACCEPTED')
            """, (b["min"], b["max"])).fetchone()[0]

            rate = round((interview_in_b / applied_in_b * 100), 1) if applied_in_b > 0 else 0.0
            score_performance.append({
                "bracket": b["bracket"],
                "total_jobs": total_in_b,
                "applied": applied_in_b,
                "interviews": interview_in_b,
                "conversion_rate": rate,
            })

        # Source ROI
        source_rows = conn.execute("""
            SELECT j.source, COUNT(a.id) as applied_count,
                   SUM(CASE WHEN a.status IN ('INTERVIEW', 'OFFER', 'ACCEPTED') THEN 1 ELSE 0 END) as interview_count
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            GROUP BY j.source
            ORDER BY applied_count DESC LIMIT 10
        """).fetchall()

        source_roi = [row_to_dict(r) for r in source_rows]

        # Resume Version Performance
        resume_rows = conn.execute("""
            SELECT r.name, COUNT(a.id) as usage_count,
                   SUM(CASE WHEN a.status IN ('INTERVIEW', 'OFFER', 'ACCEPTED') THEN 1 ELSE 0 END) as interview_count
            FROM applications a
            JOIN resume_versions r ON a.resume_version_id = r.id
            GROUP BY r.name
            ORDER BY usage_count DESC
        """).fetchall()
        resume_roi = [row_to_dict(r) for r in resume_rows]

    return {
        "funnel": {
            "discovered": discovered,
            "shortlisted": shortlisted,
            "applied": applied,
            "screening": screened,
            "interview": interviewed,
            "offer": offered,
            "accepted": accepted,
        },
        "score_performance": score_performance,
        "source_roi": source_roi,
        "resume_performance": resume_roi,
        "key_takeaways": [
            "Roles with match scores >= 85 have demonstrated a significantly higher screening-to-interview progression.",
            "Applications featuring Bravura EHR and Composity ERP evidence convert consistently across B2B SaaS roles.",
            "Direct ATS boards (Greenhouse, Ashby, Lever) yield faster response turnaround than broad aggregate boards."
        ]
    }


# ---------------------------------------------------------------------------
# 9. Discovery & External Boards
# ---------------------------------------------------------------------------

@app.get("/api/discovery")
def get_discovery_links():
    prefs = load_prefs()
    roles = prefs.get("roles", {}).get("include", ["Product Manager", "Technical Product Manager"])
    return build_discovery(roles, remote_only=True)


# ---------------------------------------------------------------------------
# 10. Settings & Preferences
# ---------------------------------------------------------------------------

@app.get("/api/profile")
def get_profile():
    return load_candidate_profile()


@app.put("/api/profile")
def save_profile(payload: dict = Body(...)):
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return {"success": True}


@app.get("/api/preferences")
def get_preferences():
    return load_prefs()


@app.put("/api/preferences")
def save_preferences(payload: dict = Body(...)):
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return {"success": True}


def load_prefs() -> dict:
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 11. Discord Alerts Tracking & 1-Click Application Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/alerts")
def get_alerts(
    unapplied_only: bool = Query(False),
    limit: int = Query(100, le=500),
):
    """Retrieve all jobs that have been alerted to Discord, along with their application tracking status."""
    with get_db() as conn:
        query = """
            SELECT 
                j.*,
                a.id as application_id,
                a.status as application_status,
                a.applied_at as application_applied_at
            FROM jobs j
            LEFT JOIN applications a ON j.id = a.job_id
            WHERE (j.notified_at IS NOT NULL OR j.score >= 85 OR (j.decision IS NOT NULL AND upper(j.decision) = 'SEND'))
        """
        if unapplied_only:
            query += " AND (a.status IS NULL OR a.status IN ('DISCOVERED', 'SHORTLISTED', 'SAVED', 'PREPARING'))"
        
        query += " ORDER BY COALESCE(j.notified_at, j.first_seen_at) DESC, j.score DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()
        alerts = []
        for r in rows:
            d = row_to_dict(r)
            try:
                d["tags"] = json.loads(d.get("tags_json") or "[]")
            except Exception:
                d["tags"] = []
            alerts.append(d)

        total_alerts = conn.execute("""
            SELECT COUNT(*) FROM jobs WHERE (notified_at IS NOT NULL OR score >= 85 OR (decision IS NOT NULL AND upper(decision) = 'SEND'))
        """).fetchone()[0]

        unapplied_count = conn.execute("""
            SELECT COUNT(*) FROM jobs j
            LEFT JOIN applications a ON j.id = a.job_id
            WHERE (j.notified_at IS NOT NULL OR j.score >= 85 OR (j.decision IS NOT NULL AND upper(j.decision) = 'SEND'))
              AND (a.status IS NULL OR a.status IN ('DISCOVERED', 'SHORTLISTED', 'SAVED', 'PREPARING'))
        """).fetchone()[0]

    return {
        "count": len(alerts),
        "total_alerts": total_alerts,
        "unapplied_count": unapplied_count,
        "alerts": alerts,
    }


@app.post("/api/alerts/{job_id}/apply")
def quick_apply_alert(job_id: str):
    """1-click application tracker from a Discord alert."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        company = job["company"]
        title = job["title"]

        app_row = conn.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        if not app_row:
            app_id = str(uuid.uuid4())
            conn.execute("""
            INSERT INTO applications (id, job_id, status, applied_at, resume_version_id, created_at, updated_at)
            VALUES (?, ?, 'APPLIED', ?, 'resume-pm-v4', ?, ?)
            """, (app_id, job_id, now_iso, now_iso, now_iso))
        else:
            app_id = app_row["id"]
            conn.execute("""
            UPDATE applications SET status = 'APPLIED', applied_at = ?, updated_at = ? WHERE id = ?
            """, (now_iso, now_iso, app_id))

        conn.execute("UPDATE jobs SET status = 'APPLIED', updated_at = ? WHERE id = ?", (now_iso, job_id))

        # Create automatic follow-up task 7 days out
        task_id = str(uuid.uuid4())
        due_7d = datetime.fromtimestamp(datetime.now().timestamp() + 7 * 86400).strftime("%Y-%m-%d")
        conn.execute("""
        INSERT INTO tasks (id, application_id, title, description, due_date, priority, is_completed, created_at)
        VALUES (?, ?, ?, ?, ?, 'HIGH', 0, ?)
        """, (task_id, app_id, f"Follow up on application with {company} ({title})", "Check application status or connect with hiring team on LinkedIn", due_7d, now_iso))

        log_activity(conn, "APPLICATION_SUBMITTED", f"Applied to {title} at {company} via Discord Alert", job_id, app_id)

    return {"success": True, "job_id": job_id, "application_id": app_id, "status": "APPLIED"}



import threading
from backend.pipeline import run as run_pipeline

_pipeline_running = False

@app.post("/api/pipeline/run")
def trigger_pipeline_run():
    global _pipeline_running
    if _pipeline_running:
        return {"status": "already_running", "message": "Pipeline is already running in background."}
    
    def _worker():
        global _pipeline_running
        _pipeline_running = True
        try:
            run_pipeline(dry_run=False, skip_notify=False)
        except Exception as e:
            print(f"Pipeline run error: {e}")
        finally:
            _pipeline_running = False

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return {"status": "started", "message": "Sourcing pipeline run started in background across enabled collectors."}


@app.get("/api/pipeline/status")
def get_pipeline_status():
    global _pipeline_running
    return {"running": _pipeline_running}


# ---------------------------------------------------------------------------
# Static frontend mount
# ---------------------------------------------------------------------------
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "CareerOS backend running. Frontend index.html not found."}
