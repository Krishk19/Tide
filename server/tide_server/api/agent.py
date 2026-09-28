from fastapi import File, Form, UploadFile
from tide_server.models import Submission
from tide_server.live import deliver
import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from sqlmodel import Session

from tide_common.protocol import msg

from tide_server.exam_service import current_exam, effective_end, seat_by_token
from tide_server.models import Seat
from tide_server.serialize import exam_policy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tide_server import clock
from tide_server.ctx import Ctx, get_ctx
from tide_server.exam_service import PairError, pair_seat
from tide_server.live import add_event, push_event, push_seat
from tide_server.models import Exam

router = APIRouter()


class PairIn(BaseModel):
    join_code: str
    roll: str = Field(min_length=1, max_length=20)
    seat_no: int = Field(ge=1, le=200)
    hostname: str = ""


@router.post("/api/pair")
async def pair(body: PairIn, ctx: Ctx = Depends(get_ctx)):
    with ctx.db() as db:
        try:
            seat, token = pair_seat(db, body.join_code, body.roll, body.seat_no, body.hostname)
        except PairError as e:
            raise HTTPException(e.status, e.message)
        exam = db.get(Exam, seat.exam_id)
    await push_event(ctx, add_event(ctx, seat.id, "joined", {"hostname": body.hostname}))
    await push_seat(ctx, seat.id)
    return {"token": token, "seat_id": seat.id, "seat_no": seat.seat_no, "roll": seat.roll,
            "exam_title": exam.title, "server_time": clock.now()}


def welcome_message(db: Session, seat: Seat) -> dict:
    exam = db.get(Exam, seat.exam_id)
    policy = exam_policy(exam)
    return msg("welcome", seat_no=seat.seat_no, roll=seat.roll, set=seat.set_name,
               policy=policy.to_dict(), server_time=clock.now(), exam_state=exam.state,
               ends_at=effective_end(exam, seat) if exam.state == "live" else None)


@router.websocket("/ws/agent")
async def ws_agent(ws: WebSocket):
    ctx: Ctx = ws.app.state.ctx
    await ws.accept()
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=5)
    except Exception:
        await ws.close(code=4401)
        return
    with ctx.db() as db:
        seat = seat_by_token(db, hello.get("token", "")) if hello.get("t") == "hello" else None
        if seat is None:
            await ws.close(code=4401)
            return
        seat_id = seat.id
        welcome = welcome_message(db, seat)
    ctx.hub.add_agent(seat_id, ws)
    await ws.send_json(welcome)
    await ctx.ingest.handle(seat_id, {"t": "heartbeat"})
    if welcome["exam_state"] == "live" and welcome["set"]:
        await deliver(ctx, seat_id)
    try:
        while True:
            await ctx.ingest.handle(seat_id, await ws.receive_json())
    except WebSocketDisconnect:
        pass
    finally:
        ctx.hub.remove_agent(seat_id, ws)


@router.post("/api/submit")
async def submit(token: str = Form(...), auto: bool = Form(False), file: UploadFile = File(...),
                 ctx: Ctx = Depends(get_ctx)):
    data = await file.read()
    with ctx.db() as db:
        seat = seat_by_token(db, token)
        if seat is None:
            raise HTTPException(401, "Unknown seat")
        folder = ctx.settings.data_dir / "submissions"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"PC{seat.seat_no:02d}_{seat.roll}.zip"
        (folder / name).write_bytes(data)
        db.add(Submission(seat_id=seat.id, ts=clock.now(), file_name=name, auto=auto))
        seat.state = "submitted"
        db.add(seat)
        db.commit()
        seat_id = seat.id
    await push_event(ctx, add_event(ctx, seat_id, "submitted", {"auto": auto}))
    await push_seat(ctx, seat_id)
    return {"ok": True}
