"""CareerOS SQLite database layer.

Manages relational schema, migrations from data/jobs.json, and all transactional
operations for Jobs, Applications, Cover Letter Versions, Interviews, Tasks, and Activity.
"""
from __future__ import annotations

import difflib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get("CAREEROS_DB_PATH", os.path.join("data", "careeros.db"))


def get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize database tables and indexes."""
    with get_db(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            external_id TEXT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT,
            description TEXT,
            location_raw TEXT,
            remote_tier TEXT,
            salary_raw TEXT,
            job_type_raw TEXT,
            posted_at TEXT,
            fetched_at TEXT,
            score INTEGER DEFAULT 0,
            decision TEXT,
            fit_reason TEXT,
            gaps TEXT,
            role_category TEXT,
            seniority TEXT,
            status TEXT DEFAULT 'DISCOVERED',
            tags_json TEXT DEFAULT '[]',
            first_seen_at TEXT,
            notified_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'SHORTLISTED',
            applied_at TEXT,
            resume_version_id TEXT,
            cover_letter_version_id TEXT,
            qa_answers_json TEXT DEFAULT '[]',
            portfolio_projects_json TEXT DEFAULT '[]',
            submitted_links_json TEXT DEFAULT '{}',
            strategy_json TEXT DEFAULT '{}',
            notes TEXT DEFAULT '',
            follow_up_date TEXT,
            salary_offered TEXT,
            outcome_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cover_letters (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            version_number INTEGER NOT NULL,
            version_label TEXT NOT NULL,
            angle_tag TEXT DEFAULT 'General',
            content TEXT NOT NULL,
            is_ai_assisted INTEGER DEFAULT 1,
            is_manually_edited INTEGER DEFAULT 0,
            is_submitted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS resume_versions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            file_path TEXT,
            focus_area TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS interviews (
            id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            round_name TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            completed_at TEXT,
            interviewer_name TEXT,
            interviewer_title TEXT,
            interviewer_linkedin TEXT,
            prep_notes TEXT DEFAULT '',
            questions_asked_json TEXT DEFAULT '[]',
            debrief_notes TEXT DEFAULT '',
            outcome TEXT DEFAULT 'PENDING',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            application_id TEXT REFERENCES applications(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            due_date TEXT,
            priority TEXT DEFAULT 'MEDIUM',
            is_completed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            website TEXT,
            ats_platform TEXT,
            industry TEXT,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id TEXT PRIMARY KEY,
            job_id TEXT,
            application_id TEXT,
            action_type TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
        CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_interviews_scheduled ON interviews(scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
        """)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN notified_at TEXT;")
        except Exception:
            pass
    _seed_default_resumes(db_path)


