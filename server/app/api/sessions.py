import random
import string
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_teacher
from app.models.entities import Teacher, Assignment, Session as ExamSession, StudentInSession, Submission, Flag
from app.schemas.session import SessionCreate, SessionStatusUpdate, SessionTeacherResponse, StudentInSessionItem

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
            flag_count=flag_cnt
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
