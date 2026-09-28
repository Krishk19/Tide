from tide_server.exam_service import JOIN_ALPHABET, new_join_code, seat_by_token


def test_join_code_shape():
    code = new_join_code()
    assert len(code) == 6 and all(c in JOIN_ALPHABET for c in code)


def test_login_rejects_wrong_pin(client):
    assert client.post("/api/teacher/login", json={"pin": "0000"}).status_code == 401


def test_teacher_endpoints_need_token(client):
    assert client.get("/api/teacher/exam").status_code == 401


def test_create_exam_upload_files_and_read_back(teacher):
    r = teacher.post("/api/teacher/exams", json={"title": "CN Lab", "duration_min": 90,
                                                 "apps": ["VS Code", "Wireshark"]})
    assert r.status_code == 200
    exam = r.json()
    assert exam["duration_s"] == 5400 and len(exam["join_code"]) == 6
    up = teacher.post(f"/api/teacher/exams/{exam['id']}/files", data={"set_name": "A"},
                      files={"file": ("q.txt", b"Q1", "text/plain")})
    assert up.json() == {"name": "q.txt", "set": "A"}
    bad = teacher.post(f"/api/teacher/exams/{exam['id']}/files", data={"set_name": "C"},
                       files={"file": ("q.txt", b"Q1", "text/plain")})
    assert bad.status_code == 422
    got = teacher.get("/api/teacher/exam").json()
    assert got["exam"]["id"] == exam["id"]
    assert got["files"] == [{"name": "q.txt", "set": "A"}]


def test_pair_and_token_lookup(client, ctx, exam, hub):
    r = client.post("/api/pair", json={"join_code": exam.join_code.lower(), "roll": "22bcs107",
                                        "seat_no": 7, "hostname": "LAB3-PC07"})
    assert r.status_code == 200
    body = r.json()
    assert body["seat_no"] == 7 and body["roll"] == "22BCS107"
    with ctx.db() as db:
        assert seat_by_token(db, body["token"]).seat_no == 7
        assert seat_by_token(db, "nope") is None
    assert hub.console_msgs[-1]["t"] == "seat"


def test_bad_code_404(client, exam):
    r = client.post("/api/pair", json={"join_code": "ZZZZZZ", "roll": "x", "seat_no": 1})
    assert r.status_code == 404


def test_seat_taken_by_other_roll_409(client, exam):
    client.post("/api/pair", json={"join_code": exam.join_code, "roll": "A1", "seat_no": 3})
    r = client.post("/api/pair", json={"join_code": exam.join_code, "roll": "B2", "seat_no": 3})
    assert r.status_code == 409


def test_repair_same_roll_same_seat_rotates_token(client, ctx, exam):
    """Review focus #1: an agent restarted mid-exam must be able to rejoin."""
    first = client.post("/api/pair", json={"join_code": exam.join_code, "roll": "A1", "seat_no": 3}).json()
    second = client.post("/api/pair", json={"join_code": exam.join_code, "roll": "A1", "seat_no": 3}).json()
    assert second["seat_id"] == first["seat_id"]
    with ctx.db() as db:
        assert seat_by_token(db, first["token"]) is None
        assert seat_by_token(db, second["token"]).id == first["seat_id"]
