from typing import Any

from fastapi import WebSocket


class Hub:
    """Who is connected right now: one socket per seat, any number of consoles."""

    def __init__(self) -> None:
        self.agents: dict[int, WebSocket] = {}
        self.consoles: set[WebSocket] = set()

    def add_agent(self, seat_id: int, ws: WebSocket) -> None:
        self.agents[seat_id] = ws

    def remove_agent(self, seat_id: int, ws: WebSocket) -> None:
        if self.agents.get(seat_id) is ws:
            del self.agents[seat_id]

    async def to_agent(self, seat_id: int, message: dict[str, Any]) -> bool:
        ws = self.agents.get(seat_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            self.agents.pop(seat_id, None)
            return False

    def add_console(self, ws: WebSocket) -> None:
        self.consoles.add(ws)

    def remove_console(self, ws: WebSocket) -> None:
        self.consoles.discard(ws)

    async def to_console(self, message: dict[str, Any]) -> None:
        for ws in list(self.consoles):
            try:
                await ws.send_json(message)
            except Exception:
                self.consoles.discard(ws)