def _seed_default_resumes(db_path: str = DB_PATH) -> None:
    """Ensure default resume versions based on Arsema's profile exist."""
    defaults = [
        {
            "id": "resume-pm-v4",
            "name": "PM Resume v4 (Technical PM & Delivery Focus)",
            "file_path": "Arsema_Doji_Wordofa_Resume.pdf",
            "focus_area": "Technical PM, API Validation, ERP/CRM & Healthcare Delivery",
            "notes": "Current primary resume highlighting Software Engineering degree and Bravura EHR + Composity ERP ownership.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": "resume-ai-pm-v1",
            "name": "AI Product Manager Resume (AI Features & Evaluation)",
            "file_path": "Arsema_Doji_Wordofa_AI_PM.pdf",
            "focus_area": "AI-Powered Features, Lead Scoring, OCR, AI Search, Automation",
            "notes": "Tailored for AI Product Manager roles emphasizing 5 end-to-end AI features shipped at Composity and PM/QA Copilot prototype.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": "resume-qa-scrum-v2",
            "name": "Scrum Master & QA Lead Resume",
            "file_path": "Arsema_Doji_Wordofa_QA_Scrum.pdf",
            "focus_area": "Agile Delivery, QA Test Planning, Blocker Resolution, Bug Reduction",
            "notes": "Focuses on Ethiojobs team of 8 delivery process, 40% defect reduction, and Jira automation.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    with get_db(db_path) as conn:
        for r in defaults:
            conn.execute("""
            INSERT OR IGNORE INTO resume_versions (id, name, file_path, focus_area, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (r["id"], r["name"], r["file_path"], r["focus_area"], r["notes"], r["created_at"]))


def migrate_from_json(json_path: str = os.path.join("data", "jobs.json"), db_path: str = DB_PATH) -> int:
    """Migrate legacy data/jobs.json entries into SQLite jobs table."""
    if not os.path.exists(json_path):
        return 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0

    jobs = data.get("jobs", [])
    if not jobs:
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = 0

    with get_db(db_path) as conn:
        for j in jobs:
            job_id = j.get("identity_key") or j.get("dedup_key") or str(uuid.uuid4())
            title = j.get("title", "").strip()
            company = j.get("company", "").strip()
            if not title or not company:
                continue

            score = j.get("score")
            try:
                score = int(score) if score is not None else 0
            except (ValueError, TypeError):
                score = 0

            status = j.get("pipeline_status") or ("SHORTLISTED" if score >= 85 else "DISCOVERED")

            fit_reason = j.get("fit_reason", "")
            if isinstance(fit_reason, (list, dict)):
                fit_reason = json.dumps(fit_reason)

            gaps = j.get("gaps", "")
            if isinstance(gaps, (list, dict)):
                gaps = json.dumps(gaps)

            notified_at = j.get("notified_at")
            if not notified_at and (j.get("status") in ("sent", "digest_sent") or score >= 85 or (j.get("decision") or "").upper() == "SEND"):
                notified_at = j.get("first_seen_at", now_iso)

            conn.execute("""
            INSERT INTO jobs (
                id, external_id, source, title, company, url, description,
                location_raw, remote_tier, salary_raw, job_type_raw, posted_at,
                fetched_at, score, decision, fit_reason, gaps, role_category,
                seniority, status, tags_json, first_seen_at, notified_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                score = excluded.score,
                decision = excluded.decision,
                fit_reason = excluded.fit_reason,
                gaps = excluded.gaps,
                notified_at = COALESCE(jobs.notified_at, excluded.notified_at),
                updated_at = excluded.updated_at
            """, (
                job_id,
                str(j.get("external_id") or j.get("id", "")),
                j.get("source", "unknown"),
                title,
                company,
                j.get("url", ""),
                j.get("description", ""),
                j.get("location_raw", ""),
                j.get("remote_tier", "A_WORLDWIDE"),
                j.get("salary_raw"),
                j.get("job_type_raw"),
                j.get("posted_at"),
                j.get("fetched_at", now_iso),
                score,
                j.get("decision", "DIGEST" if score >= 65 else "REJECT"),
                fit_reason,
                gaps,
                j.get("role_category", "Product Manager"),
                j.get("seniority", "Mid-Level"),
                status,
                json.dumps(j.get("tags", [])),
                j.get("first_seen_at", now_iso),
                notified_at,
                now_iso,
            ))
            inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Cover Letter Versioning & Diffing Engine
# ---------------------------------------------------------------------------

def compute_diff(text_a: str, text_b: str) -> Dict[str, Any]:
    """Compute rich word-level and line-level diff between two versions."""
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    line_diffs = []
    additions_count = 0
    deletions_count = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in lines_a[i1:i2]:
                line_diffs.append({"type": "equal", "text": line})
        elif tag == "delete":
            for line in lines_a[i1:i2]:
                line_diffs.append({"type": "delete", "text": line})
                deletions_count += 1
        elif tag == "insert":
            for line in lines_b[j1:j2]:
                line_diffs.append({"type": "insert", "text": line})
                additions_count += 1
        elif tag == "replace":
            for line in lines_a[i1:i2]:
                line_diffs.append({"type": "delete", "text": line})
                deletions_count += 1
            for line in lines_b[j1:j2]:
                line_diffs.append({"type": "insert", "text": line})
                additions_count += 1

    return {
        "lines": line_diffs,
        "additions_count": additions_count,
        "deletions_count": deletions_count,
        "unified": list(difflib.unified_diff(
            lines_a, lines_b, fromfile="Previous Version", tofile="Current Version"
        )),
    }
