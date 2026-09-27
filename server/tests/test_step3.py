import pytest
from datetime import datetime, timedelta, timezone
from tests.conftest import TestingSessionLocal
from app.models.entities import Session as ExamSession

def test_full_exam_gateway_and_confidentiality_flow(client):
    # 1. Register Teacher & Login
    client.post("/api/auth/register", json={
        "username": "prof_exam",
        "password": "exam_password",
        "name": "Prof. Exam Proctor"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_exam",
        "password": "exam_password"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Assignment with Visible and Hidden Tests
    assign_payload = {
        "title": "Square of Number",
        "problem_statement": "Read an integer from stdin and print its square.",
        "starter_code": "import sys\n# Write solution here",
        "visible_test_cases": [
            {"id": "v1", "input": "4", "expected_output": "16"}
        ],
        "hidden_test_cases": [
            {"id": "h1", "input": "10", "expected_output": "100"},
            {"id": "h2", "input": "-5", "expected_output": "25"}
        ],
        "language_set": "python"
    }
    assign_id = client.post("/api/assignments", json=assign_payload, headers=headers).json()["id"]

    # 3. Create Session starting in the FUTURE (+15 minutes)
    future_time = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    session_data = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": future_time
    }, headers=headers).json()
    access_code = session_data["access_code"]
    session_id = session_data["id"]

    # 4. Student joins with code
    join_res = client.post("/api/sessions/join", json={
        "access_code": access_code,
        "student_name": "Aarav Sharma",
        "student_identifier": "CS2026_001"
    })
    assert join_res.status_code == 200
    student_session_id = join_res.json()["student_session_id"]

    # Reconnect test: joining again with same roll number gives same student_session_id
    reconnect_res = client.post("/api/sessions/join", json={
        "access_code": access_code,
        "student_name": "Aarav Sharma",
        "student_identifier": "CS2026_001"
    })
    assert reconnect_res.json()["student_session_id"] == student_session_id

    # 5. Check State: Server-Clock Lock Gate (Exam is in future)
    state_locked = client.get(f"/api/exam/state/{student_session_id}").json()
    assert state_locked["status"] == "locked"
    assert state_locked["remaining_seconds"] > 0
    # CRITICAL CHECK: Zero problem or test data sent during locked state
    assert state_locked["assignment"] is None

    # 6. Fast-forward: Update session start time to PAST (-1 minute)
    with TestingSessionLocal() as db:
        s = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        s.start_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    # 7. Check State: Now UNLOCKED
    state_active = client.get(f"/api/exam/state/{student_session_id}").json()
    assert state_active["status"] == "active"
    assert state_active["remaining_seconds"] == 0
    assert state_active["assignment"] is not None
    assert state_active["assignment"]["title"] == "Square of Number"
    assert len(state_active["assignment"]["visible_test_cases"]) == 1
    # CRITICAL CHECK: Hidden test cases are NEVER present in student response!
    assert "hidden_test_cases" not in state_active["assignment"]

    # 8. Autosave Code
    student_code = "import sys\nn = int(sys.stdin.read().strip())\nprint(n * n)"
    auto_res = client.post("/api/exam/autosave", json={
        "student_session_id": student_session_id,
        "code": student_code,
        "language": "python"
    })
    assert auto_res.status_code == 200
    assert auto_res.json()["status"] == "saved"

    # State check now reflects saved code
    state_after_save = client.get(f"/api/exam/state/{student_session_id}").json()
    assert state_after_save["saved_code"] == student_code

    # 9. Run Visible Tests
    run_res = client.post("/api/exam/run", json={
        "student_session_id": student_session_id,
        "code": student_code,
        "language": "python"
    })
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["passed_all"]
    assert len(run_data["results"]) == 1
    assert run_data["results"][0]["actual_output"].strip() == "16"

    # 10. Final Submit (Runs both visible and hidden tests)
    sub_res = client.post("/api/exam/submit", json={
        "student_session_id": student_session_id,
        "code": student_code,
        "language": "python"
    })
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["is_submitted"]
    assert sub_data["total_tests"] == 3  # 1 visible + 2 hidden
    assert sub_data["passed_tests"] == 3
    assert sub_data["score_percentage"] == 100.0
    assert sub_data["hidden_summary"]["total"] == 2
    assert sub_data["hidden_summary"]["passed"] == 2
    # CRITICAL SECURITY CHECK: Hidden inputs and expected outputs are NEVER returned!
    assert "input" not in sub_data["hidden_summary"]
    assert "expected_output" not in sub_data["hidden_summary"]

    # 11. State check after submission
    state_after_sub = client.get(f"/api/exam/state/{student_session_id}").json()
    assert state_after_sub["status"] == "submitted"
    assert state_after_sub["is_submitted"]
