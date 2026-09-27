import json
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, status, Query
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.core.security import get_current_teacher
from app.models.entities import Teacher, Flag, StudentInSession, Session as ExamSession, Submission
from app.schemas.telemetry import TelemetryEvent, FlagResponse, FlagStatusUpdate

router = APIRouter(tags=["Telemetry & Flags"])

# In-memory connection manager for WebSocket streaming
class ConnectionManager:
    def __init__(self):
        # teacher_id -> list[WebSocket]
        self.teacher_sockets: dict[int, list[WebSocket]] = {}
        # student_session_id -> list[WebSocket]
        self.student_sockets: dict[int, list[WebSocket]] = {}

    async def connect_teacher(self, teacher_id: int, websocket: WebSocket):
        await websocket.accept()
        if teacher_id not in self.teacher_sockets:
            self.teacher_sockets[teacher_id] = []
        self.teacher_sockets[teacher_id].append(websocket)

    def disconnect_teacher(self, teacher_id: int, websocket: WebSocket):
        if teacher_id in self.teacher_sockets:
            self.teacher_sockets[teacher_id] = [ws for ws in self.teacher_sockets[teacher_id] if ws != websocket]

    async def connect_student(self, student_session_id: int, websocket: WebSocket):
        await websocket.accept()
        if student_session_id not in self.student_sockets:
            self.student_sockets[student_session_id] = []
        self.student_sockets[student_session_id].append(websocket)

    def disconnect_student(self, student_session_id: int, websocket: WebSocket):
        if student_session_id in self.student_sockets:
            self.student_sockets[student_session_id] = [ws for ws in self.student_sockets[student_session_id] if ws != websocket]

    async def broadcast_to_teacher(self, teacher_id: int, message: dict[str, Any]):
        sockets = self.teacher_sockets.get(teacher_id, [])
        dead_sockets = []
        for ws in sockets:
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            self.disconnect_teacher(teacher_id, ws)

manager = ConnectionManager()

