from tide_server.live import raise_flag
from fastapi import Query
from fastapi.responses import FileResponse
from tide_common.policy import APP_CATALOG, PRESETS
from tide_server.exam_service import open_flags
from tide_server.live import push_flag, push_seat
from tide_server.models import Event, Flag, Snapshot, Submission
from tide_server.serialize import event_out, flag_out, seat_out
from tide_server import clock
from fastapi import Response
from tide_server.similarity import results, results_csv
from tide_common.protocol import msg
from tide_server.exam_service import extend, start_exam
from tide_server.live import add_event, deliver, push_event
from tide_server.models import Exam, Seat
import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import select

from tide_server.ctx import Ctx, get_ctx
from tide_server.exam_service import add_file, create_exam, current_exam
from tide_server.models import ExamFile
from tide_server.serialize import exam_out

router = APIRouter(prefix="/api/teacher")


class LoginIn(BaseModel):
    pin: str


class ExamIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    duration_min: int = Field(ge=5, le=300)
    apps: list[str]


@router.post("/login")
def login(body: LoginIn, ctx: Ctx = Depends(get_ctx)):
    if not secrets.compare_digest(body.pin, ctx.settings.teacher_pin):
        raise HTTPException(401, "Wrong PIN")
    token = secrets.token_urlsafe(24)
    ctx.teacher_tokens.add(token)
    return {"token": token}


def require_teacher(authorization: str = Header(""), token: str = Query(""),
                    ctx: Ctx = Depends(get_ctx)) -> Ctx:
    tok = authorization.removeprefix("Bearer ").strip() or token
    if tok not in ctx.teacher_tokens:
        raise HTTPException(401, "Login required")
    return ctx


