from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class TestCase(BaseModel):
    id: Optional[str] = None
    input: str
    expected_output: str
    explanation: Optional[str] = None


class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    problem_statement: Optional[str] = ""
    starter_code: Optional[str] = None
    visible_test_cases: list[dict[str, Any]] = Field(default_factory=list)
    hidden_test_cases: list[dict[str, Any]] = Field(default_factory=list)
    language_set: str = "cpp,python,java"
    questions: Optional[list[dict[str, Any]]] = Field(default_factory=list)


class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    problem_statement: Optional[str] = None
    starter_code: Optional[str] = None
    visible_test_cases: Optional[list[dict[str, Any]]] = None
    hidden_test_cases: Optional[list[dict[str, Any]]] = None
    language_set: Optional[str] = None
    questions: Optional[list[dict[str, Any]]] = None


class AssignmentTeacherResponse(BaseModel):
    id: int
    teacher_id: int
    title: str
    problem_statement: str
    starter_code: Optional[str] = None
    visible_test_cases: list[dict[str, Any]]
    hidden_test_cases: list[dict[str, Any]]
    language_set: str
    created_at: datetime
    questions: Optional[list[dict[str, Any]]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AssignmentStudentResponse(BaseModel):
    id: int
    title: str
    problem_statement: str
    starter_code: Optional[str] = None
    visible_test_cases: list[dict[str, Any]]
    language_set: str
    questions: Optional[list[dict[str, Any]]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
