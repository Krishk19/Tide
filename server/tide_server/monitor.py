"""Background checks: silent agents go grey; time-up seats get told to submit."""
import asyncio

from sqlmodel import select

from tide_common.protocol import msg

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.exam_service import current_exam, effective_end
from tide_server.live import raise_flag
from tide_server.models import Seat

WATCHED_STATES = ("lobby", "ready", "blocked", "live")


async def tick(ctx: Ctx) -> None:
    t = clock.now()
    went_offline: list[int] = []
    to_end: list[int] = []
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None:
            return
        seats = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.simulated == False)).all()  # noqa: E712
        for seat in seats:
            if seat.state in WATCHED_STATES and t - seat.last_seen > ctx.settings.heartbeat_timeout_s:
                seat.resume_state = seat.state
                seat.state = "offline"
                db.add(seat)
                went_offline.append(seat.id)
            end = effective_end(exam, seat)
            if (exam.state == "live" and seat.state == "live" and end and t >= end
                    and seat.id not in ctx.ended_seats):
                to_end.append(seat.id)
        if exam.state == "live" and exam.ends_at:
            latest = max([effective_end(exam, s) or 0 for s in seats] + [exam.ends_at])
            if t >= latest + 60:
                exam.state = "ended"
                db.add(exam)
        db.commit()
    for seat_id in went_offline:
        await raise_flag(ctx, seat_id, kind="agent_offline", severity="critical",
                         title="Agent offline", source="server")
    for seat_id in to_end:
        ctx.ended_seats.add(seat_id)
        await ctx.hub.to_agent(seat_id, msg("end", reason="time"))


async def run(ctx: Ctx, interval: float = 2.0) -> None:
    while True:
        try:
            await tick(ctx)
        except Exception as e:  # keep the loop alive during a demo
            print(f"[monitor] {e!r}")
        await asyncio.sleep(interval)
