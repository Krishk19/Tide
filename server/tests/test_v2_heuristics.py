import pytest
from datetime import datetime, timezone, timedelta

def test_correlated_cheat_detection_and_risk_scoring(client):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_v2_heuristics",
        "password": "password123",
        "name": "Prof. V2 Heuristics"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_v2_heuristics",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Algorithmic Correlation Test",
        "problem_statement": "Implement binary search on a sorted integer list",
        "starter_code": "def search(nums, target):\n    pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    code = sess_res["access_code"]
    session_id = sess_res["id"]

    # 2. Student Joins
    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Kunal Deshmukh",
        "student_identifier": "CS2026_088"
    }).json()
    student_session_id = st_res["student_session_id"]

    # 3. Step 1: Student blurs window (focus-lost) at T0
    now = datetime.now(timezone.utc)
    res_blur = client.post("/api/telemetry/event", json={
        "student_session_id": student_session_id,
        "type": "focus-lost",
        "metadata": {"source": "alt-tab"},
        "ts": now.isoformat()
    })
    assert res_blur.status_code == 200
    assert res_blur.json()["type"] == "focus-lost"
    assert res_blur.json()["risk_score"] == 5

    # 4. Step 2: 2.5 seconds later, student pastes 80 characters of external code
    paste_time = now + timedelta(seconds=2.5)
    res_paste = client.post("/api/telemetry/event", json={
        "student_session_id": student_session_id,
        "type": "paste",
        "metadata": {
            "length": 80,
            "sample": "def binary_search(arr, x):\n  l = 0\n  r = len(arr)-1",
            "source": "external-source"
        },
        "ts": paste_time.isoformat()
    })
    assert res_paste.status_code == 200

    # 5. Verify Correlation: A 'correlated-cheat-attempt' flag was generated!
    flags = client.get(f"/api/dashboard/flags?session_id={session_id}", headers=headers).json()
    types = [f["type"] for f in flags]
    assert "focus-lost" in types
    assert "paste" in types
    assert "correlated-cheat-attempt" in types

    corr_flag = next(f for f in flags if f["type"] == "correlated-cheat-attempt")
    assert corr_flag["severity"] == "critical"
    assert corr_flag["metadata"]["paste_length"] == 80
    assert corr_flag["metadata"]["confidence"] == "high"

    # 6. Verify Dynamic Risk Score on Student Roster
    session_details = client.get(f"/api/sessions/{session_id}", headers=headers).json()
    student_row = next(s for s in session_details["students"] if s["id"] == student_session_id)
    # Risk score: focus-lost(5) + paste(80//25 = 3) + correlated-cheat-attempt(40) = 48
    assert student_row["risk_score"] == 48

    # 7. Non-Destructive Review with Notes: Dismissing false positive drops risk score
    dismiss_res = client.patch(f"/api/dashboard/flags/{corr_flag['id']}", json={
        "status": "dismissed",
        "notes": "Student verified: was just switching between editor tabs"
    }, headers=headers)
    assert dismiss_res.status_code == 200
    assert dismiss_res.json()["status"] == "dismissed"
    assert dismiss_res.json()["notes"] == "Student verified: was just switching between editor tabs"
    # Dismissing the 40pt flag leaves 5 + 3 = 8
    assert dismiss_res.json()["risk_score"] == 8

    # Check updated session details reflects decreased risk score
    session_details_updated = client.get(f"/api/sessions/{session_id}", headers=headers).json()
    student_row_updated = next(s for s in session_details_updated["students"] if s["id"] == student_session_id)
    assert student_row_updated["risk_score"] == 8

def test_normal_paste_does_not_trigger_false_correlation(client):
    # Register teacher & session
    client.post("/api/auth/register", json={
        "username": "prof_normal_paste",
        "password": "password123",
        "name": "Prof. Normal Paste"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_normal_paste",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Normal Coding Flow",
        "problem_statement": "Check if string has duplicate characters in Python",
        "starter_code": "def has_dup(s):\n    pass",
        "visible_test_cases": [],
        "hidden_test_cases": []
    }, headers=headers).json()["id"]

    sess_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": datetime.now(timezone.utc).isoformat()
    }, headers=headers).json()
    code = sess_res["access_code"]
    session_id = sess_res["id"]

    st_res = client.post("/api/sessions/join", json={
        "access_code": code,
        "student_name": "Neha Joshi",
        "student_identifier": "CS2026_090"
    }).json()
    student_session_id = st_res["student_session_id"]

    # Student pastes a short token (8 chars, e.g. variable name) without any prior blur
    res_paste = client.post("/api/telemetry/event", json={
        "student_session_id": student_session_id,
        "type": "paste",
        "metadata": {"length": 8, "sample": "var_temp"}
    })
    assert res_paste.status_code == 200

    flags = client.get(f"/api/dashboard/flags?session_id={session_id}", headers=headers).json()
    types = [f["type"] for f in flags]
    # No correlated-cheat-attempt should exist!
    assert "correlated-cheat-attempt" not in types
