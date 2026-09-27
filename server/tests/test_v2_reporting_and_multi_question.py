import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app


def test_multi_question_exam_lifecycle():
    client = TestClient(app)

    # 1. Register and login teacher
    client.post("/api/auth/register", json={
        "username": "multiq_prof",
        "email": "multiq@test.edu",
        "password": "password123",
        "name": "Prof Multi Question"
    })
    token = client.post("/api/auth/login", json={"username": "multiq_prof", "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Multi-Question Assignment (2 Questions)
    q1 = {
        "id": "q1",
        "title": "Reverse Array",
        "problem_statement": "Reverse the input string",
        "starter_code": "import sys\ndef solve(s):\n    pass\n",
        "visible_test_cases": [
            {"id": "v1_1", "input": "hello\n", "expected_output": "olleh\n"}
        ],
        "hidden_test_cases": [
            {"id": "h1_1", "input": "world\n", "expected_output": "dlrow\n"}
        ]
    }
    q2 = {
        "id": "q2",
        "title": "Square Number",
        "problem_statement": "Compute the square of an integer",
        "starter_code": "import sys\ndef solve(n):\n    pass\n",
        "visible_test_cases": [
            {"id": "v2_1", "input": "4\n", "expected_output": "16\n"},
            {"id": "v2_2", "input": "5\n", "expected_output": "25\n"}
        ],
        "hidden_test_cases": [
            {"id": "h2_1", "input": "10\n", "expected_output": "100\n"}
        ]
    }

    assign_res = client.post("/api/assignments", headers=headers, json={
        "title": "Lab Exam: Multi-Question Test",
        "problem_statement": "Solve both problems",
        "language_set": "python",
        "questions": [q1, q2]
    })
    assert assign_res.status_code == 201
    assign_id = assign_res.json()["id"]

    # 3. Launch Session
    start_iso = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    sess_res = client.post("/api/sessions", headers=headers, json={
        "assignment_id": assign_id,
        "start_time": start_iso
    })
    session_id = sess_res.json()["id"]
    access_code = sess_res.json()["access_code"]

    # 4. Student joins
    join_res = client.post("/api/sessions/join", json={
        "access_code": access_code,
        "student_name": "Charlie Multi",
        "student_identifier": "CS-MQ-01"
    })
    assert join_res.status_code == 200
    student_id = join_res.json()["student_session_id"]

    # 5. Check Exam State: verify student receives both questions with hidden tests withheld
    state_res = client.get(f"/api/exam/state/{student_id}")
    assert state_res.status_code == 200
    state_data = state_res.json()
    assert state_data["status"] == "active"
    assert len(state_data["assignment"]["questions"]) == 2
    # Ensure hidden test cases are NOT in client response
    for q in state_data["assignment"]["questions"]:
        assert "hidden_test_cases" not in q

    # 6. Test Running visible test for Q1
    q1_code = "import sys\ns = sys.stdin.read().strip()\nprint(s[::-1])"
    run_q1 = client.post("/api/exam/run", json={
        "student_session_id": student_id,
        "code": q1_code,
        "language": "python",
        "question_id": "q1"
    })
    assert run_q1.status_code == 200
    assert run_q1.json()["passed_all"] is True

    # 7. Autosave code for Q1, then Q2
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": q1_code,
        "language": "python",
        "question_id": "q1"
    })

    q2_code = "import sys\nn = int(sys.stdin.read().strip())\nprint(n * n)"
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": q2_code,
        "language": "python",
        "question_id": "q2"
    })

    # Verify both codes are preserved when state is queried again
    re_state = client.get(f"/api/exam/state/{student_id}").json()
    assert re_state["saved_codes"]["q1"] == q1_code
    assert re_state["saved_codes"]["q2"] == q2_code

    # 8. Submit Exam
    sub_res = client.post("/api/exam/submit", json={
        "student_session_id": student_id,
        "code": "",
        "language": "python",
        "codes": {"q1": q1_code, "q2": q2_code}
    })
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["is_submitted"] is True
    # Q1: 1 visible + 1 hidden = 2
    # Q2: 2 visible + 1 hidden = 3
    # Total tests = 5
    assert sub_data["total_tests"] == 5
    assert sub_data["passed_tests"] == 5
    assert sub_data["score_percentage"] == 100.0
    assert "question_breakdown" in sub_data
    assert sub_data["question_breakdown"]["q1"]["passed_tests"] == 2
    assert sub_data["question_breakdown"]["q2"]["passed_tests"] == 3


