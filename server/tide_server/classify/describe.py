import re
from typing import Sequence

from tide_common.policy import BROWSERS
from tide_common.protocol import Signal


def describe(signal: Signal, apps: Sequence[str]) -> str:
    d = signal.data
    lines = [f"Exam policy: allowed = {', '.join(apps)}. Browsers may only show local files.",
             f"Event: {signal.kind}",
             f"  process: {d.get('process', '')}  ({d.get('description') or d.get('original_name') or ''})",
             f'  title:   "{d.get("title", "")}"']
    if d.get("host") is not None:
        lines.append(f"  host:    {d.get('host')}")
    return "\n".join(lines)


def cache_key(signal: Signal) -> str:
    d = signal.data
    process = (d.get("process") or "").lower()
    if process in BROWSERS and d.get("host"):
        return f"{process}|{d['host'].lower()}"
    title = re.sub(r"\d+", "#", (d.get("title") or "").lower())[:80]
    return f"{process}|{title}"
