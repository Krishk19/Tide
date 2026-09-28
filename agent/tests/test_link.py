import asyncio
import json

import websockets

from tide_agent.clock import ServerClock, compute_offset
from tide_agent.link import Link
from tide_agent.outbox import Outbox


def test_compute_offset_uses_midpoint():
    assert compute_offset(sent=100.0, server_time=160.5, received=101.0) == 60.0


def test_server_clock_conversion():
    c = ServerClock(offset=60.0)
    assert c.to_local(1060.0) == 1000.0


def test_outbox_roundtrip(tmp_path):
    ob = Outbox(tmp_path / "o.jsonl")
    ob.append({"t": "flag", "n": 1})
    ob.append({"t": "flag", "n": 2})
    assert [m["n"] for m in ob.drain()] == [1, 2]
    assert ob.drain() == []


async def test_link_buffers_offline_then_flushes(tmp_path):
    """Review focus #4: flags raised while the server is unreachable arrive later; heartbeats don't."""
    received: list[dict] = []

    async def handler(ws):
        hello = json.loads(await ws.recv())
        assert hello["t"] == "hello" and hello["token"] == "tok"
        await ws.send(json.dumps({"t": "welcome", "server_time": 0.0, "policy": {}}))
        async for raw in ws:
            received.append(json.loads(raw))

    got: list[dict] = []

    async def on_message(m):
        got.append(m)

    link = Link("ws://127.0.0.1:1/ws/agent", "tok", on_message, Outbox(tmp_path / "o.jsonl"))
    assert await link.send({"t": "flag", "ref": "a"}) is False
    assert await link.send({"t": "heartbeat"}) is False

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        link.url = f"ws://127.0.0.1:{port}/ws/agent"
        task = asyncio.create_task(link.run())
        await asyncio.wait_for(link.connected.wait(), 5)
        assert await link.send({"t": "event", "n": 1}) is True
        await asyncio.sleep(0.2)
        task.cancel()
    assert got[0]["t"] == "welcome" and "_offset" in got[0]
    assert [m["t"] for m in received] == ["flag", "event"]


async def test_link_stops_on_4401(tmp_path):
    async def handler(ws):
        await ws.recv()
        await ws.close(code=4401)

    got: list[dict] = []

    async def on_message(m):
        got.append(m)

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        link = Link(f"ws://127.0.0.1:{port}/ws/agent", "bad", on_message, Outbox(tmp_path / "o.jsonl"))
        await asyncio.wait_for(link.run(), 5)
    assert got == [{"t": "auth_failed"}]
