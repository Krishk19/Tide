from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session
from app.models.entities import StudentInSession, Flag

# In-memory sliding window buffer:
# student_session_id -> list of dicts: {"type": str, "ts": datetime, "metadata": dict}
EVENT_BUFFERS: dict[int, list[dict[str, Any]]] = {}
BUFFER_WINDOW_SECONDS = 15.0

def buffer_event(
    student_session_id: int,
    event_type: str,
    ts: datetime,
    metadata: Optional[dict[str, Any]] = None
):
    """Stores recent events in an in-memory sliding window for correlation."""
    if student_session_id not in EVENT_BUFFERS:
        EVENT_BUFFERS[student_session_id] = []

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    EVENT_BUFFERS[student_session_id].append({
        "type": event_type,
        "ts": ts,
        "metadata": metadata or {}
    })

    # Prune events older than BUFFER_WINDOW_SECONDS
    cutoff = ts - timedelta(seconds=BUFFER_WINDOW_SECONDS)
    EVENT_BUFFERS[student_session_id] = [
        e for e in EVENT_BUFFERS[student_session_id] if e["ts"] >= cutoff
    ]

def evaluate_correlation(
    student_session_id: int,
    current_event_type: str,
    current_ts: datetime,
    current_metadata: Optional[dict[str, Any]] = None
) -> Optional[dict[str, Any]]:
    """
    Checks if the incoming event correlates with recent events in the sliding window.
    Rule: If current_event is 'paste' (and length >= 20 chars), check if focus-lost
    or fullscreen-exit occurred within the last 8 seconds.
    """
    if current_event_type != "paste":
        return None

    paste_len = (current_metadata or {}).get("length", 0)
    if paste_len < 20:
        return None

    if current_ts.tzinfo is None:
        current_ts = current_ts.replace(tzinfo=timezone.utc)

    events = EVENT_BUFFERS.get(student_session_id, [])

    # Look back in sliding window for focus-lost or fullscreen-exit
    for prev in reversed(events):
        if prev["type"] in ("focus-lost", "fullscreen-exit"):
            delta_sec = (current_ts - prev["ts"]).total_seconds()
            if 0.0 <= delta_sec <= 8.0:
                sample = str((current_metadata or {}).get("sample", ""))
                reason = f"Window lost focus for {delta_sec:.1f}s followed immediately by external paste of {paste_len} chars"
                return {
                    "type": "correlated-cheat-attempt",
                    "severity": "critical",
                    "metadata": {
                        "blur_duration_seconds": round(delta_sec, 1),
                        "paste_length": paste_len,
                        "paste_sample": sample[:60],
                        "confidence": "high",
                        "trigger_event": prev["type"],
                        "reason": reason
                    }
                }
    return None

def calculate_risk_score(db: Session, student_session_id: int) -> int:
    """
    Computes a dynamic risk score (0 - 100) based on accumulated, non-dismissed flags.
    Weights:
      - focus-lost: 5 pts each (capped at 25)
      - fullscreen-exit: 20 pts each
      - connection-lost: 10 pts each
      - paste: min(25, total_chars // 25)
      - correlated-cheat-attempt: 40 pts per occurrence
    """
    flags = db.query(Flag).filter(Flag.student_session_id == student_session_id).all()

    focus_lost_cnt = 0
    fullscreen_exit_cnt = 0
    connection_lost_cnt = 0
    total_paste_chars = 0
    correlated_cnt = 0
    internet_detected_cnt = 0

    for f in flags:
        if f.status == "dismissed":
            continue  # Dismissed false-alarms do not penalize student!

        if f.type == "focus-lost":
            focus_lost_cnt += 1
        elif f.type == "fullscreen-exit":
            fullscreen_exit_cnt += 1
        elif f.type == "connection-lost":
            connection_lost_cnt += 1
        elif f.type == "paste":
            total_paste_chars += (f.flag_metadata or {}).get("length", 0)
        elif f.type == "correlated-cheat-attempt":
            correlated_cnt += 1
        elif f.type == "internet-detected":
            internet_detected_cnt += 1

    score = 0
    score += min(25, focus_lost_cnt * 5)
    score += fullscreen_exit_cnt * 20
    score += connection_lost_cnt * 10
    score += min(25, total_paste_chars // 25)
    score += correlated_cnt * 40
    score += internet_detected_cnt * 50

    final_score = min(100, max(0, score))

    student = db.query(StudentInSession).filter(StudentInSession.id == student_session_id).first()
    if student:
        student.risk_score = final_score
        db.commit()
        db.refresh(student)

    return final_score

def get_risk_level(score: int) -> str:
    """Returns human-readable risk category for color coding."""
    if score >= 75:
        return "high"
    elif score >= 50:
        return "suspicious"
    elif score >= 20:
        return "low"
    return "clean"
