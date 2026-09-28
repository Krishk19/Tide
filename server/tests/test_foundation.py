import json

from tide_server.models import Exam, Flag, Seat
from tide_server.serialize import exam_out, seat_status


def flag(sev, status="open"):
    return Flag(seat_id=1, ts=0, kind="x", severity=sev, title="t", source="rule", status=status)


def test_seat_status_matrix():
    s = Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="live")
    assert seat_status(s, []) == "ok"
    assert seat_status(s, [flag("medium")]) == "warn"
    assert seat_status(s, [flag("medium"), flag("high")]) == "crit"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="lobby"), []) == "wait"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="blocked"), []) == "crit"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="offline"), [flag("critical")]) == "off"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="submitted"), [flag("critical")]) == "done"


def test_engine_creates_tables_and_roundtrips(ctx):
    with ctx.db() as db:
        e = Exam(title="T", duration_s=60, join_code="ABC234",
                 policy_json=json.dumps({"apps": ["VS Code"], "allowed_processes": ["code.exe"], "server_ip": ""}))
        db.add(e)
        db.commit()
        out = exam_out(e)
    assert out["join_code"] == "ABC234"
    assert out["apps"] == ["VS Code"]
    assert out["state"] == "lobby"
