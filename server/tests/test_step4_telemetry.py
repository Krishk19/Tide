import pytest
from datetime import datetime, timedelta, timezone

def test_telemetry_event_and_non_destructive_review(client):
    # 1. Register Teacher
    client.post("/api/auth/register", json={
        "username": "prof_telemetry",
        "password": "password123",
        "name": "Prof. Telemetry"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_telemetry",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Assignment & Session
    assign_id = client.post("/api/assignments", json={
        "title": "Telemetry Test Problem",
        "problem_statement": "Do something",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    code = sess_res["access_code"]

    # 3. Student Joins
    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Dev Student",
        "student_identifier": "ROLL_999"
    }).json()
    student_session_id = st_res["student_session_id"]

    # 4. Student emits focus-lost event
    flag_res = client.post("/api/telemetry/event", json={
        "student_session_id": student_session_id,
        "type": "focus-lost",
        "metadata": {"source": "alt-tab"}
    })
    assert flag_res.status_code == 200
    flag_data = flag_res.json()
    assert flag_data["type"] == "focus-lost"
    assert flag_data["status"] == "open"
    flag_id = flag_data["id"]

    # Student emits paste event
    paste_res = client.post("/api/telemetry/event", json={
        "student_session_id": student_session_id,
        "type": "paste",
        "metadata": {"length": 84}
    })
    assert paste_res.status_code == 200

    # 5. Teacher queries dashboard flags
    dash_flags = client.get("/api/dashboard/flags", headers=headers).json()
    assert len(dash_flags) >= 2
    types = [f["type"] for f in dash_flags]
    assert "focus-lost" in types
    assert "paste" in types

    # 6. Non-Destructive Flag Review: Teacher marks flag dismissed
    review_res = client.patch(f"/api/dashboard/flags/{flag_id}", json={
        "status": "dismissed"
    }, headers=headers)
    assert review_res.status_code == 200
    reviewed_flag = review_res.json()
    assert reviewed_flag["status"] == "dismissed"
    assert reviewed_flag["reviewed_by"] is not None
    assert reviewed_flag["reviewed_at"] is not None

    # CRITICAL CHECK: Flag is NOT deleted, it is preserved in the audit log
    updated_flags = client.get("/api/dashboard/flags", headers=headers).json()
    dismissed_items = [f for f in updated_flags if f["id"] == flag_id]
    assert len(dismissed_items) == 1
    assert dismissed_items[0]["status"] == "dismissed"

def test_telemetry_suppressed_after_submission(client):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_postsub",
        "password": "password123",
        "name": "Prof. PostSub"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_postsub",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Post Submission Test",
        "problem_statement": "Write a script that prints 42 to standard output",
        "starter_code": "print(42)",
        "visible_test_cases": [{"id": "v1", "input": "", "expected_output": "42"}],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    code = sess_res["access_code"]

    # 2. Student Joins and Submits
    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Completed Student",
        "student_identifier": "ROLL_DONE"
    }).json()
    student_session_id = st_res["student_session_id"]

    sub_res = client.post("/api/exam/submit", json={
        "student_session_id": student_session_id,
        "code": "print(42)",
        "language": "python"
    })
    assert sub_res.status_code == 200
    assert sub_res.json()["is_submitted"] is True

    # 3. Post-submission events should be suppressed!
    event1 = client.post("/api/telemetry/event", json={
        "student_session_id": student_session_id,
        "type": "focus-lost",
        "metadata": {"source": "window_close"}
    })
    assert event1.status_code == 200
    assert event1.json()["id"] == 0
    assert event1.json()["status"] == "dismissed"

    event2 = client.post("/api/telemetry/event", json={
        "student_session_id": student_session_id,
        "type": "connection-lost",
        "metadata": {"source": "tab_closed"}
    })
    assert event2.status_code == 200
    assert event2.json()["id"] == 0

    # 4. Verify no flags are recorded in DB for this session
    dash_flags = client.get(f"/api/dashboard/flags?session_id={sess_res['id']}", headers=headers).json()
    assert len(dash_flags) == 0