def test_forensic_timeline_and_marksheet_export():
    client = TestClient(app)

    # 1. Register and login teacher
    client.post("/api/auth/register", json={
        "username": "report_prof",
        "email": "report@test.edu",
        "password": "password123",
        "name": "Prof Reporting"
    })
    token = client.post("/api/auth/login", json={"username": "report_prof", "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Register second teacher for isolation test
    client.post("/api/auth/register", json={
        "username": "report_prof2",
        "email": "report2@test.edu",
        "password": "password123",
        "name": "Prof Isolated"
    })
    token2 = client.post("/api/auth/login", json={"username": "report_prof2", "password": "password123"}).json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # 3. Create Assignment & Session
    assign_res = client.post("/api/assignments", headers=headers, json={
        "title": "Algorithms Exam",
        "problem_statement": "Write an algorithm",
        "language_set": "python",
        "visible_test_cases": [{"id": "v1", "input": "3\n", "expected_output": "9\n"}],
        "hidden_test_cases": [{"id": "h1", "input": "4\n", "expected_output": "16\n"}]
    })
    assign_id = assign_res.json()["id"]

    start_iso = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    sess_res = client.post("/api/sessions", headers=headers, json={
        "assignment_id": assign_id,
        "start_time": start_iso
    })
    session_id = sess_res.json()["id"]
    access_code = sess_res.json()["access_code"]

    # 4. Join Student and generate events
    join_res = client.post("/api/sessions/join", json={
        "access_code": access_code,
        "student_name": "Diana Report",
        "student_identifier": "CS-REP-01"
    })
    student_id = join_res.json()["student_session_id"]

    # Autosave code
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": "import sys\nprint(int(sys.stdin.read().strip())**2)",
        "language": "python"
    })

    # Submit
    client.post("/api/exam/submit", json={
        "student_session_id": student_id,
        "code": "import sys\nprint(int(sys.stdin.read().strip())**2)",
        "language": "python"
    })

    # 5. Fetch Forensic Timeline
    tl_res = client.get(f"/api/sessions/{session_id}/students/{student_id}/timeline", headers=headers)
    assert tl_res.status_code == 200
    tl_data = tl_res.json()
    assert tl_data["student"]["name"] == "Diana Report"
    assert tl_data["total_events"] >= 2
    types = [e["type"] for e in tl_data["timeline"]]
    assert "joined" in types
    assert "submission" in types

    # 6. Fetch Marksheet CSV Export
    csv_res = client.get(f"/api/sessions/{session_id}/export?format=csv", headers=headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "CS-REP-01" in csv_res.text
    assert "Diana Report" in csv_res.text
    assert "100.00" in csv_res.text

    # 7. Fetch Full Forensic JSON Archive
    json_res = client.get(f"/api/sessions/{session_id}/export?format=json", headers=headers)
    assert json_res.status_code == 200
    archive_data = json_res.json()
    assert archive_data["session"]["access_code"] == access_code
    assert archive_data["student_count"] == 1
    assert archive_data["students"][0]["student_identifier"] == "CS-REP-01"
    assert archive_data["students"][0]["submission"]["test_results"]["score_percentage"] == 100.0

    # 8. Teacher Isolation Check: Teacher 2 cannot access Teacher 1's timeline or exports
    iso_tl = client.get(f"/api/sessions/{session_id}/students/{student_id}/timeline", headers=headers2)
    assert iso_tl.status_code == 404

    iso_csv = client.get(f"/api/sessions/{session_id}/export?format=csv", headers=headers2)
    assert iso_csv.status_code == 404
