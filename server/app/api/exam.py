from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import StudentInSession, Session as ExamSession, Assignment, Submission
from app.schemas.assignment import AssignmentStudentResponse
from app.schemas.exam import (
    ExamStateResponse,
    CodeRunRequest,
    CodeRunResponse,
    CodeSubmitRequest,
    CodeSubmitResponse,
    AutosaveRequest,
    AutosaveResponse,
    TestResultDetail,
)
from app.services.executor import evaluate_submission

router = APIRouter(prefix="/exam", tags=["Exam Operations"])

def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)

@router.get("/state/{student_session_id}", response_model=ExamStateResponse)
def get_exam_state(student_session_id: int, db: Session = Depends(get_db)):
    """
    Checks exam state against the server clock.
    Enforces start-time lockdown: if server_time < session.start_time,
    the problem statement and test cases are strictly withheld.
    """
    student = db.query(StudentInSession).filter(StudentInSession.id == student_session_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student session not found")

    session: ExamSession = student.session
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated exam session not found")

    assignment: Assignment = session.assignment
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    now = get_utc_now()
    start_time = session.start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    # Server-Clock Start-Time Gate
    diff_seconds = (start_time - now).total_seconds()

    sub = db.query(Submission).filter(Submission.student_session_id == student.id).first()
    is_submitted = (sub.submitted_at is not None) if sub else False

    if diff_seconds > 0 and session.status == "scheduled":
        # LOCKED STATE: Do NOT send problem statement or test cases!
        return ExamStateResponse(
            status="locked",
            start_time=start_time,
            server_time=now,
            remaining_seconds=int(diff_seconds),
            assignment=None,
            saved_code=None,
            saved_language=None,
            is_submitted=False,
            extra_time_seconds=student.extra_time_seconds or 0
        )

    # UNLOCKED: Auto-transition session to active if scheduled
    if session.status == "scheduled":
        session.status = "active"
        db.commit()

    if is_submitted:
        exam_status = "submitted"
    elif session.status == "closed":
        exam_status = "closed"
    else:
        exam_status = "active"

    # Student-safe assignment response (NEVER includes hidden_test_cases)
    student_assignment = AssignmentStudentResponse(
        id=assignment.id,
        title=assignment.title,
        problem_statement=assignment.problem_statement,
        starter_code=assignment.starter_code,
        visible_test_cases=assignment.visible_test_cases or [],
        language_set=assignment.language_set
    )

    return ExamStateResponse(
        status=exam_status,
        start_time=start_time,
        server_time=now,
        remaining_seconds=0,
        assignment=student_assignment,
        saved_code=sub.code if sub else assignment.starter_code,
        saved_language=sub.language if sub else "python",
        is_submitted=is_submitted,
        extra_time_seconds=student.extra_time_seconds or 0
    )

@router.post("/run", response_model=CodeRunResponse)
def run_code_visible_tests(req: CodeRunRequest, db: Session = Depends(get_db)):
    """
    Executes student code against visible test cases ONLY.
    Returns full stdout, stderr, and output comparisons for debugging.
    """
    student = db.query(StudentInSession).filter(StudentInSession.id == req.student_session_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student session not found")

    session: ExamSession = student.session
    assignment: Assignment = session.assignment

    visible_tests = assignment.visible_test_cases or []
    if not visible_tests:
        return CodeRunResponse(passed_all=True, results=[], execution_time_ms=0.0)

    start_t = datetime.now()
    raw_results = evaluate_submission(
        language=req.language,
        code=req.code,
        test_cases=visible_tests,
        timeout_seconds=3.0
    )
    total_time_ms = (datetime.now() - start_t).total_seconds() * 1000.0

    details = [
        TestResultDetail(
            test_id=r["test_id"],
            passed=r["passed"],
            input=str(r.get("input", "")),
            expected_output=str(r.get("expected_output", "")),
            actual_output=str(r.get("actual_output", "")),
            execution_time_ms=r.get("execution_time_ms", 0.0),
            error=r.get("error")
        )
        for r in raw_results
    ]

    passed_all = all(r.passed for r in details)
    return CodeRunResponse(
        passed_all=passed_all,
        results=details,
        execution_time_ms=total_time_ms
    )

@router.post("/submit", response_model=CodeSubmitResponse)
async def submit_exam(req: CodeSubmitRequest, db: Session = Depends(get_db)):
    """
    Evaluates student code against both visible AND hidden test cases.
    Grades server-side only: hidden inputs and outputs are never returned to the student.
    Persists submission and marks submitted_at.
    """
    student = db.query(StudentInSession).filter(StudentInSession.id == req.student_session_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student session not found")

    session: ExamSession = student.session
    assignment: Assignment = session.assignment

    visible_tests = assignment.visible_test_cases or []
    hidden_tests = assignment.hidden_test_cases or []

    # 1. Run visible tests
    vis_raw = evaluate_submission(req.language, req.code, visible_tests, timeout_seconds=3.0)
    visible_results = [
        TestResultDetail(
            test_id=r["test_id"],
            passed=r["passed"],
            input=str(r.get("input", "")),
            expected_output=str(r.get("expected_output", "")),
            actual_output=str(r.get("actual_output", "")),
            execution_time_ms=r.get("execution_time_ms", 0.0),
            error=r.get("error")
        )
        for r in vis_raw
    ]

    # 2. Run hidden tests (Confidential!)
    hid_raw = evaluate_submission(req.language, req.code, hidden_tests, timeout_seconds=3.0)
    passed_hidden_count = sum(1 for r in hid_raw if r["passed"])

    total_tests = len(visible_tests) + len(hidden_tests)
    passed_total = sum(1 for r in visible_results if r.passed) + passed_hidden_count
    score_pct = round((passed_total / total_tests * 100.0), 2) if total_tests > 0 else 100.0

    now = get_utc_now()

    # Update or create Submission
    sub = db.query(Submission).filter(Submission.student_session_id == student.id).first()
    if not sub:
        sub = Submission(student_session_id=student.id)
        db.add(sub)

    sub.code = req.code
    sub.language = req.language
    sub.submitted_at = now
    sub.last_autosaved_at = now
    sub.test_results = {
        "total_tests": total_tests,
        "passed_tests": passed_total,
        "score_percentage": score_pct,
        "visible_passed": sum(1 for r in visible_results if r.passed),
        "visible_total": len(visible_tests),
        "hidden_passed": passed_hidden_count,
        "hidden_total": len(hidden_tests)
    }
    db.commit()
    db.refresh(sub)

    # Live notify teacher command center
    try:
        from app.api.telemetry import manager
        await manager.broadcast_to_teacher(session.teacher_id, {
            "event": "student_submitted",
            "student_session_id": student.id,
            "student_name": student.student_name,
            "student_identifier": student.student_identifier,
            "session_id": session.id,
            "score_percentage": score_pct
        })
    except Exception:
        pass

    return CodeSubmitResponse(
        is_submitted=True,
        total_tests=total_tests,
        passed_tests=passed_total,
        score_percentage=score_pct,
        visible_results=visible_results,
        hidden_summary={
            "total": len(hidden_tests),
            "passed": passed_hidden_count
        },
        submitted_at=now
    )

@router.post("/autosave", response_model=AutosaveResponse)
def autosave_code(req: AutosaveRequest, db: Session = Depends(get_db)):
    """
    Debounced code-state sync endpoint called every few seconds by the student client.
    Guarantees state persistence against crashes, power outages, and process kills.
    """
    sub = db.query(Submission).filter(Submission.student_session_id == req.student_session_id).first()
    now = get_utc_now()
    if not sub:
        sub = Submission(
            student_session_id=req.student_session_id,
            code=req.code,
            language=req.language or "python",
            last_autosaved_at=now
        )
        db.add(sub)
    else:
        sub.code = req.code
        if req.language:
            sub.language = req.language
        sub.last_autosaved_at = now

    db.commit()
    return AutosaveResponse(status="saved", timestamp=now)
