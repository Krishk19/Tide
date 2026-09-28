"""Everything the agent needs from the OS. WinPlatform (win/) is real; FakePlatform (fake.py) is for dev and tests."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    process: str
    exe: str
    title: str
    description: str = ""
    original_name: str = ""


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    name: str
    exe: str = ""
    description: str = ""
    original_name: str = ""


@dataclass(frozen=True)
class AdapterInfo:
    name: str
    up: bool
    wifi: bool = False
    ssid: str | None = None


@dataclass(frozen=True)
class Peer:
    ip: str
    port: int
    process: str = ""


class Platform(Protocol):
    def foreground(self) -> WindowInfo | None: ...
    def browser_host(self, hwnd: int, process: str) -> str | None: ...
    def processes(self) -> dict[int, ProcInfo]: ...
    def kill(self, pid: int) -> None: ...
    def adapters(self) -> dict[str, AdapterInfo]: ...
    def internet(self) -> bool: ...
    def lan_peers(self, server_ip: str) -> list[Peer]: ...
    def removable_drives(self) -> set[str]: ...
    def clipboard_seq(self) -> int: ...
    def clipboard_text(self) -> str | None: ...
    def close_tab(self, hwnd: int) -> None: ...
    def screenshot(self) -> bytes | None: ...
