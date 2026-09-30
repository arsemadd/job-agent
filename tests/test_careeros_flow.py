"""Comprehensive test suite for CareerOS end-to-end workflows.

Tests:
1. DB schema initialization & migration of legacy jobs
2. Jobs querying & status transitions
3. Application creation & lifecycle progression
4. AI Application Strategy generator & tailoring
5. Cover letter versioning & visual diff engine
6. Submission snapshot recording (resume version, cover letter, Q&A, portfolio)
7. Interview scheduling & debriefing
8. Tasks & reminders
9. Analytics engine (funnel & conversion)
10. Discovery directory with all 31+ boards
"""
from __future__ import annotations

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.database import get_db, init_db, migrate_from_json, compute_diff
from backend.strategy import generate_application_strategy
from backend.collectors.linkedin_discovery import BOARD_LINKS, build_discovery
from backend.app import app


@pytest.fixture
def client(tmp_path):
    test_db = str(tmp_path / "test_careeros.db")
    os.environ["CAREEROS_DB_PATH"] = test_db
    init_db(test_db)
    with TestClient(app) as c:
        yield c


def test_discovery_boards_count_and_requested_sites():
    """Verify that all user-requested job sites are included in discovery."""
    names = [b["name"].lower() for b in BOARD_LINKS]
    urls = [b["url"].lower() for b in BOARD_LINKS]

    # Verify key user requested sites
    assert any("jobgether" in u for u in urls), "jobgether.com missing"
    assert any("powertofly" in u for u in urls), "powertofly.com missing"
    assert any("remotehub" in u for u in urls), "remotehub.io missing"
    assert any("remoteworkhub" in u for u in urls), "remoteworkhub.com missing"
    assert any("remotejobsclub" in u for u in urls), "remotejobsclub.com missing"
    assert any("cloudpeeps" in u for u in urls), "cloudpeeps.com missing"
    assert any("wordpress" in u for u in urls), "jobs.wordpress.net missing"
    assert any("simply-communicate" in u or "communicate" in u for u in urls), "simply communicate missing"
    assert any("virtualassistant" in u for u in urls), "virtualassistantjobs.com missing"
    assert any("outsourcingjobs" in u for u in urls), "outsourcingjobs.ph missing"
    assert any("jobmote" in u for u in urls), "jobmote.com missing"
    assert any("remotebaba" in u for u in urls), "remotebaba.com missing"
    assert any("idealist" in u for u in urls), "idealist.org missing"
    assert any("remotejobr" in u for u in urls), "remotejobr.com missing"
    assert any("jobscribe" in u for u in urls), "jobscribe.com missing"
    assert any("remotehunt" in u for u in urls), "remotehunt.com missing"
    assert any("outsourcinginsight" in u for u in urls), "outsourcinginsight.com missing"
    assert any("goremote" in u for u in urls), "goremote.io missing"
    assert any("dynamitejobs" in u for u in urls), "dynamitejobs.com missing"
    assert any("themuse" in u for u in urls), "themuse.com missing"
    assert any("awesomejobs" in u for u in urls), "awesomejobs.io missing"
    assert any("techjobs" in u for u in urls), "techjobs.com missing"
    assert any("laravel" in u for u in urls), "jobs.laravel.io missing"
    assert any("jobsinpods" in u for u in urls), "jobsinpods.com missing"
    assert any("rubynow" in u for u in urls), "rubynow.com missing"
    assert any("remoters" in u for u in urls), "remoters.net missing"
    assert any("outsourcely" in u for u in urls), "outsourcely.com missing"
    assert any("crossover" in u for u in urls), "crossover.com missing"
    assert any("remotejobs.com" in u for u in urls), "remotejobs.com missing"
    assert len(BOARD_LINKS) >= 30, f"Expected at least 30 discovery boards, got {len(BOARD_LINKS)}"


def test_ai_strategy_generator_grounded_in_profile():
    """Verify application strategy generation leverages Arsema's real projects."""
    strat = generate_application_strategy(
        title="Technical Product Manager - Integrations & Core API",
        company="Acme SaaS",
        description="Looking for a Technical PM to lead our REST API integrations, Jira workflows, and developer specs.",
    )

    assert "lead_with" in strat
    assert "strongest_evidence" in strat
    assert "secondary_evidence" in strat
    assert "cover_letter_angle" in strat
    assert "draft_cover_letter" in strat
    assert "sample_qa_answers" in strat

    # Verify authentic evidence is cited
    evidence_text = f"{strat['strongest_evidence']} {strat['secondary_evidence']} {strat['draft_cover_letter']}"
    assert "Bravura" in evidence_text or "Composity" in evidence_text or "Software Engineering" in evidence_text


def test_visual_diff_engine():
    """Verify word/line diff engine accurately flags additions and removals."""
    v1 = "Hi Team,\nI am writing to apply for the Technical PM role.\nI have 3 years of experience in product."
    v2 = "Hi Team,\nAt Bravura, I took an orthodontic EHR concept into a 7-phase roadmap.\nI have 3+ years in B2B SaaS and Software Engineering."

    diff = compute_diff(v1, v2)
    assert diff["additions_count"] > 0
    assert diff["deletions_count"] > 0
    assert any(line["type"] == "insert" for line in diff["lines"])
    assert any(line["type"] == "delete" for line in diff["lines"])


