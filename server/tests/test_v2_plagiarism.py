import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from app.main import app
from app.services.plagiarism import (
    tokenize_code,
    compute_similarity,
    analyze_session_plagiarism,
    get_pairwise_diff
)


def test_python_ast_identifier_renaming():
    code_a = """
def calculate_factorial(n):
    result = 1
    for i in range(1, n + 1):
        result = result * i
    return result
"""
    code_b = """
def fact(num):
    ans = 1
    for x in range(1, num + 1):
        ans = ans * x
    return ans
"""
    tokens_a = tokenize_code(code_a, "python")
    tokens_b = tokenize_code(code_b, "python")

    assert len(tokens_a) > 0
    assert len(tokens_b) > 0

    score, shared_k, total_k = compute_similarity(tokens_a, tokens_b, k=4)
    # Identical AST skeleton despite complete variable & function renaming
    assert score >= 95.0
    assert shared_k > 0


def test_python_ast_distinct_algorithms_low_similarity():
    code_a = """
def calculate_factorial(n):
    result = 1
    for i in range(1, n + 1):
        result = result * i
    return result
"""
    code_b = """
def is_palindrome(text):
    clean = text.lower().replace(" ", "")
    return clean == clean[::-1]
"""
    tokens_a = tokenize_code(code_a, "python")
    tokens_b = tokenize_code(code_b, "python")

    score, _, _ = compute_similarity(tokens_a, tokens_b, k=4)
    assert score < 30.0


def test_cpp_generic_tokenization_renaming():
    cpp_a = """
int sumArray(int arr[], int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += arr[i];
    }
    return total;
}
"""
    cpp_b = """
int calculate(int list[], int size) {
    int sum = 0;
    for (int k = 0; k < size; k++) {
        sum += list[k];
    }
    return sum;
}
"""
    tokens_a = tokenize_code(cpp_a, "cpp")
    tokens_b = tokenize_code(cpp_b, "cpp")

    assert len(tokens_a) > 0
    assert len(tokens_b) > 0

    score, shared_k, total_k = compute_similarity(tokens_a, tokens_b, k=4)
    assert score >= 85.0


def test_starter_code_subtraction():
    starter = """
def solution(nums):
    # Student code goes here
    pass
"""
    # Two students who only have the boilerplate
    code_a = """
def solution(nums):
    pass
"""
    code_b = """
def solution(nums):
    pass
"""
    starter_tokens = tokenize_code(starter, "python")
    tokens_a = tokenize_code(code_a, "python")
    tokens_b = tokenize_code(code_b, "python")

    score, _, _ = compute_similarity(tokens_a, tokens_b, starter_tokens=starter_tokens, k=4)
    # Should subtract boilerplate and return 0
    assert score == 0.0


def test_similarity_matrix_and_diff_endpoints_with_isolation():
    client = TestClient(app)

    # 1. Register and Login Teacher 1
    client.post("/api/auth/register", json={
        "username": "plag_prof1",
        "email": "prof1@test.edu",
        "password": "password123",
        "name": "Prof Plag One"
    })
    t1_login = client.post("/api/auth/login", json={"username": "plag_prof1", "password": "password123"})
    token1 = t1_login.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    # 2. Register and Login Teacher 2 (for isolation check)
    client.post("/api/auth/register", json={
        "username": "plag_prof2",
        "email": "prof2@test.edu",
        "password": "password123",
        "name": "Prof Plag Two"
    })
    t2_login = client.post("/api/auth/login", json={"username": "plag_prof2", "password": "password123"})
    token2 = t2_login.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # 3. Create Assignment & Session by Teacher 1
    assign_res = client.post("/api/assignments", headers=headers1, json={
        "title": "Factorial Problem",
        "problem_statement": "Compute factorial of n",
        "starter_code": "def solve(n):\n    pass\n",
        "language_set": "python",
        "visible_test_cases": [{"id": "v1", "input": "5\n", "expected_output": "120\n"}],
        "hidden_test_cases": []
    })
    assign_id = assign_res.json()["id"]

    start_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    sess_res = client.post("/api/sessions", headers=headers1, json={
        "assignment_id": assign_id,
        "start_time": start_iso
    })
    session_id = sess_res.json()["id"]
    access_code = sess_res.json()["access_code"]

    # 4. Join Student A and Student B
    join_a = client.post("/api/sessions/join", json={
        "access_code": access_code,
        "student_name": "Alice Plag",
        "student_identifier": "CS-PLAG-01"
    })
    assert join_a.status_code == 200
    student_a_id = join_a.json()["student_session_id"]

    join_b = client.post("/api/sessions/join", json={
        "access_code": access_code,
        "student_name": "Bob Plag",
        "student_identifier": "CS-PLAG-02"
    })
    assert join_b.status_code == 200
    student_b_id = join_b.json()["student_session_id"]

    # 5. Autosave code for both students
    # Alice writes factorial with `result` and `i`
    client.post("/api/exam/autosave", json={
        "student_session_id": student_a_id,
        "code": "import sys\ndef solve(n):\n    result = 1\n    for i in range(1, n + 1):\n        result = result * i\n    return result\nprint(solve(int(sys.stdin.read().strip())))",
        "language": "python"
    })

    # Bob writes identical logic with renamed `ans` and `x`
    client.post("/api/exam/autosave", json={
        "student_session_id": student_b_id,
        "code": "import sys\ndef solve(num):\n    ans = 1\n    for x in range(1, num + 1):\n        ans = ans * x\n    return ans\nprint(solve(int(sys.stdin.read().strip())))",
        "language": "python"
    })

    # 6. Fetch Similarity Matrix via Teacher 1
    mat_res = client.get(f"/api/sessions/{session_id}/similarity-matrix?threshold=60.0", headers=headers1)
    assert mat_res.status_code == 200
    mat_data = mat_res.json()
    assert mat_data["total_students"] == 2
    assert mat_data["total_pairs_compared"] == 1
    assert mat_data["flagged_pairs_count"] == 1

    flagged_pair = mat_data["pairs"][0]
    assert flagged_pair["similarity_pct"] >= 70.0
    assert flagged_pair["is_suspicious"] is True

    # 7. Fetch Side-by-Side Diff
    diff_res = client.get(
        f"/api/sessions/{session_id}/similarity-diff?student_a={student_a_id}&student_b={student_b_id}",
        headers=headers1
    )
    assert diff_res.status_code == 200
    diff_data = diff_res.json()
    assert diff_data["student_a"]["name"] == "Alice Plag"
    assert diff_data["student_b"]["name"] == "Bob Plag"
    assert diff_data["similarity_pct"] >= 70.0
    assert "diff_text" in diff_data

    # 8. Verify Teacher Isolation: Teacher 2 cannot access Teacher 1's similarity matrix or diff
    iso_mat = client.get(f"/api/sessions/{session_id}/similarity-matrix", headers=headers2)
    assert iso_mat.status_code == 404

    iso_diff = client.get(
        f"/api/sessions/{session_id}/similarity-diff?student_a={student_a_id}&student_b={student_b_id}",
        headers=headers2
    )
    assert iso_diff.status_code == 404