def record_flag_in_db(
    db: Session,
    student_session_id: int,
    flag_type: str,
    metadata: Optional[dict[str, Any]] = None,
    ts: Optional[datetime] = None
) -> tuple[Optional[Flag], int]:
    """
    Persists a telemetry event to SQLite and determines the owning teacher_id.
    Suppresses flags if the student has already completed and submitted their assessment.
    """
    student = db.query(StudentInSession).filter(StudentInSession.id == student_session_id).first()
    if not student:
        raise ValueError(f"Student session {student_session_id} not found")

    session: ExamSession = student.session
    teacher_id = session.teacher_id

    # Check if student has already submitted their assessment
    sub = db.query(Submission).filter(Submission.student_session_id == student_session_id).first()
    if sub and sub.submitted_at is not None:
        # Submission is finalized: suppress post-submission flags (disconnects, blur, window exit)
        return None, teacher_id

    event_time = ts or datetime.now(timezone.utc)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)

    flag = Flag(
        student_session_id=student_session_id,
        type=flag_type,
        flag_metadata=metadata or {},
        ts=event_time,
        status="open"
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return flag, teacher_id

@router.post("/api/telemetry/event", response_model=FlagResponse)
async def post_telemetry_event(req: TelemetryEvent, db: Session = Depends(get_db)):
    """
    HTTP endpoint to ingest telemetry flags from student kiosk/browser.
    Saves to database and live-broadcasts to teacher WebSocket.
    """
    try:
        flag, teacher_id = record_flag_in_db(
            db,
            student_session_id=req.student_session_id,
            flag_type=req.type,
            metadata=req.metadata,
            ts=req.ts
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    student = db.query(StudentInSession).filter(StudentInSession.id == req.student_session_id).first()

    if not flag:
        # Suppressed post-submission
        return FlagResponse(
            id=0,
            student_session_id=req.student_session_id,
            student_name=student.student_name if student else None,
            student_identifier=student.student_identifier if student else None,
            session_id=student.session_id if student else None,
            type=req.type,
            metadata={"status": "ignored_post_submission"},
            ts=req.ts or datetime.now(timezone.utc),
            status="dismissed"
        )

    payload = {
        "event": "new_flag",
        "flag": {
            "id": flag.id,
            "student_session_id": flag.student_session_id,
            "student_name": student.student_name if student else "Unknown",
            "student_identifier": student.student_identifier if student else "Unknown",
            "session_id": student.session_id if student else None,
            "type": flag.type,
            "metadata": flag.flag_metadata,
            "ts": flag.ts.isoformat(),
            "status": flag.status
        }
    }
    await manager.broadcast_to_teacher(teacher_id, payload)

    return FlagResponse(
        id=flag.id,
        student_session_id=flag.student_session_id,
        student_name=student.student_name if student else None,
        student_identifier=student.student_identifier if student else None,
        session_id=student.session_id if student else None,
        type=flag.type,
        metadata=flag.flag_metadata,
        ts=flag.ts,
        status=flag.status
    )

@router.websocket("/ws/student/{student_session_id}")
async def websocket_student_telemetry(websocket: WebSocket, student_session_id: int):
    """
    Real-time telemetry stream from student kiosk.
    Auto-detects disconnects and broadcasts 'connection-lost' flag.
    """
    await manager.connect_student(student_session_id, websocket)

    # Broadcast connection/reconnection
    db = SessionLocal()
    try:
        flag, teacher_id = record_flag_in_db(
            db,
            student_session_id=student_session_id,
            flag_type="reconnected",
            metadata={"source": "websocket_connect"}
        )
        if flag:
            student = db.query(StudentInSession).filter(StudentInSession.id == student_session_id).first()
            await manager.broadcast_to_teacher(teacher_id, {
                "event": "new_flag",
                "flag": {
                    "id": flag.id,
                    "student_session_id": student_session_id,
                    "student_name": student.student_name if student else "Unknown",
                    "student_identifier": student.student_identifier if student else "Unknown",
                    "session_id": student.session_id if student else None,
                    "type": "reconnected",
                    "metadata": flag.flag_metadata,
                    "ts": flag.ts.isoformat(),
                    "status": "open"
                }
            })
    except Exception:
        pass
    finally:
        db.close()

    try:
        while True:
            text = await websocket.receive_text()
            data = json.loads(text)
            event_type = data.get("type", "unknown")
            metadata = data.get("metadata", {})

            db = SessionLocal()
            try:
                flag, teacher_id = record_flag_in_db(
                    db,
                    student_session_id=student_session_id,
                    flag_type=event_type,
                    metadata=metadata
                )
                if flag:
                    student = db.query(StudentInSession).filter(StudentInSession.id == student_session_id).first()
                    await manager.broadcast_to_teacher(teacher_id, {
                        "event": "new_flag",
                        "flag": {
                            "id": flag.id,
                            "student_session_id": student_session_id,
                            "student_name": student.student_name if student else "Unknown",
                            "student_identifier": student.student_identifier if student else "Unknown",
                            "session_id": student.session_id if student else None,
                            "type": flag.type,
                            "metadata": flag.flag_metadata,
                            "ts": flag.ts.isoformat(),
                            "status": "open"
                        }
                    })
            finally:
                db.close()

    except WebSocketDisconnect:
        manager.disconnect_student(student_session_id, websocket)
        # Log connection-lost on abrupt disconnect (only if not already submitted)
        db = SessionLocal()
        try:
            flag, teacher_id = record_flag_in_db(
                db,
                student_session_id=student_session_id,
                flag_type="connection-lost",
                metadata={"reason": "abrupt_socket_close"}
            )
            if flag:
                student = db.query(StudentInSession).filter(StudentInSession.id == student_session_id).first()
                await manager.broadcast_to_teacher(teacher_id, {
                    "event": "new_flag",
                    "flag": {
                        "id": flag.id,
                        "student_session_id": student_session_id,
                        "student_name": student.student_name if student else "Unknown",
                        "student_identifier": student.student_identifier if student else "Unknown",
                        "session_id": student.session_id if student else None,
                        "type": "connection-lost",
                        "metadata": flag.flag_metadata,
                        "ts": flag.ts.isoformat(),
                        "status": "open"
                    }
                })
        except Exception:
            pass
        finally:
            db.close()

@router.websocket("/ws/teacher")
async def websocket_teacher_feed(websocket: WebSocket, token: Optional[str] = Query(None)):
    """
    Live streaming feed of behavioral proctoring flags for the authenticated instructor.
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        teacher_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect_teacher(teacher_id, websocket)
    try:
        while True:
            # Keep socket open and receive any ping/acknowledgements
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_teacher(teacher_id, websocket)

@router.get("/api/dashboard/flags", response_model=list[FlagResponse])
def get_teacher_flags(
    session_id: Optional[int] = None,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Returns list of flags strictly scoped to sessions owned by the authenticated teacher.
    Guarantees structural multi-teacher isolation.
    """
    query = (
        db.query(Flag, StudentInSession, ExamSession)
        .join(StudentInSession, Flag.student_session_id == StudentInSession.id)
        .join(ExamSession, StudentInSession.session_id == ExamSession.id)
        .filter(ExamSession.teacher_id == current_teacher.id)
    )

    if session_id:
        query = query.filter(ExamSession.id == session_id)

    results = query.order_by(Flag.ts.desc()).limit(100).all()

    flags = []
    for f, st, sess in results:
        flags.append(FlagResponse(
            id=f.id,
            student_session_id=f.student_session_id,
            student_name=st.student_name,
            student_identifier=st.student_identifier,
            session_id=sess.id,
            type=f.type,
            metadata=f.flag_metadata,
            ts=f.ts,
            status=f.status,
            reviewed_by=f.reviewed_by,
            reviewed_at=f.reviewed_at
        ))
    return flags

@router.patch("/api/dashboard/flags/{flag_id}", response_model=FlagResponse)
def update_flag_status(
    flag_id: int,
    req: FlagStatusUpdate,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Non-destructive flag review: marks flag as 'dismissed' or 'escalated'
    along with reviewer ID and timestamp. Preserves complete audit trail.
    """
    item = (
        db.query(Flag, StudentInSession, ExamSession)
        .join(StudentInSession, Flag.student_session_id == StudentInSession.id)
        .join(ExamSession, StudentInSession.session_id == ExamSession.id)
        .filter(Flag.id == flag_id, ExamSession.teacher_id == current_teacher.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Flag not found or unauthorized")

    flag, st, sess = item
    flag.status = req.status
    flag.reviewed_by = current_teacher.id
    flag.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(flag)

    return FlagResponse(
        id=flag.id,
        student_session_id=flag.student_session_id,
        student_name=st.student_name,
        student_identifier=st.student_identifier,
        session_id=sess.id,
        type=flag.type,
        metadata=flag.flag_metadata,
        ts=flag.ts,
        status=flag.status,
        reviewed_by=flag.reviewed_by,
        reviewed_at=flag.reviewed_at
    )
