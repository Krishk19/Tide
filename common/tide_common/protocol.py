"""Wire protocol shared by agent and server. See docs/ARCHITECTURE.md §6."""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "medium", "high", "critical"]
Action = Literal["none", "close_tab", "kill", "overlay"]
SEVERITY_RANK: dict[str, int] = {"info": 0, "medium": 1, "high": 2, "critical": 3}


class Kind:
    WINDOW = "window"          # hwnd, pid, process, exe, title, description, original_name, host
    PROCESS = "process"        # pid, process, exe, description, original_name
    NETWORK = "network"        # internet: bool, via: str, adapters: list[str]
    LAN_PEER = "lan_peer"      # ip, port, process
    USB = "usb"                # drive
    CLIPBOARD = "clipboard"    # length, preview, match_path?, match_pct?
    FILE_OPEN = "file_open"    # path, title
    OLD_CODE = "old_code"      # exam_path, source_path, pct
    EXTENSION = "extension"    # names: list[str]


class Signal(BaseModel):
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)


def msg(t: str, **payload: Any) -> dict[str, Any]:
    return {"t": t, **payload}
