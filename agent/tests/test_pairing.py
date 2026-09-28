import json
import socket
import threading

import httpx
import pytest

from tide_agent.discovery import discover, parse_server
from tide_agent.pairing import PairError, pair, submit


def test_parse_server():
    assert parse_server("10.10.0.1") == ("10.10.0.1", 8765)
    assert parse_server("10.10.0.1:9000") == ("10.10.0.1", 9000)


def test_discover_finds_responder():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def respond():
        data, addr = sock.recvfrom(64)
        if data == b"TIDE?":
            sock.sendto(json.dumps({"tide": 1, "port": 8765}).encode(), addr)

    threading.Thread(target=respond, daemon=True).start()
    assert discover(timeout=2, port=port, targets=("127.0.0.1",)) == ("127.0.0.1", 8765)
    sock.close()


def test_discover_times_out():
    assert discover(timeout=0.2, port=9, targets=("127.0.0.1",)) is None


async def test_pair_ok_and_error():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        if body["join_code"] == "BAD":
            return httpx.Response(404, json={"detail": "Unknown join code"})
        return httpx.Response(200, json={"token": "t", "seat_id": 1, "seat_no": 7, "roll": "R",
                                         "exam_title": "CN", "server_time": 1.0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    r = await pair("http://s:8765", "K7Q2XM", "r", 7, "PC", client=client)
    assert (r.token, r.seat_no) == ("t", 7)
    with pytest.raises(PairError, match="Unknown join code"):
        await pair("http://s:8765", "BAD", "r", 7, "PC", client=client)


async def test_submit_posts_zip():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    await submit("http://s:8765", "t", b"PKzip", False,
                 client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert b"PKzip" in seen["body"] and b'name="token"' in seen["body"]
