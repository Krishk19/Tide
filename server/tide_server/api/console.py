from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import select

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.exam_service import current_exam, open_flags
from tide_server.models import Flag, Seat
from tide_server.serialize import exam_out, flag_out, seat_out

router = APIRouter()


def console_hello(ctx: Ctx) -> dict:
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None:
            return {"t": "hello", "exam": None, "seats": [], "flags": [], "mode": ctx.pipeline.mode,
                    "server_time": clock.now()}
        seats = db.exec(select(Seat).where(Seat.exam_id == exam.id).order_by(Seat.seat_no)).all()
        seat_no = {s.id: s.seat_no for s in seats}
        flags = db.exec(select(Flag).order_by(Flag.id.desc()).limit(300)).all()
        return {"t": "hello", "exam": exam_out(exam),
                "seats": [seat_out(s, open_flags(db, s.id)) for s in seats],
                "flags": [flag_out(f, seat_no[f.seat_id]) for f in flags if f.seat_id in seat_no],
                "mode": ctx.pipeline.mode, "server_time": clock.now()}


@router.websocket("/ws/console")
async def ws_console(ws: WebSocket, token: str = ""):
    ctx: Ctx = ws.app.state.ctx
    await ws.accept()
    if token not in ctx.teacher_tokens:
        await ws.close(code=4401)
        return
    ctx.hub.add_console(ws)
    try:
        await ws.send_json(console_hello(ctx))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ctx.hub.remove_console(ws)
