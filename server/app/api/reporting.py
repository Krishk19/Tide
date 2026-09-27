import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_teacher
from app.models.entities import Teacher, Session as ExamSession, StudentInSession, Submission, Flag, CodeSnapshot
from app.services.plagiarism import analyze_session_plagiarism

router = APIRouter(prefix="/sessions", tags=["Reporting & Marksheet Export"])


@router.get("/{session_id}/students/{student_id}/timeline")
def get_student_forensic_timeline(
    session_id: int,
    student_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Constructs a merged, chronologically sorted forensic audit trail of all student actions:
    - Initial connection (timestamp, IP/terminal)
    - Code growth & keystroke snapshot checkpoints
    - Security & telemetry flags (focus lost, paste, disconnect, reconnection gap)
    - Pedagogical events (warning modals, compensatory time granted)
    - Exam submission (final score and test breakdown)
    - Proctor review & escalation notes
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    student = db.query(StudentInSession).filter(
        StudentInSession.id == student_id,
        StudentInSession.session_id == session_id
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in this session")

    events: List[Dict[str, Any]] = []

    # 1. Joined event
    events.append({
        "type": "joined",
        "timestamp": student.joined_at.isoformat() if student.joined_at else datetime.now(timezone.utc).isoformat(),
        "title": "Terminal Joined Exam Gateway",
        "description": f"Terminal initialized for {student.student_name} ({student.student_identifier}).",
        "severity": "info",
        "badge": "JOINED"
    })

    # 2. Code snapshots
    snapshots = db.query(CodeSnapshot).filter(
        CodeSnapshot.student_session_id == student.id
    ).order_by(CodeSnapshot.ts.asc()).all()

    last_chars = 0
    for snap in snapshots:
        delta = snap.chars_count - last_chars
        last_chars = snap.chars_count
        if snap.is_paste_event or delta >= 40:
            events.append({
                "type": "code_paste",
                "timestamp": snap.ts.isoformat(),
                "title": f"Bulk Code Injection (+{delta} chars)",
                "description": f"Editor jumped to {snap.lines_count} lines (+{delta} chars). External paste signature.",
                "severity": "critical",
                "badge": "PASTE SPIKE"
            })
        elif delta > 0 and len(snapshots) <= 25:
            # Include periodic key milestones
            events.append({
                "type": "snapshot",
                "timestamp": snap.ts.isoformat(),
                "title": f"Code Autosaved ({snap.lines_count} lines)",
                "description": f"Incremental progress checkpoint (+{delta} chars).",
                "severity": "low",
                "badge": "AUTOSAVE"
            })

    # 3. Telemetry flags
    flags = db.query(Flag).filter(
        Flag.student_session_id == student.id
    ).order_by(Flag.ts.asc()).all()

    for f in flags:
        meta = f.flag_metadata or {}
        title = f"Telemetry Flag: {f.type}"
        desc = f"Logged telemetry event {f.type}."

        if f.type == "focus-lost":
            title = "Window Switched / Focus Lost"
            desc = "Kiosk window lost focus. Student may have Alt-Tabbed or switched applications."
        elif f.type == "focus-regained":
            title = "Window Focus Regained"
            desc = "Kiosk window regained active focus."
        elif f.type == "fullscreen-exit":
            title = "Attempted Fullscreen Exit"
            desc = "Student attempted to escape locked kiosk fullscreen mode."
        elif f.type == "paste":
            title = f"Editor Paste Detected ({meta.get('length', 0)} chars)"
            desc = f"Pasted content sample: {meta.get('sample', '')[:60]}"
        elif f.type == "connection-lost":
            title = "Abrupt Socket Disconnect"
            desc = "Terminal WebSocket connection lost (network drop or PC reboot)."
        elif f.type == "reconnected":
            title = f"Reconnected After {meta.get('downtime_seconds', 0)}s Downtime"
            desc = f"Restored {meta.get('restored_line_count', 0)} lines of code automatically from SQLite."
        elif f.type == "correlated-cheat-attempt":
            title = "⚠️ Correlated Cheat Attempt Flagged"
            desc = meta.get("reason", "Focus lost immediately followed by bulk external paste.")

        if f.notes:
            desc += f" [Proctor note: {f.notes}]"

        events.append({
            "type": "flag",
            "timestamp": f.ts.isoformat(),
            "title": title,
            "description": desc,
            "severity": f.severity,
            "badge": f.type.upper(),
            "status": f.status
        })

    # 4. Compensatory time event
    if student.extra_time_seconds > 0:
        events.append({
            "type": "extra_time",
            "timestamp": student.joined_at.isoformat(),
            "title": f"Compensatory Time Granted (+{round(student.extra_time_seconds / 60)} min)",
            "description": f"Instructor added {student.extra_time_seconds} seconds of extra exam time.",
            "severity": "info",
            "badge": "TIME EXTENSION"
        })

    # 5. Submission event
    sub = db.query(Submission).filter(Submission.student_session_id == student.id).first()
    if sub and sub.submitted_at:
        tr = sub.test_results or {}
        score = tr.get("score_percentage", 0.0)
        passed = tr.get("passed_tests", 0)
        total = tr.get("total_tests", 0)
        events.append({
            "type": "submission",
            "timestamp": sub.submitted_at.isoformat(),
            "title": f"Exam Submitted - Final Score {score}%",
            "description": f"Automated grading completed. Passed {passed}/{total} test suites.",
            "severity": "info" if score >= 60 else "medium",
            "badge": "SUBMITTED"
        })

    # Sort all events chronologically
    events.sort(key=lambda e: e["timestamp"])

    return {
        "student": {
            "id": student.id,
            "name": student.student_name,
            "identifier": student.student_identifier,
            "risk_score": student.risk_score,
            "extra_time_seconds": student.extra_time_seconds
        },
        "session": {
            "id": session.id,
            "access_code": session.access_code,
            "assignment_title": session.assignment.title if session.assignment else "Assessment"
        },
        "total_events": len(events),
        "timeline": events
    }


@router.get("/{session_id}/export")
def export_session_marksheet(
    session_id: int,
    format: str = Query("csv", pattern="^(csv|json)$"),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    1-Click University Marksheet and Forensic Report Exporter:
    - format=csv: Standard CSV format ready for university LMS/ERP upload.
    - format=json: Complete structured forensic archive with source code, test traces, and audit logs.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or unauthorized")

    assignment = session.assignment
    students = db.query(StudentInSession).filter(StudentInSession.session_id == session.id).all()

    # Calculate plagiarism matrix for session to extract max similarity match per student
    plag_res = analyze_session_plagiarism(session_id, db, threshold=0.0)
    max_plag_map: Dict[int, float] = {}
    for pair in plag_res.get("pairs", []):
        sim = pair.get("similarity_pct", 0.0)
        st_a_id = pair["student_a"]["id"]
        st_b_id = pair["student_b"]["id"]
        max_plag_map[st_a_id] = max(max_plag_map.get(st_a_id, 0.0), sim)
        max_plag_map[st_b_id] = max(max_plag_map.get(st_b_id, 0.0), sim)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)

        # Header comments for university records
        writer.writerow(["# UNIVERSITY EXAMINATION REPORT"])
        writer.writerow(["# Assignment:", assignment.title if assignment else "N/A"])
        writer.writerow(["# Access Code:", session.access_code])
        writer.writerow(["# Instructor:", current_teacher.name])
        writer.writerow(["# Exported At (UTC):", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow([])

        # Table Headers
        writer.writerow([
            "Roll Number",
            "Student Name",
            "Joined At",
            "Submitted At",
            "Status",
            "Total Tests",
            "Visible Passed",
            "Hidden Passed",
            "Final Score (%)",
            "Security Flags Count",
            "Risk Score",
            "Class Health Zone",
            "Max Plagiarism Match (%)"
        ])

        for st in students:
            sub = db.query(Submission).filter(Submission.student_session_id == st.id).first()
            flag_count = db.query(Flag).filter(Flag.student_session_id == st.id).count()
            has_correlated = db.query(Flag).filter(Flag.student_session_id == st.id, Flag.type == "correlated-cheat-attempt").count() > 0

            # Determine Zone
            zone = "Green (On Track)"
            if st.risk_score >= 60 or has_correlated or flag_count >= 3:
                zone = "Red (High Suspicion)"
            elif not sub or not sub.submitted_at:
                zone = "Yellow (In Progress / Idle)"

            tr = sub.test_results or {} if sub else {}
            score = tr.get("score_percentage", 0.0) if (sub and sub.submitted_at) else 0.0
            total_tests = tr.get("total_tests", 0)
            vis_passed = tr.get("visible_passed", 0)
            hid_passed = tr.get("hidden_passed", 0)
            max_plag = max_plag_map.get(st.id, 0.0)

            writer.writerow([
                st.student_identifier,
                st.student_name,
                st.joined_at.strftime("%Y-%m-%d %H:%M:%S") if st.joined_at else "N/A",
                sub.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if (sub and sub.submitted_at) else "Not Submitted",
                "Submitted" if (sub and sub.submitted_at) else "In Progress",
                total_tests,
                vis_passed,
                hid_passed,
                f"{score:.2f}",
                flag_count,
                st.risk_score,
                zone,
                f"{max_plag:.1f}%"
            ])

        csv_content = output.getvalue()
        filename = f"tide_marksheet_{session.access_code}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    # JSON Full Forensic Archive
    archive_students = []
    for st in students:
        sub = db.query(Submission).filter(Submission.student_session_id == st.id).first()
        flags = db.query(Flag).filter(Flag.student_session_id == st.id).all()
        archive_students.append({
            "id": st.id,
            "student_identifier": st.student_identifier,
            "student_name": st.student_name,
            "joined_at": st.joined_at.isoformat() if st.joined_at else None,
            "risk_score": st.risk_score,
            "extra_time_seconds": st.extra_time_seconds,
            "max_plagiarism_pct": max_plag_map.get(st.id, 0.0),
            "submission": {
                "submitted_at": sub.submitted_at.isoformat() if (sub and sub.submitted_at) else None,
                "language": sub.language if sub else None,
                "code": sub.code if sub else None,
                "test_results": sub.test_results if sub else None
            },
            "flag_count": len(flags),
            "flags": [
                {
                    "type": f.type,
                    "severity": f.severity,
                    "timestamp": f.ts.isoformat(),
                    "status": f.status,
                    "notes": f.notes,
                    "metadata": f.flag_metadata
                }
                for f in flags
            ]
        })

    return {
        "export_metadata": {
            "version": "Tide V2.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "institution": "Computer Science Laboratory"
        },
        "teacher": {
            "id": current_teacher.id,
            "name": current_teacher.name,
            "username": current_teacher.username
        },
        "session": {
            "id": session.id,
            "access_code": session.access_code,
            "start_time": session.start_time.isoformat() if session.start_time else None,
            "status": session.status,
            "assignment_title": assignment.title if assignment else "N/A"
        },
        "student_count": len(students),
        "students": archive_students
    }
