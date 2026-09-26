from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(150), nullable=False)

    assignments = relationship("Assignment", back_populates="teacher")
    sessions = relationship("Session", back_populates="teacher")


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    problem_statement = Column(Text, nullable=False)
    starter_code = Column(Text, nullable=True)
    visible_test_cases = Column(JSON, nullable=False, default=list)
    hidden_test_cases = Column(JSON, nullable=False, default=list)  # Server-side only!
    language_set = Column(String(100), nullable=False, default="cpp,python,java")
    created_at = Column(DateTime, default=utc_now, nullable=False)

    teacher = relationship("Teacher", back_populates="assignments")
    sessions = relationship("Session", back_populates="assignment")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    access_code = Column(String(6), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    status = Column(String(30), nullable=False, default="scheduled")  # scheduled, active, closed

    teacher = relationship("Teacher", back_populates="sessions")
    assignment = relationship("Assignment", back_populates="sessions")
    students = relationship("StudentInSession", back_populates="session")


class StudentInSession(Base):
    __tablename__ = "students_in_session"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    student_name = Column(String(150), nullable=False)
    student_identifier = Column(String(100), nullable=False)  # roll number / ID
    joined_at = Column(DateTime, default=utc_now, nullable=False)

    session = relationship("Session", back_populates="students")
    submissions = relationship("Submission", back_populates="student_session")
    flags = relationship("Flag", back_populates="student_session")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    student_session_id = Column(Integer, ForeignKey("students_in_session.id"), nullable=False, index=True)
    code = Column(Text, nullable=True)
    language = Column(String(50), nullable=True)
    test_results = Column(JSON, nullable=True)  # Visible results & pass/fail booleans
    last_autosaved_at = Column(DateTime, default=utc_now, nullable=False)
    submitted_at = Column(DateTime, nullable=True)

    student_session = relationship("StudentInSession", back_populates="submissions")


class Flag(Base):
    __tablename__ = "flags"

    id = Column(Integer, primary_key=True, index=True)
    student_session_id = Column(Integer, ForeignKey("students_in_session.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # focus-lost, focus-regained, fullscreen-exit, paste, connection-lost, reconnected
    flag_metadata = Column("metadata", JSON, nullable=True)  # paste size, gap duration, correlated flags
    ts = Column(DateTime, default=utc_now, nullable=False, index=True)
    status = Column(String(30), nullable=False, default="open")  # open, dismissed, escalated
    reviewed_by = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    student_session = relationship("StudentInSession", back_populates="flags")
    reviewer = relationship("Teacher", foreign_keys=[reviewed_by])


# Indexing
Index("idx_flags_student_ts", Flag.student_session_id, Flag.ts)
Index("idx_sessions_teacher", Session.teacher_id)
Index("idx_assignments_teacher", Assignment.teacher_id)
