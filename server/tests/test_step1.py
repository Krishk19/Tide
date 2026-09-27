import pytest
from datetime import datetime, timedelta, timezone

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_teacher_register_and_login(client):
    # 1. Register Teacher A
    reg_payload = {
        "username": "prof_sharma",
        "password": "securepassword123",
        "name": "Prof. R. K. Sharma"
    }
    res = client.post("/api/auth/register", json=reg_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "prof_sharma"
    assert "password_hash" not in data

    # 2. Duplicate registration should fail
    dup_res = client.post("/api/auth/register", json=reg_payload)
    assert dup_res.status_code == 400

    # 3. Invalid login should fail
    bad_login = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "wrongpassword"})
    assert bad_login.status_code == 401

    # 4. Correct login returns JWT token
    login_res = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "securepassword123"})
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    token = token_data["access_token"]

    # 5. /api/auth/me returns teacher info
    headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "prof_sharma"

def test_assignment_crud_and_multi_teacher_isolation(client):
    # Login Teacher A
    token_a = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "securepassword123"}).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register & Login Teacher B
    client.post("/api/auth/register", json={
        "username": "dr_patel",
        "password": "patelpassword456",
        "name": "Dr. A. Patel"
    })
    token_b = client.post("/api/auth/login", json={"username": "dr_patel", "password": "patelpassword456"}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Teacher A creates Assignment 1
    assignment_payload = {
        "title": "Two Sum Problem",
        "problem_statement": "Given an array of integers nums and an integer target, return indices of the two numbers.",
        "starter_code": "def two_sum(nums, target):\n    pass",
        "visible_test_cases": [
            {"id": "1", "input": "[2,7,11,15], 9", "expected_output": "[0,1]"}
        ],
        "hidden_test_cases": [
            {"id": "h1", "input": "[3,2,4], 6", "expected_output": "[1,2]"},
            {"id": "h2", "input": "[3,3], 6", "expected_output": "[0,1]"}
        ],
        "language_set": "python,cpp"
    }
    create_res = client.post("/api/assignments", json=assignment_payload, headers=headers_a)
    assert create_res.status_code == 201
    assign_a_id = create_res.json()["id"]

    # Teacher A can view their assignments
    list_a = client.get("/api/assignments", headers=headers_a).json()
    assert len(list_a) == 1
    assert list_a[0]["title"] == "Two Sum Problem"

    # CRITICAL CHECK: Teacher B sees ZERO assignments (Multi-teacher isolation)
    list_b = client.get("/api/assignments", headers=headers_b).json()
    assert len(list_b) == 0

    # CRITICAL CHECK: Teacher B cannot get Teacher A's assignment by ID
    get_unauth = client.get(f"/api/assignments/{assign_a_id}", headers=headers_b)
    assert get_unauth.status_code == 404

    # CRITICAL CHECK: Teacher B cannot delete Teacher A's assignment
    del_unauth = client.delete(f"/api/assignments/{assign_a_id}", headers=headers_b)
    assert del_unauth.status_code == 404

def test_session_creation_and_scoping(client):
    token_a = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "securepassword123"}).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    token_b = client.post("/api/auth/login", json={"username": "dr_patel", "password": "patelpassword456"}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    assignments_a = client.get("/api/assignments", headers=headers_a).json()
    assign_id = assignments_a[0]["id"]

    # Teacher A creates a day-of session
    start_time = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    session_res = client.post("/api/sessions", json={
        "assignment_id": assign_id,
        "start_time": start_time
    }, headers=headers_a)

    assert session_res.status_code == 201
    session_data = session_res.json()
    assert len(session_data["access_code"]) == 6
    assert session_data["status"] == "scheduled"
    assert session_data["assignment_title"] == "Two Sum Problem"

    session_id = session_data["id"]

    # Teacher A sees their session
    sess_list_a = client.get("/api/sessions", headers=headers_a).json()
    assert len(sess_list_a) == 1
    assert sess_list_a[0]["access_code"] == session_data["access_code"]

    # CRITICAL CHECK: Teacher B sees ZERO sessions
    sess_list_b = client.get("/api/sessions", headers=headers_b).json()
    assert len(sess_list_b) == 0

    # CRITICAL CHECK: Teacher B cannot get Teacher A's session by ID
    sess_unauth = client.get(f"/api/sessions/{session_id}", headers=headers_b)
    assert sess_unauth.status_code == 404
