import pytest
from datetime import datetime, timezone
from app.models import Flag, StudentInSession, Submission

def test_internet_detected_telemetry_freezes_exam_and_increases_risk(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_security",
        "password": "password123",
        "name": "Prof. Security"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_security",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Security Enclave Test",
        "problem_statement": "Implement secure algorithm",
        "starter_code": "def solve(): pass",
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
    join_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Rogue Student",
        "student_identifier": "SEC_007"
    }).json()
    student_id = join_res["student_session_id"]
    assert join_res["is_frozen"] is False

    # Check initial triage zone
    triage_before = client.get(f"/api/dashboard/triage?session_id={session_id}", headers=headers).json()
    st_triage = next(s for s in triage_before["students"] if s["id"] == student_id)
    assert st_triage["zone"] == "green"
    assert st_triage["is_frozen"] is False
    assert st_triage["risk_score"] == 0

    # 3. Unauthorized internet connection detected! Post telemetry event
    flag_res = client.post("/api/telemetry/event", json={
        "student_session_id": student_id,
        "type": "internet-detected",
        "metadata": {
            "source": "canary-probe",
            "reason": "Active WAN connection detected"
        },
        "ts": datetime.now(timezone.utc).isoformat()
    })
    assert flag_res.status_code == 200
    flag_data = flag_res.json()
    assert flag_data["type"] == "internet-detected"
    assert flag_data["severity"] == "critical"
    assert flag_data["risk_score"] >= 50

    # 4. Verify Student is now FROZEN in DB
    student = db.query(StudentInSession).filter(StudentInSession.id == student_id).first()
    assert student.is_frozen is True

    # 5. Verify Triage Dashboard reflects RED zone and FROZEN status
    triage_after = client.get(f"/api/dashboard/triage?session_id={session_id}", headers=headers).json()
    st_triage_after = next(s for s in triage_after["students"] if s["id"] == student_id)
    assert st_triage_after["zone"] == "red"
    assert st_triage_after["is_frozen"] is True
    assert "FROZEN" in st_triage_after["zone_reason"]
    assert st_triage_after["risk_score"] >= 50


def test_evaluator_unfreeze_and_freeze_endpoints(client, db):
    # 1. Setup session & student
    client.post("/api/auth/register", json={
        "username": "prof_unfreeze",
        "password": "password123",
        "name": "Prof. Unfreeze"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_unfreeze",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Unfreeze Protocol Test",
        "problem_statement": "Solve problem",
        "starter_code": "pass"
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    session_id = sess_res["id"]
    code = sess_res["access_code"]

    join_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Penalized Student",
        "student_identifier": "PEN_101"
    }).json()
    student_id = join_res["student_session_id"]

    # Trigger internet detection
    client.post("/api/telemetry/event", json={
        "student_session_id": student_id,
        "type": "internet-detected",
        "metadata": {"reason": "Hotspot connected"}
    })

    # Verify frozen
    student = db.query(StudentInSession).filter(StudentInSession.id == student_id).first()
    assert student.is_frozen is True

    # 2. Evaluator unfreezes student exam
    unfreeze_res = client.post(f"/api/sessions/{session_id}/students/{student_id}/unfreeze", headers=headers)
    assert unfreeze_res.status_code == 200
    unfreeze_data = unfreeze_res.json()
    assert unfreeze_data["success"] is True
    assert unfreeze_data["is_frozen"] is False

    # Check DB state
    db.refresh(student)
    assert student.is_frozen is False

    # Open internet-detected flag should now be dismissed
    internet_flag = db.query(Flag).filter(
        Flag.student_session_id == student.id,
        Flag.type == "internet-detected"
    ).first()
    assert internet_flag.status == "dismissed"

    # Dynamic risk score should drop back to 0
    assert student.risk_score == 0

    # 3. Evaluator manually freezes student
    freeze_res = client.post(f"/api/sessions/{session_id}/students/{student_id}/freeze", headers=headers)
    assert freeze_res.status_code == 200
    assert freeze_res.json()["is_frozen"] is True

    db.refresh(student)
    assert student.is_frozen is True


def test_frozen_student_rejoin_reports_is_frozen(client, db):
    # Setup
    client.post("/api/auth/register", json={
        "username": "prof_rejoin",
        "password": "password123",
        "name": "Prof. Rejoin"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_rejoin",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Rejoin Test",
        "problem_statement": "Rejoin test",
        "starter_code": "pass"
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    session_id = sess_res["id"]
    code = sess_res["access_code"]

    join_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Crash Student",
        "student_identifier": "CRASH_99"
    }).json()
    student_id = join_res["student_session_id"]

    # Student triggers internet detection
    client.post("/api/telemetry/event", json={
        "student_session_id": student_id,
        "type": "internet-detected",
        "metadata": {"reason": "Wi-Fi connected"}
    })

    # Student refreshes browser / restarts kiosk and rejoins
    rejoin_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Crash Student",
        "student_identifier": "CRASH_99"
    }).json()

    assert rejoin_res["is_reconnect"] is True
    assert rejoin_res["is_frozen"] is True
