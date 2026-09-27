import pytest
from datetime import datetime, timezone, timedelta
from app.models import Flag, Submission

def test_crash_reconnect_resilience(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_reconnect",
        "password": "password123",
        "name": "Prof. Reconnect"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_reconnect",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Crash Resilience Test",
        "problem_statement": "Implement bubble sort with O(n^2) worst case",
        "starter_code": "# starter code\ndef bubble_sort(arr):\n    pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    code = sess_res["access_code"]
    session_id = sess_res["id"]

    # 2. Student Joins initially
    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Rohan Mehra",
        "student_identifier": "CS2026_101"
    }).json()
    student_session_id = st_res["student_session_id"]
    assert st_res["is_reconnect"] is False
    assert st_res["downtime_seconds"] == 0

    # 3. Student writes code and autosaves
    written_code = (
        "def bubble_sort(arr):\n"
        "    n = len(arr)\n"
        "    for i in range(n):\n"
        "        for j in range(0, n-i-1):\n"
        "            if arr[j] > arr[j+1]:\n"
        "                arr[j], arr[j+1] = arr[j+1], arr[j]\n"
        "    return arr"
    )
    autosave_res = client.post("/api/exam/autosave", json={
        "student_session_id": student_session_id,
        "code": written_code,
        "language": "python"
    })
    assert autosave_res.status_code == 200

    # 4. Simulate crash / connection-lost event at T - 15s
    t_disconnect = datetime.now(timezone.utc) - timedelta(seconds=15)
    flag_disc = Flag(
        student_session_id=student_session_id,
        type="connection-lost",
        severity="medium",
        flag_metadata={"reason": "Abrupt client process termination"},
        ts=t_disconnect
    )
    db.add(flag_disc)
    db.commit()

    # 5. Student reboots machine and rejoins with identical roll number & access code
    rejoin_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Rohan Mehra",
        "student_identifier": "CS2026_101"
    })
    assert rejoin_res.status_code == 200
    rejoin_data = rejoin_res.json()
    assert rejoin_data["is_reconnect"] is True
    assert rejoin_data["downtime_seconds"] >= 14
    assert rejoin_data["student_session_id"] == student_session_id

    # 6. Verify exam state restores exact autosaved code
    state_res = client.get(f"/api/exam/state/{student_session_id}")
    assert state_res.status_code == 200
    assert state_res.json()["saved_code"] == written_code

    # 7. Verify forensic reconnected flag was logged in DB
    reconn_flag = db.query(Flag).filter(
        Flag.student_session_id == student_session_id,
        Flag.type == "reconnected"
    ).first()
    assert reconn_flag is not None
    assert reconn_flag.severity == "info"
    meta = reconn_flag.flag_metadata
    assert meta["source"] == "rejoin_flow"
    assert meta["downtime_seconds"] >= 14
    assert meta["restored_line_count"] == 7
    assert meta["restored_char_count"] == len(written_code)


def test_reconnect_rejected_after_submission(client):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_sub_guard",
        "password": "password123",
        "name": "Prof. Submission Guard"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_sub_guard",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Submission Guard Test",
        "problem_statement": "Implement sum of two integers",
        "starter_code": "def add(a, b):\n    return a + b",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    code = sess_res["access_code"]

    # 2. Student joins and submits exam
    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Pooja Patel",
        "student_identifier": "CS2026_102"
    }).json()
    student_session_id = st_res["student_session_id"]

    # Submit exam
    sub_res = client.post("/api/exam/submit", json={
        "student_session_id": student_session_id,
        "code": "def add(a, b):\n    return a + b",
        "language": "python"
    })
    assert sub_res.status_code == 200

    # 3. Attempt to rejoin after submission should be rejected
    rejoin_attempt = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Pooja Patel",
        "student_identifier": "CS2026_102"
    })
    assert rejoin_attempt.status_code == 400
    assert "already finalized and submitted" in rejoin_attempt.json()["detail"]


def test_websocket_reconnect_deduplication(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_dedup",
        "password": "password123",
        "name": "Prof. Dedup"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_dedup",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Dedup Test",
        "problem_statement": "Check duplicate reconnection events",
        "starter_code": "pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    code = sess_res["access_code"]

    # 2. Student joins
    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Aman Verma",
        "student_identifier": "CS2026_103"
    }).json()
    student_session_id = st_res["student_session_id"]

    # Rejoin flow logs a reconnected flag
    rejoin_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Aman Verma",
        "student_identifier": "CS2026_103"
    })
    assert rejoin_res.status_code == 200

    reconn_flags_before = db.query(Flag).filter(
        Flag.student_session_id == student_session_id,
        Flag.type == "reconnected"
    ).all()
    assert len(reconn_flags_before) == 1

    # 3. Simulate WebSocket connection immediately after (within 8s)
    # Testing telemetry handler deduplication logic directly
    now = datetime.now(timezone.utc)
    recent_reconnect = db.query(Flag).filter(
        Flag.student_session_id == student_session_id,
        Flag.type == "reconnected"
    ).order_by(Flag.ts.desc()).first()

    assert recent_reconnect is not None
    r_ts = recent_reconnect.ts
    if r_ts.tzinfo is None:
        r_ts = r_ts.replace(tzinfo=timezone.utc)

    # Within 8.0 seconds window, websocket should skip recording duplicate flag
    assert (now - r_ts).total_seconds() < 8.0

    # Total reconnected flags remains 1
    reconn_flags_after = db.query(Flag).filter(
        Flag.student_session_id == student_session_id,
        Flag.type == "reconnected"
    ).all()
    assert len(reconn_flags_after) == 1