@router.post("/exams")
def create(body: ExamIn, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        return exam_out(create_exam(db, body.title, body.duration_min * 60, body.apps))


@router.post("/exams/{exam_id}/files")
async def upload(exam_id: int, set_name: str = Form(...), file: UploadFile = File(...),
                 ctx: Ctx = Depends(require_teacher)):
    if set_name not in ("A", "B"):
        raise HTTPException(422, "set_name must be A or B")
    data = await file.read()
    with ctx.db() as db:
        f = add_file(db, exam_id, set_name, file.filename or "file", data)
    return {"name": f.name, "set": f.set_name}


@router.get("/exam")
def get_exam(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None:
            return {"exam": None, "files": []}
        files = db.exec(select(ExamFile).where(ExamFile.exam_id == exam.id)).all()
        return {"exam": exam_out(exam), "files": [{"name": f.name, "set": f.set_name} for f in files]}


class ExtendIn(BaseModel):
    minutes: int = Field(ge=1, le=120)
    seat_id: int | None = None


class TextIn(BaseModel):
    text: str = Field(default="Please keep your eyes on your own screen.", max_length=200)


def _exam(db) -> Exam:
    exam = current_exam(db)
    if exam is None:
        raise HTTPException(404, "No exam")
    return exam


@router.post("/start")
async def start(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        exam = _exam(db)
        if exam.state != "lobby":
            raise HTTPException(409, "Exam already started")
        seat_ids = start_exam(db, exam)
        out = exam_out(exam)
    await ctx.hub.to_console({"t": "exam", "exam": out})
    for seat_id in seat_ids:
        await deliver(ctx, seat_id)
    return out


@router.post("/extend")
async def extend_time(body: ExtendIn, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        exam = _exam(db)
        changed = extend(db, exam, body.seat_id, body.minutes)
        out = exam_out(exam)
    for seat_id, ends_at in changed:
        await ctx.hub.to_agent(seat_id, msg("time", ends_at=ends_at))
    if body.seat_id is None:
        await ctx.hub.to_console({"t": "exam", "exam": out})
    else:
        await push_event(ctx, add_event(ctx, body.seat_id, "teacher", {"text": f"+{body.minutes} min"}))
    return {"ok": True}


@router.post("/notice")
async def notice(body: TextIn, ctx: Ctx = Depends(require_teacher)):
    for seat_id in list(ctx.hub.agents):
        await ctx.hub.to_agent(seat_id, msg("notice", text=body.text))
    return {"ok": True}


@router.post("/seats/{seat_id}/warn")
async def warn(seat_id: int, body: TextIn, ctx: Ctx = Depends(require_teacher)):
    await ctx.hub.to_agent(seat_id, msg("notice", text=body.text))
    await push_event(ctx, add_event(ctx, seat_id, "teacher", {"text": "Warned"}))
    return {"ok": True}


@router.post("/seats/{seat_id}/force-submit")
async def force_submit(seat_id: int, ctx: Ctx = Depends(require_teacher)):
    ctx.ended_seats.add(seat_id)
    await ctx.hub.to_agent(seat_id, msg("end", reason="teacher"))
    await push_event(ctx, add_event(ctx, seat_id, "teacher", {"text": "Force submit"}))
    return {"ok": True}


@router.get("/results")
def get_results(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        return results(db, _exam(db))


@router.get("/results.csv")
def get_results_csv(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        body = results_csv(results(db, _exam(db)))
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="tide-results.csv"'})


class ReviewIn(BaseModel):
    status: str = Field(pattern="^(dismissed|confirmed|open)$")


@router.get("/catalog")
def catalog(ctx: Ctx = Depends(require_teacher)):
    return {"apps": list(APP_CATALOG), "presets": {k: list(v) for k, v in PRESETS.items()}}


@router.get("/seats/{seat_id}")
def seat_detail(seat_id: int, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        seat = db.get(Seat, seat_id)
        if seat is None:
            raise HTTPException(404, "No seat")
        flags = db.exec(select(Flag).where(Flag.seat_id == seat_id)).all()
        events = db.exec(select(Event).where(Event.seat_id == seat_id)).all()
        timeline = ([{"type": "flag", **flag_out(f, seat.seat_no)} for f in flags] +
                    [{"type": "event", **event_out(e)} for e in events])
        timeline.sort(key=lambda i: (i["ts"], i["type"] == "flag"), reverse=True)
        growth, current = [], {}
        snaps = db.exec(select(Snapshot).where(Snapshot.seat_id == seat_id).order_by(Snapshot.id)).all()
        for s in snaps:
            current[s.path] = s.line_count
            total = sum(current.values())
            if growth and growth[-1]["ts"] == s.ts:
                growth[-1]["lines"] = total
            else:
                growth.append({"ts": s.ts, "lines": total})
        return {"seat": seat_out(seat, open_flags(db, seat_id)), "timeline": timeline,
                "growth": growth, "files": [{"path": p, "lines": n} for p, n in current.items()]}


@router.patch("/flags/{flag_id}")
async def review(flag_id: int, body: ReviewIn, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        flag = db.get(Flag, flag_id)
        if flag is None:
            raise HTTPException(404, "No flag")
        flag.status = body.status
        flag.reviewed_at = clock.now()
        db.add(flag)
        db.commit()
        seat_id = flag.seat_id
        seat_no = db.get(Seat, seat_id).seat_no
        out = flag_out(flag, seat_no)
    await push_flag(ctx, flag_id)
    await push_seat(ctx, seat_id)
    return out


@router.get("/shots/{flag_id}")
def shot(flag_id: int, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        flag = db.get(Flag, flag_id)
    if flag is None or not flag.screenshot:
        raise HTTPException(404, "No screenshot")
    return FileResponse(ctx.settings.data_dir / "shots" / flag.screenshot, media_type="image/jpeg")


@router.get("/submissions/{seat_id}")
def submission_file(seat_id: int, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        sub = db.exec(select(Submission).where(Submission.seat_id == seat_id)
                      .order_by(Submission.id.desc())).first()
    if sub is None:
        raise HTTPException(404, "No submission")
    return FileResponse(ctx.settings.data_dir / "submissions" / sub.file_name,
                        media_type="application/zip", filename=sub.file_name)


SIM_EVENTS = {
    "ai_site": dict(kind="blocked_site", severity="critical", title="ChatGPT — closed", source="rule", action="close_tab"),
    "jev_ai": dict(kind="jev", severity="critical", title="poe.com — AI assistant", source="jev",
                   label="ai_assistant", confidence=0.96, action="close_tab"),
    "internet": dict(kind="internet", severity="critical", title="Internet via Wi-Fi", source="rule", action="overlay"),
    "old_code": dict(kind="old_code", severity="high", title="Old code reused · 82%", source="rule",
                     data={"source_path": "D:\\old\\dsa_lab5.cpp", "pct": 82}),
    "usb": dict(kind="usb", severity="high", title="USB drive inserted", source="rule"),
}


class SimIn(BaseModel):
    seat_no: int
    kind: str


@router.post("/simulate")
async def simulate(body: SimIn, ctx: Ctx = Depends(require_teacher)):
    if body.kind not in SIM_EVENTS:
        raise HTTPException(422, f"kind must be one of {sorted(SIM_EVENTS)}")
    with ctx.db() as db:
        exam = _exam(db)
        seat = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.seat_no == body.seat_no)).first()
    if seat is None:
        raise HTTPException(404, "No such seat")
    flag = await raise_flag(ctx, seat.id, **SIM_EVENTS[body.kind])
    return {"flag_id": flag.id}
