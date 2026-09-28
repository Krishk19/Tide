import pytest
from starlette.websockets import WebSocketDisconnect


def login(client):
    return client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]


def test_console_ws_requires_token(client, exam):
    with client.websocket_connect("/ws/console?token=bad") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_console_hello_has_room(client, exam, paired):
    with client.websocket_connect(f"/ws/console?token={login(client)}") as ws:
        hello = ws.receive_json()
    assert hello["t"] == "hello" and hello["mode"] == "heuristics"
    assert hello["exam"]["join_code"] == exam.join_code
    assert [s["seat_no"] for s in hello["seats"]] == [7]


async def test_seat_detail_review_and_shot(teacher, ctx, paired):
    seat, _ = paired
    await ctx.ingest.handle(seat.id, {"t": "event", "kind": "window", "data": {"process": "code.exe"}, "ts": 5})
    await ctx.ingest.handle(seat.id, {"t": "flag", "ref": "r", "kind": "usb", "severity": "high",
                                      "title": "USB drive inserted", "data": {}, "ts": 6, "action": "none"})
    await ctx.ingest.handle(seat.id, {"t": "evidence", "ref": "r", "jpeg_b64": "/9j/AA=="})
    await ctx.ingest.handle(seat.id, {"t": "snapshot", "ts": 7, "files": [{"path": "main.c", "text": "a\nb\n", "sha": "1"}]})
    d = teacher.get(f"/api/teacher/seats/{seat.id}").json()
    assert d["seat"]["status"] == "crit"
    assert [i["type"] for i in d["timeline"]][:2] == ["flag", "event"]
    assert d["growth"] == [{"ts": 7, "lines": 2}] and d["files"] == [{"path": "main.c", "lines": 2}]
    flag_id = d["timeline"][0]["id"]
    token = teacher.headers["Authorization"].split()[1]
    assert teacher.get(f"/api/teacher/shots/{flag_id}?token={token}").status_code == 200
    r = teacher.patch(f"/api/teacher/flags/{flag_id}", json={"status": "dismissed"})
    assert r.json()["status"] == "dismissed"
    assert teacher.get(f"/api/teacher/seats/{seat.id}").json()["seat"]["status"] == "wait"


def test_catalog(teacher):
    c = teacher.get("/api/teacher/catalog").json()
    assert "Wireshark" in c["apps"] and "networking" in c["presets"]
