from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Index, Boolean
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
    questions = Column(JSON, nullable=True, default=list)

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
    risk_score = Column(Integer, default=0, nullable=False)
    extra_time_seconds = Column(Integer, default=0, nullable=False)

    session = relationship("Session", back_populates="students")
    submissions = relationship("Submission", back_populates="student_session")
    flags = relationship("Flag", back_populates="student_session")
    code_snapshots = relationship("CodeSnapshot", back_populates="student_session", cascade="all, delete-orphan", order_by="CodeSnapshot.ts")


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
    type = Column(String(50), nullable=False)  # focus-lost, focus-regained, fullscreen-exit, paste, connection-lost, reconnected, correlated-cheat-attempt
    severity = Column(String(20), default="medium", nullable=False)  # info, low, medium, high, critical
    flag_metadata = Column("metadata", JSON, nullable=True)  # paste size, gap duration, correlated flags
    ts = Column(DateTime, default=utc_now, nullable=False, index=True)
    status = Column(String(30), nullable=False, default="open")  # open, dismissed, escalated
    notes = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    student_session = relationship("StudentInSession", back_populates="flags")
    reviewer = relationship("Teacher", foreign_keys=[reviewed_by])


class CodeSnapshot(Base):
    __tablename__ = "code_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    student_session_id = Column(Integer, ForeignKey("students_in_session.id"), nullable=False, index=True)
    code = Column(Text, nullable=False)
    lines_count = Column(Integer, default=0, nullable=False)
    chars_count = Column(Integer, default=0, nullable=False)
    is_paste_event = Column(Boolean, default=False, nullable=False)
    ts = Column(DateTime, default=utc_now, nullable=False, index=True)

    student_session = relationship("StudentInSession", back_populates="code_snapshots")


# Indexing
Index("idx_flags_student_ts", Flag.student_session_id, Flag.ts)
Index("idx_snapshots_student_ts", CodeSnapshot.student_session_id, CodeSnapshot.ts)
Index("idx_sessions_teacher", Session.teacher_id)
Index("idx_assignments_teacher", Assignment.teacher_id)
