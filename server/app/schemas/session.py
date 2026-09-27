from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class SessionCreate(BaseModel):
    assignment_id: int
    start_time: datetime

class SessionStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(scheduled|active|closed)$")

class StudentInSessionItem(BaseModel):
    id: int
    student_name: str
    student_identifier: str
    joined_at: datetime
    last_autosaved_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    flag_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class SessionTeacherResponse(BaseModel):
    id: int
    teacher_id: int
    assignment_id: int
    assignment_title: Optional[str] = None
    access_code: str
    start_time: datetime
    status: str
    student_count: int = 0
    students: Optional[list[StudentInSessionItem]] = None

    model_config = ConfigDict(from_attributes=True)

class StudentJoinRequest(BaseModel):
    access_code: str = Field(..., min_length=4, max_length=10)
    student_name: str = Field(..., min_length=2, max_length=150)
    student_identifier: str = Field(..., min_length=2, max_length=100)

class StudentJoinResponse(BaseModel):
    student_session_id: int
    session_id: int
    student_name: str
    student_identifier: str
