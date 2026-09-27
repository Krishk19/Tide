from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_teacher
from app.models.entities import Teacher
from app.schemas.auth import TeacherRegisterRequest, TeacherLoginRequest, TokenResponse, TeacherResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def register_teacher(req: TeacherRegisterRequest, db: Session = Depends(get_db)):
    """Registers a new instructor account."""
    existing = db.query(Teacher).filter(Teacher.username == req.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    teacher = Teacher(
        username=req.username,
        password_hash=hash_password(req.password),
        name=req.name
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher

@router.post("/login", response_model=TokenResponse)
def login_teacher(req: TeacherLoginRequest, db: Session = Depends(get_db)):
    """Logs in an instructor and returns a JWT Bearer token."""
    teacher = db.query(Teacher).filter(Teacher.username == req.username).first()
    if not teacher or not verify_password(req.password, teacher.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": str(teacher.id), "username": teacher.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "teacher": teacher
    }

@router.get("/me", response_model=TeacherResponse)
def get_me(current_teacher: Teacher = Depends(get_current_teacher)):
    """Returns the authenticated instructor's profile."""
    return current_teacher
