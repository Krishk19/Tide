import pytest
from datetime import datetime, timezone, timedelta
from app.models import StudentInSession, Submission, Flag

def test_triage_zones_classification(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_triage",
        "password": "password123",
        "name": "Prof. Triage"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_triage",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Triage Problem",
        "problem_statement": "Implement graph search algorithm",
        "starter_code": "def bfs(graph, start):\n    pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    session_id = sess_res["id"]
    code = sess_res["access_code"]

    # 2. Student 1: On Track (Active organic typing)
    s1_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Aarav OnTrack",
        "student_identifier": "CS2026_G1"
    }).json()
    s1_id = s1_res["student_session_id"]
    client.post("/api/exam/autosave", json={
        "student_session_id": s1_id,
        "code": "def bfs(graph, start):\n    queue = [start]\n    visited = set([start])\n    return visited",
        "language": "python"
    })

    # 3. Student 2: Struggling / Idle (Joined 15m ago, minimal code, unsubmitted)
    t_past = datetime.now(timezone.utc) - timedelta(minutes=15)
    st2 = StudentInSession(
        session_id=session_id,
        student_name="Pooja Struggling",
        student_identifier="CS2026_Y1",
        joined_at=t_past,
        risk_score=0
    )
    db.add(st2)
    db.commit()
    db.refresh(st2)
    sub2 = Submission(
        student_session_id=st2.id,
        code="def bfs():",
        language="python",
        last_autosaved_at=t_past
    )
    db.add(sub2)
    db.commit()

    # 4. Student 3: High Suspicion (High risk score & correlated cheat flag)
    s3_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Kunal Suspicious",
        "student_identifier": "CS2026_R1"
    }).json()
    s3_id = s3_res["student_session_id"]
    st3 = db.query(StudentInSession).filter(StudentInSession.id == s3_id).first()
    st3.risk_score = 85
    db.commit()

    flag_corr = Flag(
        student_session_id=s3_id,
        type="correlated-cheat-attempt",
        severity="critical",
        flag_metadata={"reason": "Window blur 6s followed by 90 char paste"},
        ts=datetime.now(timezone.utc),
        status="open"
    )
    db.add(flag_corr)
    db.commit()

    # 5. Query Classroom Triage Endpoint
    res = client.get(f"/api/dashboard/triage?session_id={session_id}", headers=headers)
    assert res.status_code == 200
    triage_data = res.json()

    assert triage_data["session_id"] == session_id
    assert triage_data["total_students"] == 3
    counts = triage_data["counts"]
    assert counts["all"] == 3
    assert counts["green"] == 1
    assert counts["yellow"] == 1
    assert counts["red"] == 1

    students_map = {s["student_identifier"]: s for s in triage_data["students"]}
    assert students_map["CS2026_G1"]["zone"] == "green"
    assert students_map["CS2026_Y1"]["zone"] == "yellow"
    reason_str = students_map["CS2026_R1"]["zone_reason"].lower()
    assert "correlation" in reason_str or "risk" in reason_str


def test_triage_multi_teacher_isolation(client):
    # Teacher 1
    client.post("/api/auth/register", json={"username": "prof_triage_t1", "password": "password123", "name": "Teacher One"})
    t1_token = client.post("/api/auth/login", json={"username": "prof_triage_t1", "password": "password123"}).json()["access_token"]
    t1_headers = {"Authorization": f"Bearer {t1_token}"}

    # Teacher 2
    client.post("/api/auth/register", json={"username": "prof_triage_t2", "password": "password123", "name": "Teacher Two"})
    t2_token = client.post("/api/auth/login", json={"username": "prof_triage_t2", "password": "password123"}).json()["access_token"]
    t2_headers = {"Authorization": f"Bearer {t2_token}"}

    # T1 creates session
    assign_id = client.post("/api/assignments", json={
        "title": "T1 Problem",
        "problem_statement": "Description here for t1",
        "starter_code": "pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=t1_headers).json()["id"]

    s1_id = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=t1_headers).json()["id"]

    # T2 attempts to access T1's triage
    res = client.get(f"/api/dashboard/triage?session_id={s1_id}", headers=t2_headers)
    assert res.status_code == 404
