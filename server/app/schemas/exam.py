from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel
from app.schemas.assignment import AssignmentStudentResponse

class ExamStateResponse(BaseModel):
    status: str  # "locked", "active", "submitted", "closed"
    start_time: datetime
    server_time: datetime
    remaining_seconds: int
    assignment: Optional[AssignmentStudentResponse] = None
    saved_code: Optional[str] = None
    saved_language: Optional[str] = None
    is_submitted: bool = False

class CodeRunRequest(BaseModel):
    student_session_id: int
    code: str
    language: str

class TestResultDetail(BaseModel):
    test_id: Any
    passed: bool
    input: Optional[str] = None
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    execution_time_ms: Optional[float] = None
    error: Optional[str] = None

class CodeRunResponse(BaseModel):
    passed_all: bool
    results: list[TestResultDetail]
    execution_time_ms: float
    error: Optional[str] = None

class CodeSubmitRequest(BaseModel):
    student_session_id: int
    code: str
    language: str

class CodeSubmitResponse(BaseModel):
    is_submitted: bool
    total_tests: int
    passed_tests: int
    score_percentage: float
    visible_results: list[TestResultDetail]
    hidden_summary: dict[str, Any]  # total, passed counts only! No raw inputs.
    submitted_at: datetime

class AutosaveRequest(BaseModel):
    student_session_id: int
    code: str
    language: Optional[str] = "python"

class AutosaveResponse(BaseModel):
    status: str = "saved"
    timestamp: datetime
