from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_teacher
from app.models.entities import Teacher, Assignment
from app.schemas.assignment import AssignmentCreate, AssignmentUpdate, AssignmentTeacherResponse

router = APIRouter(prefix="/assignments", tags=["Assignments"])

@router.post("", response_model=AssignmentTeacherResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    req: AssignmentCreate,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Creates an assignment authored days ahead.
    Strictly scoped to current_teacher.id.
    """
    assignment = Assignment(
        teacher_id=current_teacher.id,
        title=req.title,
        problem_statement=req.problem_statement,
        starter_code=req.starter_code,
        visible_test_cases=req.visible_test_cases,
        hidden_test_cases=req.hidden_test_cases,
        language_set=req.language_set
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment

@router.get("", response_model=list[AssignmentTeacherResponse])
def list_assignments(
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Lists assignments owned exclusively by the authenticated teacher.
    Guarantees structural multi-teacher isolation.
    """
    return db.query(Assignment).filter(Assignment.teacher_id == current_teacher.id).order_by(Assignment.created_at.desc()).all()

@router.get("/{assignment_id}", response_model=AssignmentTeacherResponse)
def get_assignment(
    assignment_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """Fetches a specific assignment owned by the current teacher."""
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == current_teacher.id
    ).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return assignment

@router.put("/{assignment_id}", response_model=AssignmentTeacherResponse)
def update_assignment(
    assignment_id: int,
    req: AssignmentUpdate,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """Updates an assignment owned by the current teacher."""
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == current_teacher.id
    ).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    
    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)
        
    db.commit()
    db.refresh(assignment)
    return assignment

@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """Deletes an assignment owned by the current teacher."""
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == current_teacher.id
    ).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    
    db.delete(assignment)
    db.commit()
    return None
