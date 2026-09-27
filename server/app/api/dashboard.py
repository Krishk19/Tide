from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_teacher
from app.models.entities import (
    Teacher,
    Session as ExamSession,
    StudentInSession,
    Submission,
    Flag,
    CodeSnapshot
)

router = APIRouter(tags=["Classroom Health Triage Grid"])


def calculate_classroom_triage(
    db: Session,
    session_id: int,
    teacher_id: int
) -> dict[str, Any]:
    """
    Computes real-time 3-zone health triage classification for all students in a session:
    - Zone 1 (Green): On Track (Organic velocity, active, low risk)
    - Zone 2 (Yellow): Struggling / Idle (Needs pedagogical assistance)
    - Zone 3 (Red): High Suspicion (Proctoring security intervention)
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == teacher_id
    ).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or unauthorized"
        )

    students = db.query(StudentInSession).filter(
        StudentInSession.session_id == session.id
    ).order_by(StudentInSession.joined_at.asc()).all()

    now = datetime.now(timezone.utc)
    student_triage_list = []
    green_cnt = 0
    yellow_cnt = 0
    red_cnt = 0

    for st in students:
        sub = db.query(Submission).filter(Submission.student_session_id == st.id).first()
        code_text = (sub.code if sub and sub.code else "") or ""
        lines_cnt = len(code_text.splitlines()) if code_text else 0
        chars_cnt = len(code_text)
        is_sub = (sub.submitted_at is not None) if sub else False

        # Query telemetry flags
        flags_cnt = db.query(Flag).filter(Flag.student_session_id == st.id).count()
        has_correlated = db.query(Flag).filter(
            Flag.student_session_id == st.id,
            Flag.type == "correlated-cheat-attempt",
            Flag.status != "dismissed"
        ).first() is not None

        critical_flags = db.query(Flag).filter(
            Flag.student_session_id == st.id,
            Flag.severity.in_(["critical", "high"]),
            Flag.status != "dismissed"
        ).count()

        # Inactivity calculation
        st_joined = st.joined_at
        if st_joined.tzinfo is None:
            st_joined = st_joined.replace(tzinfo=timezone.utc)

        last_active = sub.last_autosaved_at if (sub and sub.last_autosaved_at) else st_joined
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        inactive_secs = max(0, int((now - last_active).total_seconds()))
        elapsed_secs = max(0, int((now - st_joined).total_seconds()))

        # Determine Zone & Diagnostic Reason
        risk = st.risk_score or 0
        zone = "green"
        reason = "Progressing normally"

        if st.is_frozen:
            zone = "red"
            red_cnt += 1
            reason = "EXAM FROZEN: Unauthorized external internet detected"
        elif risk >= 60 or has_correlated or critical_flags >= 2:
            zone = "red"
            red_cnt += 1
            if has_correlated:
                reason = "High-confidence correlation alert (blur + paste)"
            elif risk >= 60:
                reason = f"Elevated risk score ({risk}/100)"
            else:
                reason = f"{critical_flags} open high-severity security flags"
        elif not is_sub and elapsed_secs >= 600 and lines_cnt <= 2:
            zone = "yellow"
            yellow_cnt += 1
            reason = f"Inactive ({int(elapsed_secs / 60)}m elapsed with minimal code)"
        elif not is_sub and inactive_secs >= 720:
            zone = "yellow"
            yellow_cnt += 1
            reason = f"No autosave activity for {int(inactive_secs / 60)} minutes"
        elif not is_sub and sub and sub.test_results and sub.test_results.get("total_tests", 0) > 0 and sub.test_results.get("passed_tests", 0) == 0:
            zone = "yellow"
            yellow_cnt += 1
            reason = "Struggling with compiler or runtime errors"
        else:
            zone = "green"
            green_cnt += 1
            if is_sub:
                score = (sub.test_results or {}).get("score_percentage", 100)
                reason = f"Finalized & submitted (Score: {score}%)"
            else:
                reason = f"Active incremental velocity ({lines_cnt} lines)"

        student_triage_list.append({
            "id": st.id,
            "student_name": st.student_name,
            "student_identifier": st.student_identifier,
            "zone": zone,
            "zone_reason": reason,
            "risk_score": risk,
            "lines_count": lines_cnt,
            "chars_count": chars_cnt,
            "flag_count": flags_cnt,
            "is_submitted": is_sub,
            "is_frozen": bool(st.is_frozen),
            "extra_time_seconds": st.extra_time_seconds or 0,
            "inactive_seconds": inactive_secs,
            "last_autosaved_at": last_active.isoformat()
        })

    return {
        "session_id": session.id,
        "total_students": len(students),
        "counts": {
            "all": len(students),
            "green": green_cnt,
            "yellow": yellow_cnt,
            "red": red_cnt
        },
        "students": student_triage_list
    }


@router.get("/dashboard/triage")
def get_dashboard_triage(
    session_id: int = Query(...),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Returns the real-time 3-Zone Class Health Triage summary and student breakdown.
    Eliminates alert fatigue with instant Green/Yellow/Red categorisation.
    """
    return calculate_classroom_triage(db, session_id, current_teacher.id)


@router.get("/sessions/{session_id}/triage")
def get_session_triage(
    session_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    RESTful endpoint for session triage health grid.
    """
    return calculate_classroom_triage(db, session_id, current_teacher.id)