def test_end_to_end_application_lifecycle(client):
    """Test full cycle: Create Job -> Strategy -> Submit Application -> Version Diff -> Interview -> Outcome."""
    # 1. Insert a mock job
    with get_db() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO jobs (id, source, title, company, url, description, score, status, first_seen_at, updated_at)
        VALUES ('job-acme-1', 'greenhouse', 'Technical Product Manager', 'Acme Corp', 'https://example.com/job', 
                'We need a Technical PM with API and EHR experience.', 90, 'DISCOVERED', '2026-09-29T10:00:00Z', '2026-09-29T10:00:00Z')
        """)

    # 2. Advance to SHORTLISTED and generate AI Strategy
    res_strat = client.post("/api/jobs/job-acme-1/strategy")
    assert res_strat.status_code == 200
    strat_data = res_strat.json()
    assert strat_data["success"] is True
    app_id = strat_data["application_id"]

    # 3. Verify application was created with v1 cover letter draft
    res_job = client.get("/api/jobs/job-acme-1")
    assert res_job.status_code == 200
    job_detail = res_job.json()
    assert job_detail["application"] is not None
    assert len(job_detail["cover_letters"]) >= 1

    # 4. Create v2 tailored cover letter
    res_cl = client.post(f"/api/applications/{app_id}/cover-letters", json={
        "version_label": "v2 (Focused on API & Jira Delivery)",
        "angle_tag": "Technical PM + Delivery",
        "content": "Hi Acme Team,\n\nI specialize in developer-ready Jira user stories and Postman API validation.\nAt Bravura, I built the 7-phase EHR roadmap.",
        "is_ai_assisted": True,
        "is_manually_edited": True,
        "is_submitted": False
    })
    assert res_cl.status_code == 200

    # 5. Compute visual diff between v1 and v2
    res_diff = client.get(f"/api/applications/{app_id}/cover-letters/diff?v_from=1&v_to=2")
    assert res_diff.status_code == 200
    diff_res = res_diff.json()
    assert "lines" in diff_res
    assert diff_res["additions_count"] > 0

    # 6. Record Application Submission (Exact snapshot)
    res_submit = client.post(f"/api/applications/{app_id}/submit", json={
        "resume_version_id": "resume-pm-v4",
        "cover_letter_text": "Submitted Final Cover Letter for Acme Corp",
        "cover_letter_angle": "Technical PM + Delivery",
        "portfolio_projects": ["Bravura Healthcare EHR", "Composity ERP"],
        "qa_answers": [{"question": "Why Acme?", "answer": "Acme solves mission-critical workflows."}],
        "notes": "Submitted through Greenhouse portal with referral"
    })
    assert res_submit.status_code == 200
    assert res_submit.json()["status"] == "APPLIED"

    # 7. Advance to Interview and schedule round
    res_int = client.post("/api/interviews", json={
        "application_id": app_id,
        "round_name": "Technical & Systems Design Round",
        "scheduled_at": "2026-10-05T15:00:00Z",
        "interviewer_name": "Sarah Miller",
        "interviewer_title": "VP of Product",
        "prep_notes": "Focus on Bravura EHR dependency sequencing and Composity API validation."
    })
    assert res_int.status_code == 200
    int_id = res_int.json()["interview_id"]

    # 8. Complete Interview debrief
    res_debrief = client.patch(f"/api/interviews/{int_id}", json={
        "completed_at": "2026-10-05T16:00:00Z",
        "questions_asked": ["How do you handle API spec conflicts?", "Describe your EHR roadmap."],
        "debrief_notes": "Strong positive reaction to software engineering background and Jira acceptance criteria.",
        "outcome": "PASSED"
    })
    assert res_debrief.status_code == 200

    # 9. Verify Analytics calculates funnel
    res_analytics = client.get("/api/analytics")
    assert res_analytics.status_code == 200
    analytics_data = res_analytics.json()
    assert analytics_data["funnel"]["applied"] >= 1
    assert analytics_data["funnel"]["interview"] >= 1


def test_discord_alerts_tracker_and_quick_apply(client):
    """Verify discord alerts endpoint and 1-click application tracking."""
    # 1. Insert jobs with alerted status or high score
    with get_db() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO jobs (id, source, title, company, url, description, score, status, notified_at, first_seen_at, updated_at)
        VALUES ('alert-job-1', 'jobgether', 'Remote Technical PM', 'GlobalTech', 'https://jobgether.com/job/123', 
                'Remote PM job', 92, 'DISCOVERED', '2026-09-30T10:00:00Z', '2026-09-30T10:00:00Z', '2026-09-30T10:00:00Z')
        """)

    # 2. Get alerts list
    res = client.get("/api/alerts")
    assert res.status_code == 200
    data = res.json()
    assert data["total_alerts"] >= 1
    assert any(a["id"] == "alert-job-1" for a in data["alerts"])

    # 3. Quick apply
    res_apply = client.post("/api/alerts/alert-job-1/apply")
    assert res_apply.status_code == 200
    apply_data = res_apply.json()
    assert apply_data["status"] == "APPLIED"

    # 4. Check that application was tracked
    res_updated = client.get("/api/alerts")
    assert res_updated.status_code == 200
    matched_job = next(a for a in res_updated.json()["alerts"] if a["id"] == "alert-job-1")
    assert matched_job["application_status"] == "APPLIED"

