import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_teacher
from app.models.entities import Teacher, Session as ExamSession, StudentInSession, Submission, Flag, Assignment
from app.api.telemetry import manager, record_flag_in_db
from app.services.executor import evaluate_submission
from app.services.heuristics import calculate_risk_score

router = APIRouter(prefix="/sessions", tags=["Remote Classroom Control"])


# --- Schemas ---
class BroadcastAnnouncementRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    type: str = Field("info", pattern="^(info|warning|urgent)$")


class ExtendTimeRequest(BaseModel):
    added_minutes: int = Field(5, ge=1, le=180)
    reason: Optional[str] = "Compensatory time granted by instructor"


class DirectWarningRequest(BaseModel):
    message: str = Field(
        "Warning from Instructor: Maintain exam focus and integrity.",
        min_length=1,
        max_length=500
    )


# --- Endpoints ---

@router.post("/{session_id}/broadcast")
async def broadcast_announcement(
    session_id: int,
    req: BroadcastAnnouncementRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Broadcasts a real-time announcement to all connected student kiosks in the session.
    Pushes via WebSocket so student editor focus is never interrupted.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    students = db.query(StudentInSession).filter(StudentInSession.session_id == session.id).all()
    student_ids = [s.id for s in students]

    now = datetime.now(timezone.utc)
    payload = {
        "event": "broadcast_announcement",
        "session_id": session.id,
        "message": req.message.strip(),
        "type": req.type,
        "ts": now.isoformat()
    }

    # Broadcast to all students in session
    await manager.broadcast_to_students(student_ids, payload)

    # Also notify teacher feed
    await manager.broadcast_to_teacher(current_teacher.id, {
        "event": "broadcast_sent",
        "session_id": session.id,
        "recipient_count": len(student_ids),
        "message": req.message.strip(),
        "type": req.type,
        "ts": now.isoformat()
    })

    return {
        "success": True,
        "session_id": session.id,
        "recipient_count": len(student_ids),
        "message": req.message.strip(),
        "type": req.type,
        "ts": now.isoformat()
    }


@router.post("/{session_id}/students/{student_id}/extend-time")
async def extend_student_time(
    session_id: int,
    student_id: int,
    req: ExtendTimeRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Grants compensatory extra time (e.g. +5, +10 mins) to a specific student whose PC rebooted or froze.
    Updates the database and pushes dynamic timer extension to the student kiosk via WebSocket.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    student = db.query(StudentInSession).filter(
        StudentInSession.id == student_id,
        StudentInSession.session_id == session.id
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in this session")

    # Increment extra time
    added_seconds = req.added_minutes * 60
    current_extra = student.extra_time_seconds or 0
    student.extra_time_seconds = current_extra + added_seconds
    db.commit()
    db.refresh(student)

    now = datetime.now(timezone.utc)
    # Log forensic flag in audit trail
    meta = {
        "added_minutes": req.added_minutes,
        "added_seconds": added_seconds,
        "total_extra_seconds": student.extra_time_seconds,
        "reason": req.reason,
        "granted_by": current_teacher.name or current_teacher.username
    }
    flag = Flag(
        student_session_id=student.id,
        type="extended-time",
        severity="info",
        flag_metadata=meta,
        ts=now,
        status="open"
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)

    # Push to student kiosk
    await manager.send_to_student(student.id, {
        "event": "extend_time",
        "added_minutes": req.added_minutes,
        "added_seconds": added_seconds,
        "total_extra_seconds": student.extra_time_seconds,
        "reason": req.reason
    })

    # Broadcast to teacher feed
    await manager.broadcast_to_teacher(current_teacher.id, {
        "event": "new_flag",
        "flag": {
            "id": flag.id,
            "student_session_id": student.id,
            "student_name": student.student_name,
            "student_identifier": student.student_identifier,
            "session_id": session.id,
            "type": "extended-time",
            "severity": "info",
            "metadata": meta,
            "ts": flag.ts.isoformat(),
            "status": "open",
            "risk_score": student.risk_score or 0
        }
    })

    return {
        "success": True,
        "student_id": student.id,
        "added_minutes": req.added_minutes,
        "total_extra_seconds": student.extra_time_seconds,
        "reason": req.reason
    }


@router.post("/{session_id}/students/{student_id}/warn")
async def warn_student(
    session_id: int,
    student_id: int,
    req: DirectWarningRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Pushes an official warning modal directly to the student's screen and logs an audit flag.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    student = db.query(StudentInSession).filter(
        StudentInSession.id == student_id,
        StudentInSession.session_id == session.id
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in this session")

    now = datetime.now(timezone.utc)
    meta = {
        "warning_message": req.message.strip(),
        "issued_by": current_teacher.name or current_teacher.username,
        "source": "remote_teacher_intervention"
    }

    flag = Flag(
        student_session_id=student.id,
        type="instructor-warning",
        severity="medium",
        flag_metadata=meta,
        ts=now,
        status="open"
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)

    # Push warning modal to student kiosk
    await manager.send_to_student(student.id, {
        "event": "direct_warning",
        "message": req.message.strip(),
        "sent_at": now.isoformat()
    })

    # Broadcast to teacher feed
    await manager.broadcast_to_teacher(current_teacher.id, {
        "event": "new_flag",
        "flag": {
            "id": flag.id,
            "student_session_id": student.id,
            "student_name": student.student_name,
            "student_identifier": student.student_identifier,
            "session_id": session.id,
            "type": "instructor-warning",
            "severity": "medium",
            "metadata": meta,
            "ts": flag.ts.isoformat(),
            "status": "open",
            "risk_score": student.risk_score or 0
        }
    })

    return {
        "success": True,
        "student_id": student.id,
        "message": req.message.strip(),
        "ts": now.isoformat()
    }


@router.post("/{session_id}/students/{student_id}/force-submit")
async def force_submit_student(
    session_id: int,
    student_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Remotely freezes student kiosk, executes sandbox grading on latest autosaved code,
    marks submission as finalized, and renders submitted score screen.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    student = db.query(StudentInSession).filter(
        StudentInSession.id == student_id,
        StudentInSession.session_id == session.id
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in this session")

    assignment: Assignment = session.assignment
    visible_tests = assignment.visible_test_cases or []
    hidden_tests = assignment.hidden_test_cases or []

    sub = db.query(Submission).filter(Submission.student_session_id == student.id).first()
    code_to_eval = (sub.code if sub and sub.code else assignment.starter_code) or ""
    language_to_eval = (sub.language if sub and sub.language else "python") or "python"

    # Evaluate visible tests
    vis_raw = evaluate_submission(language_to_eval, code_to_eval, visible_tests, timeout_seconds=3.0)
    passed_vis_count = sum(1 for r in vis_raw if r.get("passed"))

    # Evaluate hidden tests
    hid_raw = evaluate_submission(language_to_eval, code_to_eval, hidden_tests, timeout_seconds=3.0)
    passed_hid_count = sum(1 for r in hid_raw if r.get("passed"))

    total_tests = len(visible_tests) + len(hidden_tests)
    passed_total = passed_vis_count + passed_hid_count
    score_pct = round((passed_total / total_tests * 100.0), 2) if total_tests > 0 else 100.0

    now = datetime.now(timezone.utc)

    if not sub:
        sub = Submission(student_session_id=student.id)
        db.add(sub)

    sub.code = code_to_eval
    sub.language = language_to_eval
    sub.submitted_at = now
    sub.last_autosaved_at = now
    sub.test_results = {
        "total_tests": total_tests,
        "passed_tests": passed_total,
        "score_percentage": score_pct,
        "visible_passed": passed_vis_count,
        "visible_total": len(visible_tests),
        "hidden_passed": passed_hid_count,
        "hidden_total": len(hidden_tests),
        "force_submitted": True
    }
    db.commit()
    db.refresh(sub)

    # Log forensic flag
    flag = Flag(
        student_session_id=student.id,
        type="force-submitted",
        severity="high",
        flag_metadata={
            "reason": "Remotely submitted by instructor",
            "score_percentage": score_pct,
            "passed_tests": passed_total,
            "total_tests": total_tests
        },
        ts=now,
        status="open"
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)

    result_payload = {
        "score_percentage": score_pct,
        "passed_tests": passed_total,
        "total_tests": total_tests,
        "force_submitted": True
    }

    # Push to student kiosk to immediately lock screen and show submitted view
    await manager.send_to_student(student.id, {
        "event": "force_submit",
        "reason": "Examination has been remotely concluded and finalized by instructor.",
        "result": result_payload
    })

    # Broadcast to teacher feed
    await manager.broadcast_to_teacher(current_teacher.id, {
        "event": "student_submitted",
        "student_session_id": student.id,
        "student_name": student.student_name,
        "student_identifier": student.student_identifier,
        "session_id": session.id,
        "score_percentage": score_pct
    })

    return {
        "success": True,
        "student_id": student.id,
        "is_submitted": True,
        "score_percentage": score_pct,
        "passed_tests": passed_total,
        "total_tests": total_tests
    }


@router.get("/{session_id}/students/{student_id}/playback")
def get_playback_history(
    session_id: int,
    student_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Returns full chronological keyframe snapshots and timeline events
    for the interactive code growth scrubber in the teacher command center.
    """
    from app.services.playback import get_student_playback_data
    return get_student_playback_data(
        db=db,
        session_id=session_id,
        student_id=student_id,
        teacher_id=current_teacher.id
    )


@router.post("/{session_id}/students/{student_id}/unfreeze")
async def unfreeze_student_exam(
    session_id: int,
    student_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Evaluator remotely unlocks and unfreezes a student whose exam was frozen
    due to unauthorized external internet detection or manual lock.
    Dismisses internet-detected flags, recalculates risk score, and pushes unfreeze via WebSocket.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    student = db.query(StudentInSession).filter(
        StudentInSession.id == student_id,
        StudentInSession.session_id == session.id
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in this session")

    student.is_frozen = False
    now = datetime.now(timezone.utc)

    # Dismiss any open internet-detected flags so risk score reflects evaluator resolution
    internet_flags = db.query(Flag).filter(
        Flag.student_session_id == student.id,
        Flag.type == "internet-detected",
        Flag.status == "open"
    ).all()
    for f in internet_flags:
        f.status = "dismissed"
        f.notes = f"Unfrozen by evaluator: {current_teacher.name or current_teacher.username}"
        f.reviewed_by = current_teacher.id
        f.reviewed_at = now

    # Log forensic unfreeze flag in audit trail
    unfreeze_flag = Flag(
        student_session_id=student.id,
        type="exam-unfrozen",
        severity="info",
        flag_metadata={
            "action": "unfreeze",
            "unfrozen_by": current_teacher.name or current_teacher.username,
            "reason": "Evaluator verified network isolation and unlocked exam."
        },
        ts=now,
        status="dismissed",
        reviewed_by=current_teacher.id,
        reviewed_at=now
    )
    db.add(unfreeze_flag)
    db.commit()
    db.refresh(student)

    # Recalculate dynamic risk score
    new_risk = calculate_risk_score(db, student.id)

    # Push unfreeze command to student kiosk via WebSocket
    await manager.send_to_student(student.id, {
        "event": "unfreeze_exam",
        "reason": "Exam unlocked by evaluator",
        "unfrozen_at": now.isoformat()
    })

    # Broadcast to teacher feed
    await manager.broadcast_to_teacher(current_teacher.id, {
        "event": "student_unfrozen",
        "session_id": session.id,
        "student_session_id": student.id,
        "student_name": student.student_name,
        "student_identifier": student.student_identifier,
        "is_frozen": False,
        "risk_score": new_risk
    })

    return {
        "success": True,
        "session_id": session.id,
        "student_id": student.id,
        "is_frozen": False,
        "risk_score": new_risk,
        "message": f"Exam successfully unfreezed for {student.student_name}"
    }


@router.post("/{session_id}/students/{student_id}/freeze")
async def freeze_student_exam(
    session_id: int,
    student_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Evaluator manually freezes/locks a student exam.
    Pushes freeze command to student kiosk via WebSocket.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    student = db.query(StudentInSession).filter(
        StudentInSession.id == student_id,
        StudentInSession.session_id == session.id
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in this session")

    student.is_frozen = True
    now = datetime.now(timezone.utc)

    freeze_flag = Flag(
        student_session_id=student.id,
        type="exam-frozen",
        severity="high",
        flag_metadata={
            "action": "freeze",
            "frozen_by": current_teacher.name or current_teacher.username,
            "reason": "Exam manually frozen by instructor."
        },
        ts=now,
        status="open"
    )
    db.add(freeze_flag)
    db.commit()
    db.refresh(student)

    new_risk = calculate_risk_score(db, student.id)

    # Push freeze command to student kiosk via WebSocket
    await manager.send_to_student(student.id, {
        "event": "freeze_exam",
        "reason": "Exam locked by evaluator.",
        "frozen_at": now.isoformat()
    })

    # Broadcast to teacher feed
    await manager.broadcast_to_teacher(current_teacher.id, {
        "event": "student_frozen",
        "session_id": session.id,
        "student_session_id": student.id,
        "student_name": student.student_name,
        "student_identifier": student.student_identifier,
        "is_frozen": True,
        "risk_score": new_risk
    })

    return {
        "success": True,
        "session_id": session.id,
        "student_id": student.id,
        "is_frozen": True,
        "risk_score": new_risk,
        "message": f"Exam frozen for {student.student_name}"
    }


