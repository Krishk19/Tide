import base64

from sqlmodel import select

from tide_server import clock, monitor
from tide_server.exam_service import add_file, pair_seat, set_for_seat
from tide_server.models import Exam, Flag, Seat


def test_set_for_seat():
    assert set_for_seat(7, {"A", "B"}) == "A"
    assert set_for_seat(8, {"A", "B"}) == "B"
    assert set_for_seat(8, {"A"}) == "A"


def _seed(ctx, exam):
    with ctx.db() as db:
        add_file(db, exam.id, "A", "qA.txt", b"set A question")
        add_file(db, exam.id, "B", "qB.txt", b"set B question")
        seats = {n: pair_seat(db, exam.join_code, f"R{n}", n, "")[0].id for n in (7, 8, 9)}
    return seats


async def test_blocked_mode_delivers_only_to_offline_ready_seats(ctx, teacher, blocked_exam, hub, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    exam = blocked_exam
    seats = _seed(ctx, exam)
    await ctx.ingest.handle(seats[7], {"t": "preflight", "internet": False, "extensions": ["GitHub Copilot"],
                                       "denied_closed": [], "inventory_count": 12})
    await ctx.ingest.handle(seats[7], {"t": "preflight", "internet": False, "extensions": ["GitHub Copilot"],
                                       "denied_closed": [], "inventory_count": 12})
    await ctx.ingest.handle(seats[8], {"t": "preflight", "internet": False, "extensions": [],
                                       "denied_closed": ["WhatsApp"], "inventory_count": 3})
    await ctx.ingest.handle(seats[9], {"t": "preflight", "internet": True, "extensions": [],
                                       "denied_closed": [], "inventory_count": 0})
    r = teacher.post("/api/teacher/start")
    assert r.status_code == 200 and r.json()["ends_at"] == 1000.0 + 5400

    starts = {sid: m for sid, m in hub.agent_msgs if m["t"] == "start"}
    assert set(starts) == {seats[7], seats[8]}
    assert starts[seats[7]]["set"] == "A" and starts[seats[8]]["set"] == "B"
    assert base64.b64decode(starts[seats[8]]["files"][0]["b64"]) == b"set B question"
    with ctx.db() as db:
        assert db.get(Seat, seats[9]).state == "blocked"
        assert len(db.exec(select(Flag).where(Flag.kind == "ai_extension")).all()) == 1

    # seat 9 disconnects from the internet -> gets its questions late
    await ctx.ingest.handle(seats[9], {"t": "preflight", "internet": False, "extensions": [],
                                       "denied_closed": [], "inventory_count": 0})
    late = [m for sid, m in hub.agent_msgs if sid == seats[9] and m["t"] == "start"]
    assert late and late[0]["set"] == "A"


async def test_extend_per_seat_and_global(ctx, teacher, exam, hub, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    seats = _seed(ctx, exam)
    for n in (7, 8):
        await ctx.ingest.handle(seats[n], {"t": "preflight", "internet": False, "extensions": [],
                                           "denied_closed": [], "inventory_count": 0})
    teacher.post("/api/teacher/start")
    teacher.post("/api/teacher/extend", json={"minutes": 5, "seat_id": seats[7]})
    times = [(sid, m["ends_at"]) for sid, m in hub.agent_msgs if m["t"] == "time"]
    assert times == [(seats[7], 1000.0 + 5400 + 300)]
    teacher.post("/api/teacher/extend", json={"minutes": 5})
    with ctx.db() as db:
        assert db.get(Exam, exam.id).ends_at == 1000.0 + 5400 + 300
        assert db.get(Seat, seats[7]).ends_at_override == 1000.0 + 5400 + 600


async def test_monitor_ends_seats_when_time_is_up(ctx, teacher, exam, hub, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    seats = _seed(ctx, exam)
    await ctx.ingest.handle(seats[7], {"t": "preflight", "internet": False, "extensions": [],
                                       "denied_closed": [], "inventory_count": 0})
    teacher.post("/api/teacher/start")
    monkeypatch.setattr(clock, "now", lambda: 1000.0 + 5400)
    with ctx.db() as db:
        s = db.get(Seat, seats[7])
        s.last_seen = 1000.0 + 5400
        db.add(s)
        db.commit()
    await monitor.tick(ctx)
    await monitor.tick(ctx)
    ends = [sid for sid, m in hub.agent_msgs if m["t"] == "end"]
    assert ends == [seats[7]]


def test_reconnect_during_live_redelivers(client, ctx, exam, monkeypatch):
    """Review focus #1: a restarted agent gets its set and the server end time again."""
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    with ctx.db() as db:
        add_file(db, exam.id, "A", "qA.txt", b"A")
        seat, token = pair_seat(db, exam.join_code, "R7", 7, "")
    login = client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token})
        ws.receive_json()
        ws.send_json({"t": "preflight", "internet": False, "extensions": [], "denied_closed": [],
                      "inventory_count": 0})
        client.post("/api/teacher/start", headers={"Authorization": f"Bearer {login}"})
        assert ws.receive_json()["t"] == "start"
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token})
        welcome = ws.receive_json()
        again = ws.receive_json()
    assert welcome["exam_state"] == "live" and welcome["ends_at"] == 1000.0 + 5400
    assert again["t"] == "start" and again["set"] == "A"


def test_warn_and_force_submit(teacher, ctx, paired, hub):
    seat, _ = paired
    teacher.post(f"/api/teacher/seats/{seat.id}/warn", json={"text": "Eyes on your screen"})
    teacher.post(f"/api/teacher/seats/{seat.id}/force-submit")
    kinds = [m["t"] for sid, m in hub.agent_msgs if sid == seat.id]
    assert kinds == ["notice", "end"]


async def test_allowed_mode_delivers_to_online_seats(ctx, teacher, exam, hub, monkeypatch):
    """Default exams allow internet (monitored): being online never withholds questions."""
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    seats = _seed(ctx, exam)
    await ctx.ingest.handle(seats[9], {"t": "preflight", "internet": True, "extensions": [],
                                       "denied_closed": [], "inventory_count": 0})
    with ctx.db() as db:
        assert db.get(Seat, seats[9]).state == "ready"
    teacher.post("/api/teacher/start")
    assert any(sid == seats[9] and m["t"] == "start" for sid, m in hub.agent_msgs)
