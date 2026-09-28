"""Deterministic rules. Run on the agent (instant, offline-safe) — ARCHITECTURE §5.1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .policy import (BROWSERS, CLIPBOARD_MIN, DENY_HOSTS, DENY_PROCESSES, LOCAL_HOSTS,
                     Policy, host_match)
from .protocol import Action, Kind, Severity, Signal


@dataclass(frozen=True)
class RuleHit:
    kind: str
    severity: Severity
    action: Action
    title: str


@dataclass(frozen=True)
class RuleResult:
    status: Literal["allow", "hit", "unknown"]
    hit: RuleHit | None = None


ALLOW = RuleResult("allow")
UNKNOWN = RuleResult("unknown")


def _hit(kind: str, severity: Severity, action: Action, title: str) -> RuleResult:
    return RuleResult("hit", RuleHit(kind, severity, action, title))


def _denied_process(data: dict) -> str | None:
    for key in ("process", "original_name"):
        name = DENY_PROCESSES.get((data.get(key) or "").lower())
        if name:
            return name
    return None


def evaluate(signal: Signal, policy: Policy) -> RuleResult:
    d = signal.data
    k = signal.kind

    if k in (Kind.WINDOW, Kind.PROCESS):
        denied = _denied_process(d)
        if denied:
            return _hit("denied_app", "critical", "kill", f"{denied} — closed")
        if k == Kind.PROCESS:
            return ALLOW
        process = (d.get("process") or "").lower()
        if process in BROWSERS:
            host = d.get("host")
            if host is None:
                return UNKNOWN
            if host.lower() in LOCAL_HOSTS:
                return ALLOW
            name = host_match(host, DENY_HOSTS)
            if name:
                return _hit("blocked_site", "critical", "close_tab", f"{name} — closed")
            return UNKNOWN
        return ALLOW if policy.is_allowed_process(process) else UNKNOWN

    if k == Kind.NETWORK:
        if d.get("internet"):
            return _hit("internet", "critical", "overlay", f"Internet via {d.get('via') or 'network'}")
        return ALLOW
    if k == Kind.CLIPBOARD:
        if d.get("match_path"):
            return _hit("clipboard", "high", "none", f"Paste matches old file · {d.get('match_pct', 0)}%")
        if d.get("length", 0) >= CLIPBOARD_MIN:
            return _hit("clipboard", "medium", "none", f"Large paste · {d['length']} chars")
        return ALLOW
    if k == Kind.FILE_OPEN:
        return _hit("file_open", "high", "none", "Pre-exam file opened")
    if k == Kind.OLD_CODE:
        return _hit("old_code", "high", "none", f"Old code reused · {d.get('pct', 0)}%")
    if k == Kind.USB:
        return _hit("usb", "high", "none", "USB drive inserted")
    if k == Kind.LAN_PEER:
        return _hit("lan_peer", "medium", "none", f"Connection to {d.get('ip', '?')}")
    if k == Kind.EXTENSION:
        names = d.get("names") or []
        return _hit("ai_extension", "medium", "none", f"{', '.join(names)} installed") if names else ALLOW
    return ALLOW
