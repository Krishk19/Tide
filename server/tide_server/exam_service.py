import base64
from tide_common.protocol import msg
import hashlib
import json
import secrets
from typing import Sequence

from sqlmodel import Session, select

from tide_common.policy import Policy

from tide_server import clock
from tide_server.models import Exam, ExamFile, Flag, Seat

JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I


class PairError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def new_join_code() -> str:
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(6))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_exam(db: Session, title: str, duration_s: int, apps: Sequence[str],
                internet: str = "allowed") -> Exam:
    code = new_join_code()
    while db.exec(select(Exam).where(Exam.join_code == code)).first():
        code = new_join_code()
    exam = Exam(title=title, duration_s=duration_s, join_code=code,
                policy_json=json.dumps(Policy.from_apps(apps, internet=internet).to_dict()))
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def add_file(db: Session, exam_id: int, set_name: str, name: str, data: bytes) -> ExamFile:
    f = ExamFile(exam_id=exam_id, set_name=set_name, name=name, data=data)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def current_exam(db: Session) -> Exam | None:
    return db.exec(select(Exam).order_by(Exam.id.desc())).first()


def open_flags(db: Session, seat_id: int) -> list[Flag]:
    return list(db.exec(select(Flag).where(Flag.seat_id == seat_id, Flag.status == "open")).all())


def pair_seat(db: Session, join_code: str, roll: str, seat_no: int, hostname: str) -> tuple[Seat, str]:
    exam = db.exec(select(Exam).where(Exam.join_code == join_code.strip().upper())).first()
    if exam is None or exam.state == "ended":
        raise PairError(404, "Unknown join code")
    roll = roll.strip().upper()
    seat = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.seat_no == seat_no)).first()
    if seat and seat.roll != roll:
        raise PairError(409, f"Seat {seat_no} is taken")
    if seat and seat.state == "submitted":
        raise PairError(409, "Already submitted")
    token = secrets.token_urlsafe(32)
    if seat and seat.simulated:            # demo mode: a real PC replaces the simulated one
        seat.simulated, seat.state, seat.fg_app, seat.preflight_json = False, "lobby", "", "{}"
    seat = seat or Seat(exam_id=exam.id, seat_no=seat_no, roll=roll)
    seat.hostname = hostname
    seat.token_hash = hash_token(token)
    seat.last_seen = clock.now()
    db.add(seat)
    db.commit()
    db.refresh(seat)
    return seat, token


def effective_end(exam: Exam, seat: Seat) -> float | None:
    return seat.ends_at_override or exam.ends_at


def seat_by_token(db: Session, token: str) -> Seat | None:
    if not token:
        return None
    return db.exec(select(Seat).where(Seat.token_hash == hash_token(token))).first()


def set_for_seat(seat_no: int, available: set[str]) -> str:
    return "B" if seat_no % 2 == 0 and "B" in available else "A"


def sets_available(db: Session, exam_id: int) -> set[str]:
    return {f.set_name for f in db.exec(select(ExamFile).where(ExamFile.exam_id == exam_id)).all()}


def go_live(db: Session, exam: Exam, seat: Seat) -> None:
    seat.set_name = seat.set_name or set_for_seat(seat.seat_no, sets_available(db, exam.id))
    seat.state = "live"
    db.add(seat)


def start_exam(db: Session, exam: Exam) -> list[int]:
    t = clock.now()
    exam.state, exam.started_at, exam.ends_at = "live", t, t + exam.duration_s
    db.add(exam)
    ready = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.state == "ready")).all()
    for seat in ready:
        go_live(db, exam, seat)
    db.commit()
    return [s.id for s in ready]


def extend(db: Session, exam: Exam, seat_id: int | None, minutes: int) -> list[tuple[int, float]]:
    delta = minutes * 60
    changed: list[tuple[int, float]] = []
    if seat_id is None:
        exam.ends_at = (exam.ends_at or clock.now()) + delta
        db.add(exam)
        seats = db.exec(select(Seat).where(Seat.exam_id == exam.id)).all()
        for s in seats:
            if s.ends_at_override:
                s.ends_at_override += delta
                db.add(s)
        db.commit()
        return [(s.id, effective_end(exam, s)) for s in seats if s.state in ("live", "offline")]
    seat = db.get(Seat, seat_id)
    seat.ends_at_override = (effective_end(exam, seat) or clock.now()) + delta
    db.add(seat)
    db.commit()
    changed.append((seat.id, seat.ends_at_override))
    return changed


def start_message(db: Session, exam: Exam, seat: Seat) -> dict:
    files = db.exec(select(ExamFile).where(ExamFile.exam_id == exam.id,
                                           ExamFile.set_name == seat.set_name)).all()
    return msg("start", set=seat.set_name,
               files=[{"name": f.name, "b64": base64.b64encode(f.data).decode()} for f in files],
               ends_at=effective_end(exam, seat))
