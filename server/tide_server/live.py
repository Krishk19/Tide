from tide_server.exam_service import start_message
from tide_server.models import Exam
"""Write-then-broadcast helpers. Every state change the console must see goes through here."""
import json
from typing import Any

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.exam_service import open_flags
from tide_server.models import Event, Flag, Seat
from tide_server.serialize import event_out, flag_out, seat_out


def add_event(ctx: Ctx, seat_id: int, kind: str, data: dict[str, Any] | None = None,
              ts: float | None = None) -> Event:
    with ctx.db() as db:
        e = Event(seat_id=seat_id, ts=ts or clock.now(), kind=kind, data_json=json.dumps(data or {}))
        db.add(e)
        db.commit()
        db.refresh(e)
        return e


async def push_seat(ctx: Ctx, seat_id: int) -> None:
    with ctx.db() as db:
        seat = db.get(Seat, seat_id)
        message = {"t": "seat", "seat": seat_out(seat, open_flags(db, seat_id))}
    await ctx.hub.to_console(message)


async def push_event(ctx: Ctx, event: Event) -> None:
    await ctx.hub.to_console({"t": "event", "event": event_out(event)})


async def push_flag(ctx: Ctx, flag_id: int) -> None:
    with ctx.db() as db:
        flag = db.get(Flag, flag_id)
        seat = db.get(Seat, flag.seat_id)
        message = {"t": "flag", "flag": flag_out(flag, seat.seat_no)}
    await ctx.hub.to_console(message)


async def raise_flag(ctx: Ctx, seat_id: int, *, kind: str, severity: str, title: str, source: str,
                     data: dict[str, Any] | None = None, action: str = "none",
                     label: str | None = None, confidence: float | None = None,
                     ref: str | None = None, ts: float | None = None) -> Flag:
    with ctx.db() as db:
        flag = Flag(seat_id=seat_id, ts=ts or clock.now(), kind=kind, severity=severity, title=title,
                    source=source, label=label, confidence=confidence,
                    data_json=json.dumps(data or {}), action=action, ref=ref)
        db.add(flag)
        db.commit()
        db.refresh(flag)
    await push_flag(ctx, flag.id)
    await push_seat(ctx, seat_id)
    return flag


async def deliver(ctx: Ctx, seat_id: int) -> None:
    with ctx.db() as db:
        seat = db.get(Seat, seat_id)
        message = start_message(db, db.get(Exam, seat.exam_id), seat)
    await ctx.hub.to_agent(seat_id, message)
    await push_event(ctx, add_event(ctx, seat_id, "start", {"set": message["set"],
                                                           "files": len(message["files"])}))
    await push_seat(ctx, seat_id)
