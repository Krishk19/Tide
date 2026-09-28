import pytest
from starlette.websockets import WebSocketDisconnect

from tide_server import clock, monitor
from tide_server.models import Event, Flag, Seat
from sqlmodel import select


def test_bad_token_is_rejected(client, paired):
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_hello_gets_welcome_with_policy(client, paired):
    seat, token = paired
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token, "agent_version": "0.1", "local_time": 0})
        w = ws.receive_json()
    assert w["t"] == "welcome"
    assert w["seat_no"] == 7 and w["exam_state"] == "lobby"
    assert "code.exe" in w["policy"]["allowed_processes"]


def test_heartbeat_updates_last_seen_and_app(client, ctx, paired, monkeypatch):
    seat, token = paired
    monkeypatch.setattr(clock, "now", lambda: 5000.0)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token})
        ws.receive_json()
        ws.send_json({"t": "heartbeat", "fg": "Code.exe"})
        ws.send_json({"t": "heartbeat", "fg": "Code.exe"})   # second message proves the first was processed
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
    assert s.last_seen == 5000.0 and s.fg_app == "VS Code"


async def test_monitor_marks_offline_then_back(ctx, paired, hub, monkeypatch):
    seat, _ = paired
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
        s.state, s.last_seen = "live", 100.0
        db.add(s)
        db.commit()
    monkeypatch.setattr(clock, "now", lambda: 111.0)
    await monitor.tick(ctx)
    await monitor.tick(ctx)   # idempotent: still one flag
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
        flags = db.exec(select(Flag).where(Flag.kind == "agent_offline")).all()
    assert s.state == "offline" and s.resume_state == "live"
    assert len(flags) == 1 and flags[0].severity == "critical"

    monkeypatch.setattr(clock, "now", lambda: 130.0)
    await ctx.ingest.handle(seat.id, {"t": "heartbeat", "fg": "code.exe"})
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
        back = db.exec(select(Event).where(Event.kind == "agent_back")).one()
    assert s.state == "live"
    assert '"gap": 30' in back.data_json
