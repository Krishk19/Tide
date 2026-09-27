from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_teacher
from app.models.entities import Teacher, Session as ExamSession
from app.services.plagiarism import analyze_session_plagiarism, get_pairwise_diff

router = APIRouter(prefix="/sessions", tags=["AST Plagiarism & Similarity"])


@router.get("/{session_id}/similarity-matrix")
def get_similarity_matrix(
    session_id: int,
    threshold: float = Query(65.0, ge=0.0, le=100.0, description="Minimum similarity percentage filter"),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Computes pairwise AST / structural code similarity across all students in an exam session.
    Alpha-renames variable and function identifiers, strips syntax noise, and applies
    tokenized k-gram Jaccard matching + sequence alignment.
    Multi-signal correlation filters false positives and flags bulk pastes or synchronized timing.
    Strictly isolated to authenticated teacher's session.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or unauthorized"
        )

    result = analyze_session_plagiarism(session_id, db, threshold=threshold)
    return result


@router.get("/{session_id}/similarity-diff")
def get_similarity_diff(
    session_id: int,
    student_a: int = Query(..., description="First student session ID"),
    student_b: int = Query(..., description="Second student session ID"),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Retrieves detailed side-by-side code diff, structural similarity score,
    and canonical AST token preview between two students.
    """
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.teacher_id == current_teacher.id
    ).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or unauthorized"
        )

    result = get_pairwise_diff(session_id, student_a, student_b, db)
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    return result
