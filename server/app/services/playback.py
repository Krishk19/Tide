from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.entities import (
    Session as ExamSession,
    StudentInSession,
    Submission,
    Flag,
    CodeSnapshot,
    Assignment
)


def record_code_snapshot(
    db: Session,
    student_session_id: int,
    code: str,
    ts: Optional[datetime] = None
) -> Optional[CodeSnapshot]:
    """
    Records an immutable delta keyframe of the student's code.
    Detects sudden bulk jumps and correlates with telemetry paste flags.
    """
    event_time = ts or datetime.now(timezone.utc)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)

    # Check previous snapshot
    prev = db.query(CodeSnapshot).filter(
        CodeSnapshot.student_session_id == student_session_id
    ).order_by(CodeSnapshot.ts.desc()).first()

    # Deduplicate identical code snapshots
    if prev and prev.code == code:
        return prev

    clean_code = code or ""
    lines_cnt = len(clean_code.splitlines()) if clean_code else 0
    chars_cnt = len(clean_code)

    is_paste = False
    if prev:
        delta_chars = chars_cnt - prev.chars_count
        if delta_chars >= 25:
            # Check for recent paste flag within 25 seconds
            t_window = event_time - timedelta(seconds=25)
            recent_flag = db.query(Flag).filter(
                Flag.student_session_id == student_session_id,
                Flag.type.in_(["paste", "correlated-cheat-attempt"]),
                Flag.ts >= t_window
            ).first()
            if recent_flag or delta_chars >= 50:
                is_paste = True
    else:
        # Initial snapshot
        if chars_cnt >= 100:
            is_paste = True

    snapshot = CodeSnapshot(
        student_session_id=student_session_id,
        code=clean_code,
        lines_count=lines_cnt,
        chars_count=chars_cnt,
        is_paste_event=is_paste,
        ts=event_time
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_student_playback_data(
    db: Session,
    session_id: int,
    student_id: int,
    teacher_id: int
) -> dict[str, Any]:
    """
    Constructs the complete forensic timeline and keyframe history
    for the teacher's interactive code growth scrubber.
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

    student = db.query(StudentInSession).filter(
        StudentInSession.id == student_id,
        StudentInSession.session_id == session.id
    ).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found in this session"
        )

    assignment = session.assignment
    sub = db.query(Submission).filter(Submission.student_session_id == student.id).first()

    snapshots = db.query(CodeSnapshot).filter(
        CodeSnapshot.student_session_id == student.id
    ).order_by(CodeSnapshot.ts.asc()).all()

    # If no snapshots have been recorded yet, create baseline from starter or submission
    if not snapshots:
        starter = (assignment.starter_code if assignment else "") or ""
        baseline = record_code_snapshot(db, student.id, starter, student.joined_at)
        if sub and sub.code and sub.code != starter:
            current_snap = record_code_snapshot(db, student.id, sub.code, sub.last_autosaved_at or sub.submitted_at)
            snapshots = [baseline, current_snap]
        else:
            snapshots = [baseline]

    # Flags & Telemetry events
    flags = db.query(Flag).filter(
        Flag.student_session_id == student.id
    ).order_by(Flag.ts.asc()).all()

    joined_at = student.joined_at
    if joined_at.tzinfo is None:
        joined_at = joined_at.replace(tzinfo=timezone.utc)

    # Process snapshots with relative timestamps
    snapshot_items = []
    prev_chars = 0
    prev_lines = 0
    max_jump_chars = 0
    paste_count = 0

    for idx, s in enumerate(snapshots):
        s_ts = s.ts
        if s_ts.tzinfo is None:
            s_ts = s_ts.replace(tzinfo=timezone.utc)
        rel_sec = max(0, int((s_ts - joined_at).total_seconds()))

        delta_c = s.chars_count - prev_chars
        delta_l = s.lines_count - prev_lines
        if delta_c > max_jump_chars and idx > 0:
            max_jump_chars = delta_c

        if s.is_paste_event:
            paste_count += 1

        snapshot_items.append({
            "id": s.id,
            "index": idx,
            "ts": s_ts.isoformat(),
            "time_str": s_ts.strftime("%H:%M:%S"),
            "relative_seconds": rel_sec,
            "code": s.code,
            "lines_count": s.lines_count,
            "chars_count": s.chars_count,
            "delta_chars": delta_c,
            "delta_lines": delta_l,
            "is_paste_event": s.is_paste_event
        })

        prev_chars = s.chars_count
        prev_lines = s.lines_count

    # Process flags for timeline marker ticks
    timeline_events = []
    for f in flags:
        f_ts = f.ts
        if f_ts.tzinfo is None:
            f_ts = f_ts.replace(tzinfo=timezone.utc)
        f_rel = max(0, int((f_ts - joined_at).total_seconds()))

        timeline_events.append({
            "id": f.id,
            "type": f.type,
            "severity": f.severity,
            "ts": f_ts.isoformat(),
            "time_str": f_ts.strftime("%H:%M:%S"),
            "relative_seconds": f_rel,
            "metadata": f.flag_metadata or {}
        })

    end_time = sub.submitted_at if (sub and sub.submitted_at) else (snapshots[-1].ts if snapshots else joined_at)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    total_duration = max(1, int((end_time - joined_at).total_seconds()))

    return {
        "student_id": student.id,
        "student_name": student.student_name,
        "student_identifier": student.student_identifier,
        "session_id": session.id,
        "assignment_title": assignment.title if assignment else "Assessment",
        "joined_at": joined_at.isoformat(),
        "submitted_at": sub.submitted_at.isoformat() if (sub and sub.submitted_at) else None,
        "total_duration_seconds": total_duration,
        "starter_code": assignment.starter_code if assignment else "",
        "final_code": sub.code if sub else (snapshots[-1].code if snapshots else ""),
        "total_snapshots": len(snapshot_items),
        "total_pastes": paste_count,
        "max_jump_chars": max_jump_chars,
        "risk_score": student.risk_score or 0,
        "snapshots": snapshot_items,
        "events": timeline_events
    }
