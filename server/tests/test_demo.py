import asyncio
import json
import socket

from fastapi.testclient import TestClient
from sqlmodel import select

from tide_server import clock
from tide_server.app import create_app
from tide_server.discovery import start_discovery
from tide_server.models import Flag, Seat
from tide_server.simulate import SCRIPT, SimRoom


async def test_discovery_replies():
    transport = await start_discovery("127.0.0.1", 0, 8765)
    port = transport.get_extra_info("sockname")[1]
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.sendto(b"TIDE?", ("127.0.0.1", port))
    data = await asyncio.wait_for(loop.sock_recv(sock, 1024), 2)
    transport.close()
    sock.close()
    assert json.loads(data) == {"tide": 1, "port": 8765}


def test_demo_without_mock_has_exam_but_no_fake_seats(settings):
    app = create_app(settings.model_copy(update={"demo": True}))
    with TestClient(app):
        ctx = app.state.ctx
        with ctx.db() as db:
            assert db.exec(select(Seat)).all() == []
            from tide_server.models import ExamFile
            assert len(db.exec(select(ExamFile)).all()) == 4


def test_mock_room_boot_seeds_room(settings):
    app = create_app(settings.model_copy(update={"demo": True, "mock_room": True}))
    with TestClient(app):
        ctx = app.state.ctx
        with ctx.db() as db:
            seats = db.exec(select(Seat)).all()
    assert len(seats) == 59 and 7 not in {s.seat_no for s in seats}
    by_no = {s.seat_no: s for s in seats}
    assert by_no[19].state == "ready" and by_no[58].state == "lobby"   # demo exam allows internet


async def test_sim_script_fires_after_start(settings, monkeypatch):
    app = create_app(settings.model_copy(update={"demo": True, "mock_room": True}))
    with TestClient(app) as client:
        ctx = app.state.ctx
        token = client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]
        monkeypatch.setattr(clock, "now", lambda: 1000.0)
        client.post("/api/teacher/start", headers={"Authorization": f"Bearer {token}"})
        room = SimRoom(ctx, ctx.extras["exam_id"])
        first = SCRIPT[0]
        monkeypatch.setattr(clock, "now", lambda: 1000.0 + first.at_s + 0.1)
        await room.tick()
        await room.tick()
        with ctx.db() as db:
            flags = db.exec(select(Flag).where(Flag.title == first.title)).all()
        assert len(flags) == 1


def test_simulate_endpoint(teacher, ctx, paired):
    r = teacher.post("/api/teacher/simulate", json={"seat_no": 7, "kind": "jev_ai"})
    assert r.status_code == 200
    with ctx.db() as db:
        f = db.exec(select(Flag)).one()
    assert (f.source, f.label, f.confidence) == ("jev", "ai_assistant", 0.96)
    assert teacher.post("/api/teacher/simulate", json={"seat_no": 7, "kind": "nope"}).status_code == 422


def test_real_agent_takes_over_simulated_seat(settings):
    app = create_app(settings.model_copy(update={"demo": True, "mock_room": True}))
    with TestClient(app) as client:
        ctx = app.state.ctx
        from tide_server.models import Exam
        with ctx.db() as db:
            join = db.get(Exam, ctx.extras["exam_id"]).join_code
        r = client.post("/api/pair", json={"join_code": join, "roll": "22BCS108", "seat_no": 8})
        assert r.status_code == 200
        with ctx.db() as db:
            s = db.get(Seat, r.json()["seat_id"])
        assert (s.simulated, s.state) == (False, "lobby")


async def test_mock_room_follows_the_exam_the_teacher_creates(settings):
    app = create_app(settings.model_copy(update={"mock_room": True}))
    with TestClient(app) as client:
        ctx = app.state.ctx
        room = SimRoom(ctx)
        await room.tick()                                   # no exam yet: nothing happens
        token = client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]
        client.post("/api/teacher/exams", json={"title": "My test", "duration_min": 60, "apps": ["VS Code"]},
                    headers={"Authorization": f"Bearer {token}"})
        await room.tick()
        with ctx.db() as db:
            assert len(db.exec(select(Seat).where(Seat.simulated == True)).all()) == 59  # noqa: E712
