import pytest
from datetime import datetime, timezone
from app.models import Flag, StudentInSession, Submission

def test_broadcast_announcement(client):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_broadcast",
        "password": "password123",
        "name": "Prof. Broadcast"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_broadcast",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Broadcast Test",
        "problem_statement": "Implement basic math functions",
        "starter_code": "pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    session_id = sess_res["id"]
    code = sess_res["access_code"]

    # 2. Two students join
    client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Student Alpha",
        "student_identifier": "CS2026_A"
    })
    client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Student Beta",
        "student_identifier": "CS2026_B"
    })

    # 3. Teacher broadcasts notice
    res = client.post(f"/api/sessions/{session_id}/broadcast", json={
        "message": "Notice: In Problem 1, you may use standard library modules.",
        "type": "warning"
    }, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["recipient_count"] == 2
    assert data["type"] == "warning"
    assert "standard library" in data["message"]


def test_extend_student_time(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_time",
        "password": "password123",
        "name": "Prof. Time Extension"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_time",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Time Extension Test",
        "problem_statement": "Implement dynamic programming",
        "starter_code": "pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    session_id = sess_res["id"]
    code = sess_res["access_code"]

    # 2. Student joins
    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Vikram Seth",
        "student_identifier": "CS2026_201"
    }).json()
    student_id = st_res["student_session_id"]

    # 3. Grant +10 minutes
    ext_res = client.post(f"/api/sessions/{session_id}/students/{student_id}/extend-time", json={
        "added_minutes": 10,
        "reason": "Terminal power surge recovery"
    }, headers=headers)
    assert ext_res.status_code == 200
    ext_data = ext_res.json()
    assert ext_data["success"] is True
    assert ext_data["added_minutes"] == 10
    assert ext_data["total_extra_seconds"] == 600

    # Verify DB flag logged
    flag = db.query(Flag).filter(
        Flag.student_session_id == student_id,
        Flag.type == "extended-time"
    ).first()
    assert flag is not None
    assert flag.severity == "info"
    assert flag.flag_metadata["added_minutes"] == 10

    # 4. Grant another +5 minutes
    ext_res2 = client.post(f"/api/sessions/{session_id}/students/{student_id}/extend-time", json={
        "added_minutes": 5
    }, headers=headers)
    assert ext_res2.status_code == 200
    assert ext_res2.json()["total_extra_seconds"] == 900

    # 5. Verify exam state reflects extra time
    state_res = client.get(f"/api/exam/state/{student_id}")
    assert state_res.status_code == 200
    assert state_res.json()["extra_time_seconds"] == 900


def test_warn_student(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_warn",
        "password": "password123",
        "name": "Prof. Warning"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_warn",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Warning Test",
        "problem_statement": "Implement basic search algorithm",
        "starter_code": "pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    session_id = sess_res["id"]
    code = sess_res["access_code"]

    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Kavita Reddy",
        "student_identifier": "CS2026_202"
    }).json()
    student_id = st_res["student_session_id"]

    # 2. Issue warning
    warn_res = client.post(f"/api/sessions/{session_id}/students/{student_id}/warn", json={
        "message": "Warning: Frequent head movement detected. Please face the monitor."
    }, headers=headers)
    assert warn_res.status_code == 200
    assert warn_res.json()["success"] is True

    # Verify DB flag
    flag = db.query(Flag).filter(
        Flag.student_session_id == student_id,
        Flag.type == "instructor-warning"
    ).first()
    assert flag is not None
    assert flag.severity == "medium"
    assert "Frequent head movement" in flag.flag_metadata["warning_message"]


def test_force_submit_student(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_force",
        "password": "password123",
        "name": "Prof. Force Submit"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_force",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Force Submit Problem",
        "problem_statement": "Write function returning square of number",
        "starter_code": "def square(x):\n    return x * x",
        "visible_test_cases": [{"input": "4", "expected_output": "16"}],
        "hidden_test_cases": [{"input": "5", "expected_output": "25"}]
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    session_id = sess_res["id"]
    code = sess_res["access_code"]

    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Tanya Sharma",
        "student_identifier": "CS2026_203"
    }).json()
    student_id = st_res["student_session_id"]

    # Student autosaves correct solution
    square_code = (
        "import sys\n"
        "raw = sys.stdin.read().strip()\n"
        "if raw:\n"
        "    x = int(raw)\n"
        "    print(x * x)"
    )
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": square_code,
        "language": "python"
    })

    # 2. Teacher executes force-submit
    force_res = client.post(f"/api/sessions/{session_id}/students/{student_id}/force-submit", headers=headers)
    assert force_res.status_code == 200
    force_data = force_res.json()
    assert force_data["success"] is True
    assert force_data["is_submitted"] is True
    assert force_data["score_percentage"] == 100.0
    assert force_data["passed_tests"] == 2

    # Verify Submission in DB is submitted
    sub = db.query(Submission).filter(Submission.student_session_id == student_id).first()
    assert sub.submitted_at is not None
    assert sub.test_results["force_submitted"] is True

    # Verify Flag in DB
    flag = db.query(Flag).filter(
        Flag.student_session_id == student_id,
        Flag.type == "force-submitted"
    ).first()
    assert flag is not None
    assert flag.severity == "high"


def test_classroom_multi_teacher_isolation(client):
    # Teacher 1
    client.post("/api/auth/register", json={"username": "t1_cls", "password": "password123", "name": "Teacher One"})
    t1_token = client.post("/api/auth/login", json={"username": "t1_cls", "password": "password123"}).json()["access_token"]
    t1_headers = {"Authorization": f"Bearer {t1_token}"}

    # Teacher 2
    client.post("/api/auth/register", json={"username": "t2_cls", "password": "password123", "name": "Teacher Two"})
    t2_token = client.post("/api/auth/login", json={"username": "t2_cls", "password": "password123"}).json()["access_token"]
    t2_headers = {"Authorization": f"Bearer {t2_token}"}

    # Teacher 1 creates session and student joins
    a1_id = client.post("/api/assignments", json={
        "title": "T1 Problem Title",
        "problem_statement": "Description for T1 problem statement",
        "starter_code": "pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=t1_headers).json()["id"]

    s1_res = client.post("/api/sessions", json={
        "assignment_id": a1_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=t1_headers).json()
    s1_id = s1_res["id"]
    s1_code = s1_res["access_code"]

    st1_id = client.post("/api/sessions/join", json={
        "access_code": s1_code,
        "student_name": "Student T1",
        "student_identifier": "CS_T1"
    }).json()["student_session_id"]

    # Teacher 2 attempts unauthorized actions on Session 1 / Student 1
    # 1. Broadcast
    b_res = client.post(f"/api/sessions/{s1_id}/broadcast", json={"message": "Hack", "type": "urgent"}, headers=t2_headers)
    assert b_res.status_code == 404

    # 2. Extend time
    e_res = client.post(f"/api/sessions/{s1_id}/students/{st1_id}/extend-time", json={"added_minutes": 5}, headers=t2_headers)
    assert e_res.status_code == 404

    # 3. Warn
    w_res = client.post(f"/api/sessions/{s1_id}/students/{st1_id}/warn", json={"message": "Unauthorized warn"}, headers=t2_headers)
    assert w_res.status_code == 404

    # 4. Force submit
    f_res = client.post(f"/api/sessions/{s1_id}/students/{st1_id}/force-submit", headers=t2_headers)
    assert f_res.status_code == 404
