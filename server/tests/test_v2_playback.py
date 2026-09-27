import pytest
from datetime import datetime, timezone, timedelta
from app.models import CodeSnapshot, Flag

def test_code_snapshot_recording_and_deduplication(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_pb1",
        "password": "password123",
        "name": "Prof. Playback One"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_pb1",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Playback Problem",
        "problem_statement": "Implement palindrome check function",
        "starter_code": "def is_palindrome(s):\n    pass",
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
        "student_name": "Devansh Roy",
        "student_identifier": "CS2026_301"
    }).json()
    student_id = st_res["student_session_id"]

    # 3. Snapshot 1: Student starts typing
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": "def is_palindrome(s):\n    clean = s.lower()",
        "language": "python"
    })

    # 4. Snapshot 2: Duplicate autosave (same code) - should NOT duplicate snapshot
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": "def is_palindrome(s):\n    clean = s.lower()",
        "language": "python"
    })

    snapshots_1 = db.query(CodeSnapshot).filter(
        CodeSnapshot.student_session_id == student_id
    ).all()
    # At most 1 snapshot exists for this code
    assert len(snapshots_1) == 1
    assert snapshots_1[0].lines_count == 2

    # 5. Snapshot 3: Normal typing growth
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": "def is_palindrome(s):\n    clean = s.lower()\n    return clean == clean[::-1]",
        "language": "python"
    })

    snapshots_2 = db.query(CodeSnapshot).filter(
        CodeSnapshot.student_session_id == student_id
    ).order_by(CodeSnapshot.ts.asc()).all()
    assert len(snapshots_2) == 2
    assert snapshots_2[1].lines_count == 3
    assert snapshots_2[1].is_paste_event is False

    # 6. Snapshot 4: Sudden bulk paste (+120 chars in one go)
    bulk_code = (
        "def is_palindrome(s):\n"
        "    clean = s.lower()\n"
        "    return clean == clean[::-1]\n\n"
        "# Sudden 120+ char injected algorithmic logic block\n"
        "def extended_palindrome_partition(text):\n"
        "    return [text[i:j] for i in range(len(text)) for j in range(i+1, len(text)+1)]"
    )
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": bulk_code,
        "language": "python"
    })

    snapshots_3 = db.query(CodeSnapshot).filter(
        CodeSnapshot.student_session_id == student_id
    ).order_by(CodeSnapshot.ts.asc()).all()
    assert len(snapshots_3) == 3
    assert snapshots_3[2].is_paste_event is True
    assert snapshots_3[2].lines_count == 7


def test_playback_timeline_endpoint(client, db):
    # 1. Register Teacher & Session
    client.post("/api/auth/register", json={
        "username": "prof_timeline",
        "password": "password123",
        "name": "Prof. Timeline"
    })
    token = client.post("/api/auth/login", json={
        "username": "prof_timeline",
        "password": "password123"
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assign_id = client.post("/api/assignments", json={
        "title": "Timeline Problem",
        "problem_statement": "Binary tree traversal problem",
        "starter_code": "def traverse():\n    pass",
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
        "student_name": "Riya Sen",
        "student_identifier": "CS2026_302"
    }).json()
    student_id = st_res["student_session_id"]

    # Record some typing milestones
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": "def traverse():\n    visited = []",
        "language": "python"
    })
    client.post("/api/exam/autosave", json={
        "student_session_id": student_id,
        "code": "def traverse():\n    visited = []\n    return visited",
        "language": "python"
    })

    # Log a telemetry flag
    client.post("/api/telemetry/event", json={
        "student_session_id": student_id,
        "type": "paste",
        "metadata": {"length": 45, "source": "external"}
    })

    # Fetch Playback
    pb_res = client.get(f"/api/sessions/{session_id}/students/{student_id}/playback", headers=headers)
    assert pb_res.status_code == 200
    pb_data = pb_res.json()

    assert pb_data["student_name"] == "Riya Sen"
    assert pb_data["total_snapshots"] >= 2
    assert "snapshots" in pb_data
    assert "events" in pb_data
    assert len(pb_data["events"]) >= 1

    # Multi-Teacher Isolation: another teacher cannot view this student's playback
    client.post("/api/auth/register", json={
        "username": "prof_intruder",
        "password": "password123",
        "name": "Prof. Intruder"
    })
    token_intruder = client.post("/api/auth/login", json={
        "username": "prof_intruder",
        "password": "password123"
    }).json()["access_token"]
    intruder_headers = {"Authorization": f"Bearer {token_intruder}"}

    unauthorized_res = client.get(f"/api/sessions/{session_id}/students/{student_id}/playback", headers=intruder_headers)
    assert unauthorized_res.status_code == 404
