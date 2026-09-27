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
from app.services.heuristics import buffer_event, evaluate_correlation, calculate_risk_score

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

    async def send_to_student(self, student_session_id: int, message: dict[str, Any]):
        sockets = self.student_sockets.get(student_session_id, [])
        dead_sockets = []
        for ws in sockets:
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            self.disconnect_student(student_session_id, ws)

    async def broadcast_to_students(self, student_session_ids: list[int], message: dict[str, Any]):
        for sid in student_session_ids:
            await self.send_to_student(sid, message)

manager = ConnectionManager()

def record_flag_in_db(
    db: Session,
    student_session_id: int,
    flag_type: str,
    metadata: Optional[dict[str, Any]] = None,
    ts: Optional[datetime] = None,
    severity: Optional[str] = None
) -> tuple[Optional[Flag], Optional[Flag], int, int]:
    """
    Persists a telemetry event to SQLite, checks for sliding-window correlations,
    computes live risk score, and determines the owning teacher_id.
    Suppresses flags if the student has already completed and submitted their assessment.
    Returns: (primary_flag, correlated_flag, teacher_id, risk_score)
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
        return None, None, teacher_id, student.risk_score or 0

    event_time = ts or datetime.now(timezone.utc)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)

    # Deduplicate rapid focus-lost, focus-regained, or fullscreen-exit signals within 3 seconds
    if flag_type in ("focus-lost", "focus-regained", "fullscreen-exit"):
        last_same_flag = db.query(Flag).filter(
            Flag.student_session_id == student_session_id,
            Flag.type == flag_type
        ).order_by(Flag.ts.desc()).first()
        if last_same_flag and last_same_flag.ts:
            l_ts = last_same_flag.ts
            if l_ts.tzinfo is None:
                l_ts = l_ts.replace(tzinfo=timezone.utc)
            if abs((event_time - l_ts).total_seconds()) < 3.0:
                return None, None, teacher_id, student.risk_score or 0

    # Determine default severity
    if not severity:
        if flag_type in ("correlated-cheat-attempt", "internet-detected"):
            severity = "critical"
        elif flag_type in ("fullscreen-exit", "connection-lost"):
            severity = "high"
        elif flag_type == "paste":
            severity = "high" if (metadata or {}).get("length", 0) >= 50 else "medium"
        elif flag_type == "focus-lost":
            severity = "medium"
        else:
            severity = "info"

    if flag_type == "internet-detected":
        student.is_frozen = True

    flag = Flag(
        student_session_id=student_session_id,
        type=flag_type,
        severity=severity,
        flag_metadata=metadata or {},
        ts=event_time,
        status="open"
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)

    # 1. In-memory sliding window buffer
    buffer_event(student_session_id, flag_type, event_time, metadata)

    # 2. Evaluate correlation
    corr_flag = None
    corr_data = evaluate_correlation(student_session_id, flag_type, event_time, metadata)
    if corr_data:
        corr_flag = Flag(
            student_session_id=student_session_id,
            type=corr_data["type"],
            severity=corr_data.get("severity", "critical"),
            flag_metadata=corr_data.get("metadata", {}),
            ts=event_time,
            status="open"
        )
        db.add(corr_flag)
        db.commit()
        db.refresh(corr_flag)

    # 3. Dynamic Risk Score Calculation
    risk_score = calculate_risk_score(db, student_session_id)

    return flag, corr_flag, teacher_id, risk_score

@router.post("/api/telemetry/event", response_model=FlagResponse)
async def post_telemetry_event(req: TelemetryEvent, db: Session = Depends(get_db)):
    """
    HTTP endpoint to ingest telemetry flags from student kiosk/browser.
    Saves to database and live-broadcasts to teacher WebSocket.
    """
    try:
        flag, corr_flag, teacher_id, risk_score = record_flag_in_db(
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
            severity="info",
            metadata={"status": "ignored_post_submission"},
            ts=req.ts or datetime.now(timezone.utc),
            status="dismissed",
            risk_score=student.risk_score if student else 0
        )

    # Broadcast primary flag
    payload = {
        "event": "new_flag",
        "flag": {
            "id": flag.id,
            "student_session_id": flag.student_session_id,
            "student_name": student.student_name if student else "Unknown",
            "student_identifier": student.student_identifier if student else "Unknown",
            "session_id": student.session_id if student else None,
            "type": flag.type,
            "severity": flag.severity,
            "metadata": flag.flag_metadata,
            "ts": flag.ts.isoformat(),
            "status": flag.status,
            "risk_score": risk_score
        }
    }
    await manager.broadcast_to_teacher(teacher_id, payload)

    # Broadcast synthesized correlated flag if triggered
    if corr_flag:
        corr_payload = {
            "event": "new_flag",
            "flag": {
                "id": corr_flag.id,
                "student_session_id": corr_flag.student_session_id,
                "student_name": student.student_name if student else "Unknown",
                "student_identifier": student.student_identifier if student else "Unknown",
                "session_id": student.session_id if student else None,
                "type": corr_flag.type,
                "severity": corr_flag.severity,
                "metadata": corr_flag.flag_metadata,
                "ts": corr_flag.ts.isoformat(),
                "status": corr_flag.status,
                "risk_score": risk_score
            }
        }
        await manager.broadcast_to_teacher(teacher_id, corr_payload)

    # Broadcast risk score update to refresh teacher roster
    await manager.broadcast_to_teacher(teacher_id, {
        "event": "risk_score_update",
        "student_session_id": student.id if student else req.student_session_id,
        "risk_score": risk_score
    })

    return FlagResponse(
        id=flag.id,
        student_session_id=flag.student_session_id,
        student_name=student.student_name if student else None,
        student_identifier=student.student_identifier if student else None,
        session_id=student.session_id if student else None,
        type=flag.type,
        severity=flag.severity,
        metadata=flag.flag_metadata,
        ts=flag.ts,
        status=flag.status,
        risk_score=risk_score
    )

@router.websocket("/ws/student/{student_session_id}")
async def websocket_student_telemetry(websocket: WebSocket, student_session_id: int):
    """
    Real-time telemetry stream from student kiosk.
    Auto-detects disconnects and broadcasts 'connection-lost' flag.
    """
    await manager.connect_student(student_session_id, websocket)

    # Broadcast connection/reconnection (de-duplicated if join_session recently logged one)
    db = SessionLocal()
    try:
        recent_reconnect = db.query(Flag).filter(
            Flag.student_session_id == student_session_id,
            Flag.type == "reconnected"
        ).order_by(Flag.ts.desc()).first()

        now = datetime.now(timezone.utc)
        skip_ws_flag = False
        if recent_reconnect and recent_reconnect.ts:
            r_ts = recent_reconnect.ts
            if r_ts.tzinfo is None:
                r_ts = r_ts.replace(tzinfo=timezone.utc)
            if (now - r_ts).total_seconds() < 8.0:
                skip_ws_flag = True

        if not skip_ws_flag:
            flag, corr_flag, teacher_id, risk_score = record_flag_in_db(
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
                        "severity": flag.severity,
                        "metadata": flag.flag_metadata,
                        "ts": flag.ts.isoformat(),
                        "status": "open",
                        "risk_score": risk_score
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
                flag, corr_flag, teacher_id, risk_score = record_flag_in_db(
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
                            "severity": flag.severity,
                            "metadata": flag.flag_metadata,
                            "ts": flag.ts.isoformat(),
                            "status": "open",
                            "risk_score": risk_score
                        }
                    })

                if corr_flag:
                    student = db.query(StudentInSession).filter(StudentInSession.id == student_session_id).first()
                    await manager.broadcast_to_teacher(teacher_id, {
                        "event": "new_flag",
                        "flag": {
                            "id": corr_flag.id,
                            "student_session_id": student_session_id,
                            "student_name": student.student_name if student else "Unknown",
                            "student_identifier": student.student_identifier if student else "Unknown",
                            "session_id": student.session_id if student else None,
                            "type": corr_flag.type,
                            "severity": corr_flag.severity,
                            "metadata": corr_flag.flag_metadata,
                            "ts": corr_flag.ts.isoformat(),
                            "status": "open",
                            "risk_score": risk_score
                        }
                    })

                if flag:
                    await manager.broadcast_to_teacher(teacher_id, {
                        "event": "risk_score_update",
                        "student_session_id": student_session_id,
                        "risk_score": risk_score
                    })
            finally:
                db.close()

    except WebSocketDisconnect:
        manager.disconnect_student(student_session_id, websocket)
        # Log connection-lost on abrupt disconnect (only if not already submitted)
        db = SessionLocal()
        try:
            flag, corr_flag, teacher_id, risk_score = record_flag_in_db(
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
                        "severity": flag.severity,
                        "metadata": flag.flag_metadata,
                        "ts": flag.ts.isoformat(),
                        "status": "open",
                        "risk_score": risk_score
                    }
                })
                await manager.broadcast_to_teacher(teacher_id, {
                    "event": "risk_score_update",
                    "student_session_id": student_session_id,
                    "risk_score": risk_score
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
            severity=f.severity,
            metadata=f.flag_metadata,
            ts=f.ts,
            status=f.status,
            notes=f.notes,
            reviewed_by=f.reviewed_by,
            reviewed_at=f.reviewed_at,
            risk_score=st.risk_score or 0
        ))
    return flags

@router.patch("/api/dashboard/flags/{flag_id}", response_model=FlagResponse)
async def update_flag_status(
    flag_id: int,
    req: FlagStatusUpdate,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Non-destructive flag review: marks flag as 'dismissed' or 'escalated'
    along with reviewer ID, timestamp, and optional notes.
    Recalculates risk score to reward false-positive dismissal.
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
    if req.notes is not None:
        flag.notes = req.notes
    flag.reviewed_by = current_teacher.id
    flag.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(flag)

    # Recalculate dynamic risk score upon review
    new_risk = calculate_risk_score(db, flag.student_session_id)
    await manager.broadcast_to_teacher(current_teacher.id, {
        "event": "risk_score_update",
        "student_session_id": st.id,
        "risk_score": new_risk
    })

    return FlagResponse(
        id=flag.id,
        student_session_id=flag.student_session_id,
        student_name=st.student_name,
        student_identifier=st.student_identifier,
        session_id=sess.id,
        type=flag.type,
        severity=flag.severity,
        metadata=flag.flag_metadata,
        ts=flag.ts,
        status=flag.status,
        notes=flag.notes,
        reviewed_by=flag.reviewed_by,
        reviewed_at=flag.reviewed_at,
        risk_score=new_risk
    )
