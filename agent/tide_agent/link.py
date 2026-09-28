import asyncio
import json
import time
from typing import Awaitable, Callable

import websockets

from tide_common.protocol import msg

from .clock import compute_offset
from .outbox import Outbox

NOT_BUFFERED = {"heartbeat"}


class Link:
    """One WebSocket to the teacher server, reconnecting forever. Sends while offline go to the outbox."""

    def __init__(self, url: str, token: str, on_message: Callable[[dict], Awaitable[None]],
                 outbox: Outbox, version: str = "0.1.0") -> None:
        self.url, self.token, self.on_message, self.outbox, self.version = url, token, on_message, outbox, version
        self.ws = None
        self.connected = asyncio.Event()
        self.offset = 0.0

    async def run(self) -> None:
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(self.url, open_timeout=5, ping_interval=10) as ws:
                    sent = time.time()
                    await ws.send(json.dumps(msg("hello", token=self.token, agent_version=self.version,
                                                 local_time=sent)))
                    welcome = json.loads(await ws.recv())
                    if welcome.get("t") != "welcome":
                        raise ConnectionError("expected welcome")
                    self.offset = compute_offset(sent, welcome["server_time"], time.time())
                    welcome["_offset"] = self.offset
                    self.ws = ws
                    backoff = 1.0
                    await self.on_message(welcome)
                    for pending in self.outbox.drain():
                        await ws.send(json.dumps(pending))
                    self.connected.set()
                    async for raw in ws:
                        await self.on_message(json.loads(raw))
            except websockets.ConnectionClosed as e:
                if e.rcvd is not None and e.rcvd.code == 4401:
                    self.ws = None
                    self.connected.clear()
                    await self.on_message({"t": "auth_failed"})
                    return
            except (OSError, asyncio.TimeoutError, ConnectionError, websockets.WebSocketException):
                pass
            finally:
                self.ws = None
                self.connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5.0)

    async def send(self, message: dict) -> bool:
        ws = self.ws
        if ws is not None:
            try:
                await ws.send(json.dumps(message))
                return True
            except Exception:
                pass
        if message.get("t") not in NOT_BUFFERED:
            self.outbox.append(message)
        return False
