import pytest
from datetime import datetime, timedelta, timezone
from tests.conftest import TestingSessionLocal
from app.models.entities import Session as ExamSession

def test_system_info(client):
    res = client.get("/api/system/info")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "primary_lan_ip" in data
    assert "/student" in data["student_portal_url"]
    assert "/dashboard" in data["teacher_dashboard_url"]

def test_complete_v1_exam_lifecycle(client):
    # Step A: Register Teacher A & Login
    client.post("/api/auth/register", json={
        "username": "prof_master",
        "password": "master_password",
        "name": "Prof. Master Evaluator"
    })
    token_a = client.post("/api/auth/login", json={
        "username": "prof_master",
        "password": "master_password"
    }).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Step B: Author Assignment
    assign_res = client.post("/api/assignments", json={
        "title": "Palindrome String Checker",
        "problem_statement": "Read a string from stdin. Print 'YES' if it is a palindrome, else 'NO'.",
        "starter_code": "import sys\ns = sys.stdin.read().strip()\n",
        "language_set": "python",
        "visible_test_cases": [
            {"id": "v1", "input": "racecar", "expected_output": "YES"},
            {"id": "v2", "input": "hello", "expected_output": "NO"}
        ],
        "hidden_test_cases": [
            {"id": "h1", "input": "a", "expected_output": "YES"},
            {"id": "h2", "input": "madam", "expected_output": "YES"},
            {"id": "h3", "input": "openai", "expected_output": "NO"}
        ]
    }, headers=headers_a)
    assert assign_res.status_code == 201
    assign_id = assign_res.json()["id"]

    # Step C: Schedule Session starting in the future
    future_time = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": future_time
    }, headers=headers_a)
    assert sess_res.status_code == 201
    access_code = sess_res.json()["access_code"]
    sess_id = sess_res.json()["id"]
    assert len(access_code) == 6

    # Step D: Student Joins
    join_res = client.post("/api/sessions/join", json={
        "access_code": access_code,
        "student_name": "Test Candidate",
        "student_identifier": "CANDIDATE_101"
    })
    assert join_res.status_code == 200
    st_sess_id = join_res.json()["student_session_id"]

    # Step E: Verify Start-Time Gate (Locked)
    state_locked = client.get(f"/api/exam/state/{st_sess_id}").json()
    assert state_locked["status"] == "locked"
    assert state_locked["assignment"] is None

    # Fast-forward start time to past
    with TestingSessionLocal() as db:
        s = db.query(ExamSession).filter(ExamSession.id == sess_id).first()
        s.start_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()

    # Verify Unlocked State
    state_active = client.get(f"/api/exam/state/{st_sess_id}").json()
    assert state_active["status"] == "active"
    assert state_active["assignment"]["title"] == "Palindrome String Checker"
    assert len(state_active["assignment"]["visible_test_cases"]) == 2
    assert "hidden_test_cases" not in state_active["assignment"]

    # Step F: Debounced Autosave
    solution_code = """
import sys
s = sys.stdin.read().strip()
if s == s[::-1]:
    print("YES")
else:
    print("NO")
"""
    auto_res = client.post("/api/exam/autosave", json={
        "student_session_id": st_sess_id,
        "code": solution_code,
        "language": "python"
    })
    assert auto_res.status_code == 200

    # Step G: Run Visible Tests
    run_res = client.post("/api/exam/run", json={
        "student_session_id": st_sess_id,
        "code": solution_code,
        "language": "python"
    })
    assert run_res.status_code == 200
    assert run_res.json()["passed_all"]

    # Step H: Telemetry Emission (Focus-Lost & Paste)
    f_res = client.post("/api/telemetry/event", json={
        "student_session_id": st_sess_id,
        "type": "focus-lost",
        "metadata": {"source": "alt-tab"}
    })
    assert f_res.status_code == 200
    flag_id = f_res.json()["id"]

    p_res = client.post("/api/telemetry/event", json={
        "student_session_id": st_sess_id,
        "type": "paste",
        "metadata": {"length": 72}
    })
    assert p_res.status_code == 200

    # Verify Teacher receives flags
    flags = client.get("/api/dashboard/flags", headers=headers_a).json()
    assert len(flags) >= 2

    # Step I: Submit Code & Grade Server-Side
    sub_res = client.post("/api/exam/submit", json={
        "student_session_id": st_sess_id,
        "code": solution_code,
        "language": "python"
    })
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["is_submitted"]
    assert sub_data["total_tests"] == 5  # 2 visible + 3 hidden
    assert sub_data["passed_tests"] == 5
    assert sub_data["score_percentage"] == 100.0

    # Step J: Non-destructive flag review
    rev_res = client.patch(f"/api/dashboard/flags/{flag_id}", json={
        "status": "dismissed"
    }, headers=headers_a)
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "dismissed"

    # Step K: Structural Multi-Teacher Data Isolation Check
    client.post("/api/auth/register", json={
        "username": "prof_isolated",
        "password": "iso_password",
        "name": "Prof. Isolated"
    })
    token_b = client.post("/api/auth/login", json={
        "username": "prof_isolated",
        "password": "iso_password"
    }).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Teacher B must see ZERO of Teacher A's assignments, sessions, and flags
    assert len(client.get("/api/assignments", headers=headers_b).json()) == 0
    assert len(client.get("/api/sessions", headers=headers_b).json()) == 0
    assert len(client.get("/api/dashboard/flags", headers=headers_b).json()) == 0
    assert client.get(f"/api/sessions/{sess_id}", headers=headers_b).status_code == 404
