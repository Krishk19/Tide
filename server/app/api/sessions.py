from datetime import datetime, timezone
import random
import string
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_teacher
from app.models.entities import (
    Teacher,
    Assignment,
    Session as ExamSession,
    StudentInSession,
    Submission,
    Flag,
)
from app.schemas.session import (
    SessionCreate,
    SessionStatusUpdate,
    SessionTeacherResponse,
    StudentInSessionItem,
    StudentJoinRequest,
    StudentJoinResponse,
)

router = APIRouter(prefix="/sessions", tags=["Sessions"])

def generate_access_code(db: Session, length: int = 6) -> str:
    """Generates a random alphanumeric code that does not collide with active or scheduled sessions."""
    characters = string.ascii_uppercase + "23456789"  # exclude 0, 1, O, I for clarity
    for _ in range(50):
        code = "".join(random.choices(characters, k=length))
        collision = db.query(ExamSession).filter(
            ExamSession.access_code == code,
            ExamSession.status.in_(["scheduled", "active"])
        ).first()
        if not collision:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to generate unique access code. Please try again."
    )

@router.post("", response_model=SessionTeacherResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    req: SessionCreate,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Creates a day-of assessment session referencing an assignment.
    Generates a 6-character access code and sets start_time.
    """
    # Verify assignment belongs to current teacher
    assignment = db.query(Assignment).filter(
        Assignment.id == req.assignment_id,
        Assignment.teacher_id == current_teacher.id
    ).first()
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found or does not belong to you"
        )

    code = generate_access_code(db)
    session = ExamSession(
        teacher_id=current_teacher.id,
        assignment_id=assignment.id,
        access_code=code,
        start_time=req.start_time,
        status="scheduled"
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "id": session.id,
        "teacher_id": session.teacher_id,
        "assignment_id": session.assignment_id,
        "assignment_title": assignment.title,
        "access_code": session.access_code,
        "start_time": session.start_time,
        "status": session.status,
        "student_count": 0,
        "students": []
    }

@router.get("", response_model=list[SessionTeacherResponse])
def list_sessions(
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Lists sessions owned by the authenticated teacher.
    Derives scope strictly from JWT teacher_id.
    """
    sessions = db.query(ExamSession).filter(
        ExamSession.teacher_id == current_teacher.id
    ).order_by(ExamSession.start_time.desc()).all()

    result = []
    for s in sessions:
        student_count = db.query(StudentInSession).filter(StudentInSession.session_id == s.id).count()
        result.append({
            "id": s.id,
            "teacher_id": s.teacher_id,
            "assignment_id": s.assignment_id,
            "assignment_title": s.assignment.title if s.assignment else "Untitled",
            "access_code": s.access_code,
            "start_time": s.start_time,
            "status": s.status,
            "student_count": student_count
        })
    return result

@router.get("/{session_id}", response_model=SessionTeacherResponse)
def get_session(
    session_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """Fetches details for a specific session owned by the authenticated teacher."""
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    students = db.query(StudentInSession).filter(StudentInSession.session_id == session.id).all()
    student_items = []
    for st in students:
        sub = db.query(Submission).filter(Submission.student_session_id == st.id).first()
        flag_cnt = db.query(Flag).filter(Flag.student_session_id == st.id).count()
        student_items.append(StudentInSessionItem(
            id=st.id,
            student_name=st.student_name,
            student_identifier=st.student_identifier,
            joined_at=st.joined_at,
            last_autosaved_at=sub.last_autosaved_at if sub else None,
            submitted_at=sub.submitted_at if sub else None,
            flag_count=flag_cnt,
            risk_score=st.risk_score or 0,
            extra_time_seconds=st.extra_time_seconds or 0
        ))

    return {
        "id": session.id,
        "teacher_id": session.teacher_id,
        "assignment_id": session.assignment_id,
        "assignment_title": session.assignment.title if session.assignment else "Untitled",
        "access_code": session.access_code,
        "start_time": session.start_time,
        "status": session.status,
        "student_count": len(student_items),
        "students": student_items
    }

@router.patch("/{session_id}/status", response_model=SessionTeacherResponse)
def update_session_status(
    session_id: int,
    req: SessionStatusUpdate,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """Updates session status (e.g. active, closed)."""
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session.status = req.status
    db.commit()
    db.refresh(session)
    return get_session(session_id, current_teacher, db)

@router.post("/join", response_model=StudentJoinResponse)
async def join_session(req: StudentJoinRequest, db: Session = Depends(get_db)):
    """
    Student joins an exam session using a 6-character access code.
    If the student already joined previously with the same identifier:
    - Verifies they haven't submitted yet.
    - Calculates the exact downtime gap Delta-t from their last disconnect/autosave.
    - Restores their exact autosaved code from SQLite.
    - Logs a forensic 'reconnected' flag to the teacher dashboard.
    """
    clean_code = req.access_code.strip().upper()
    session = db.query(ExamSession).filter(
        ExamSession.access_code == clean_code,
        ExamSession.status.in_(["scheduled", "active"])
    ).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired access code"
        )

    # Check for existing student in session (reconnect support)
    student = db.query(StudentInSession).filter(
        StudentInSession.session_id == session.id,
        StudentInSession.student_identifier == req.student_identifier.strip()
    ).first()

    now = datetime.now(timezone.utc)

    if student:
        # Check if student has already finalized their submission
        sub = db.query(Submission).filter(Submission.student_session_id == student.id).first()
        if sub and sub.submitted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assessment already finalized and submitted"
            )

        # Calculate exact downtime gap Delta-t
        last_disconnect = db.query(Flag).filter(
            Flag.student_session_id == student.id,
            Flag.type == "connection-lost"
        ).order_by(Flag.ts.desc()).first()

        if last_disconnect and last_disconnect.ts:
            t_disc = last_disconnect.ts
            if t_disc.tzinfo is None:
                t_disc = t_disc.replace(tzinfo=timezone.utc)
            delta_seconds = max(0, int((now - t_disc).total_seconds()))
        elif sub and sub.last_autosaved_at:
            t_save = sub.last_autosaved_at
            if t_save.tzinfo is None:
                t_save = t_save.replace(tzinfo=timezone.utc)
            delta_seconds = max(0, int((now - t_save).total_seconds()))
        else:
            delta_seconds = 0

        restored_code = (sub.code if sub else "") or ""
        line_count = len(restored_code.splitlines()) if restored_code else 0
        char_count = len(restored_code)

        # Log forensic reconnected flag
        from app.api.telemetry import record_flag_in_db, manager
        reconnect_meta = {
            "downtime_seconds": delta_seconds,
            "restored_line_count": line_count,
            "restored_char_count": char_count,
            "source": "rejoin_flow",
            "reason": f"Student reconnected after {delta_seconds}s downtime. Restored {line_count} lines of code."
        }
        flag, corr_flag, teacher_id, risk_score = record_flag_in_db(
            db=db,
            student_session_id=student.id,
            flag_type="reconnected",
            metadata=reconnect_meta,
            ts=now,
            severity="info"
        )

        if flag:
            try:
                await manager.broadcast_to_teacher(teacher_id, {
                    "event": "new_flag",
                    "flag": {
                        "id": flag.id,
                        "student_session_id": student.id,
                        "student_name": student.student_name,
                        "student_identifier": student.student_identifier,
                        "session_id": session.id,
                        "type": "reconnected",
                        "severity": flag.severity,
                        "metadata": reconnect_meta,
                        "ts": flag.ts.isoformat(),
                        "status": "open",
                        "risk_score": risk_score
                    }
                })
            except Exception:
                pass

        return {
            "student_session_id": student.id,
            "session_id": session.id,
            "student_name": student.student_name,
            "student_identifier": student.student_identifier,
            "is_reconnect": True,
            "downtime_seconds": delta_seconds,
            "last_saved_at": sub.last_autosaved_at if sub else None
        }

    # Brand new student join
    student = StudentInSession(
        session_id=session.id,
        student_name=req.student_name.strip(),
        student_identifier=req.student_identifier.strip(),
        risk_score=0
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    # Initialize starter submission record
    assignment = session.assignment
    default_lang = "python"
    if assignment and assignment.language_set:
        langs = [l.strip().lower() for l in assignment.language_set.split(",")]
        if langs:
            default_lang = langs[0]

    sub = Submission(
        student_session_id=student.id,
        code=assignment.starter_code if assignment else "",
        language=default_lang,
        test_results=None,
        last_autosaved_at=now
    )
    db.add(sub)
    db.commit()

    return {
        "student_session_id": student.id,
        "session_id": session.id,
        "student_name": student.student_name,
        "student_identifier": student.student_identifier,
        "is_reconnect": False,
        "downtime_seconds": 0,
        "last_saved_at": now
    }
