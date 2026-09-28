"""Shapes sent to the console. Keep in sync with console/src/types.ts."""
import json
from typing import Any

from tide_common.policy import Policy, display_app
from tide_common.protocol import SEVERITY_RANK

from tide_server.models import Event, Exam, Flag, Seat


def exam_policy(exam: Exam) -> Policy:
    return Policy.from_dict(json.loads(exam.policy_json or "{}"))


def seat_status(seat: Seat, open_flags: list[Flag]) -> str:
    if seat.state == "submitted":
        return "done"
    if seat.state == "offline":
        return "off"
    worst = max((SEVERITY_RANK[f.severity] for f in open_flags if f.status == "open"), default=0)
    if seat.state == "blocked" or worst >= 2:
        return "crit"
    if worst == 1:
        return "warn"
    if seat.state == "lobby":
        return "wait"
    return "ok"


def seat_out(seat: Seat, open_flags: list[Flag]) -> dict[str, Any]:
    return {"id": seat.id, "seat_no": seat.seat_no, "roll": seat.roll, "set": seat.set_name,
            "state": seat.state, "status": seat_status(seat, open_flags),
            "flags": len([f for f in open_flags if f.status == "open"]),
            "fg_app": seat.fg_app, "simulated": seat.simulated,
            "preflight": json.loads(seat.preflight_json or "{}")}


def flag_out(flag: Flag, seat_no: int) -> dict[str, Any]:
    return {"id": flag.id, "seat_id": flag.seat_id, "seat_no": seat_no, "ts": flag.ts,
            "kind": flag.kind, "severity": flag.severity, "title": flag.title,
            "source": flag.source, "label": flag.label, "confidence": flag.confidence,
            "action": flag.action, "status": flag.status, "has_shot": bool(flag.screenshot),
            "data": json.loads(flag.data_json or "{}")}


def exam_out(exam: Exam) -> dict[str, Any]:
    return {"id": exam.id, "title": exam.title, "duration_s": exam.duration_s,
            "join_code": exam.join_code, "state": exam.state, "started_at": exam.started_at,
            "ends_at": exam.ends_at, "apps": list(exam_policy(exam).apps)}


def event_text(kind: str, data: dict[str, Any]) -> str:
    if kind == "window":
        host = data.get("host")
        return host if host else display_app(data.get("process", ""))
    if kind == "network":
        return "Internet on" if data.get("internet") else "Offline"
    if kind == "joined":
        return "Joined"
    if kind == "start":
        return f"Set {data.get('set')} delivered · {data.get('files', 0)} files"
    if kind == "agent_back":
        return f"Agent back after {data.get('gap', 0)} s"
    if kind == "denied_closed":
        return f"{data.get('name')} closed at pre-flight"
    if kind == "teacher":
        return data.get("text", "")
    if kind == "submitted":
        return "Submitted" + (" (time up)" if data.get("auto") else "")
    return kind


def event_out(event: Event) -> dict[str, Any]:
    data = json.loads(event.data_json or "{}")
    return {"id": event.id, "seat_id": event.seat_id, "ts": event.ts, "kind": event.kind,
            "text": event_text(event.kind, data)}


KIND_TEXT = {"blocked_site": "AI / blocked site", "denied_app": "Blocked app", "jev": "Jev flag",
             "heuristic": "Suspicious app", "internet": "Internet detected", "old_code": "Old code reused",
             "file_open": "Pre-exam file", "code_burst": "Code burst", "agent_offline": "Agent offline",
             "usb": "USB drive", "lan_peer": "LAN connection", "clipboard": "Large paste",
             "ai_extension": "AI extension"}
