"""Each watcher turns OS state into Signals. poll() is sync and cheap; the engine runs it in a thread."""
import time
from pathlib import Path
from typing import Callable

from tide_common.policy import AI_EXTENSIONS, BROWSERS, CLIPBOARD_MIN
from tide_common.protocol import Kind, Signal

from .inventory import Inventory
from .platform import AdapterInfo, Platform


class WindowWatcher:
    def __init__(self, p: Platform) -> None:
        self.p = p
        self._last: tuple | None = None
        self._host_key: tuple | None = None
        self._host: str | None = None
        self.current_process = ""

    def poll(self) -> list[Signal]:
        w = self.p.foreground()
        if w is None:
            return []
        self.current_process = w.process
        host = None
        if w.process.lower() in BROWSERS:
            if self._host_key != (w.hwnd, w.title):
                self._host_key = (w.hwnd, w.title)
                self._host = self.p.browser_host(w.hwnd, w.process)
            host = self._host
        key = (w.hwnd, w.process.lower(), w.title, host)
        if key == self._last:
            return []
        self._last = key
        return [Signal(kind=Kind.WINDOW, data={
            "hwnd": w.hwnd, "pid": w.pid, "process": w.process, "exe": w.exe, "title": w.title,
            "description": w.description, "original_name": w.original_name, "host": host})]


class ProcessWatcher:
    def __init__(self, p: Platform) -> None:
        self.p = p
        self._seen: set[int] = set()

    def poll(self) -> list[Signal]:
        procs = self.p.processes()
        new = [pi for pid, pi in procs.items() if pid not in self._seen]
        self._seen = set(procs)
        return [Signal(kind=Kind.PROCESS, data={"pid": pi.pid, "process": pi.name, "exe": pi.exe,
                                                "description": pi.description,
                                                "original_name": pi.original_name}) for pi in new]


def _via(ads: dict[str, AdapterInfo], new_up: list[str]) -> str:
    candidates = [ads[n] for n in new_up] + [a for a in ads.values() if a.up and a.wifi]
    for a in candidates:
        if a.wifi and a.ssid:
            return f"Wi-Fi “{a.ssid}”"
        return a.name
    return "network"


class NetworkWatcher:
    def __init__(self, p: Platform, probe_every_s: float = 5.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.p, self.probe_every_s, self.clock = p, probe_every_s, clock
        self._up: set[str] | None = None
        self._internet: bool | None = None
        self._last_probe = float("-inf")

    def poll(self) -> list[Signal]:
        now = self.clock()
        ads = self.p.adapters()
        up = {n for n, a in ads.items() if a.up}
        new_up = sorted(up - self._up) if self._up is not None else []
        self._up = up
        if not new_up and now - self._last_probe < self.probe_every_s:
            return []
        self._last_probe = now
        internet = self.p.internet()
        if internet == self._internet:
            return []
        self._internet = internet
        return [Signal(kind=Kind.NETWORK, data={"internet": internet, "via": _via(ads, new_up),
                                                "adapters": sorted(up)})]


class LanWatcher:
    def __init__(self, p: Platform, server_ip: str) -> None:
        self.p, self.server_ip = p, server_ip
        self._seen: set[str] = set()

    def poll(self) -> list[Signal]:
        out = []
        for peer in self.p.lan_peers(self.server_ip):
            if peer.ip not in self._seen:
                self._seen.add(peer.ip)
                out.append(Signal(kind=Kind.LAN_PEER, data={"ip": peer.ip, "port": peer.port,
                                                            "process": peer.process}))
        return out


class UsbWatcher:
    def __init__(self, p: Platform) -> None:
        self.p = p
        self._seen: set[str] | None = None

    def poll(self) -> list[Signal]:
        drives = self.p.removable_drives()
        new = sorted(drives - self._seen) if self._seen is not None else []
        self._seen = drives
        return [Signal(kind=Kind.USB, data={"drive": d}) for d in new]


class ClipboardWatcher:
    def __init__(self, p: Platform, exam_texts: Callable[[], dict[str, str]],
                 inventory: Callable[[], Inventory | None]) -> None:
        self.p, self.exam_texts, self.inventory = p, exam_texts, inventory
        self._seq: int | None = None

    def poll(self) -> list[Signal]:
        seq = self.p.clipboard_seq()
        if seq == self._seq:
            return []
        first = self._seq is None
        self._seq = seq
        if first:
            return []
        text = self.p.clipboard_text() or ""
        if len(text) < CLIPBOARD_MIN:
            return []
        snippet = text.strip()
        if any(snippet in t for t in self.exam_texts().values()):
            return []
        data = {"length": len(text), "preview": text[:120]}
        inv = self.inventory()
        match = inv.best_match(text) if inv else None
        if match:
            data["match_path"], data["match_pct"] = match
        return [Signal(kind=Kind.CLIPBOARD, data=data)]


def scan_extensions(ext_dir: Path) -> list[str]:
    if not ext_dir.is_dir():
        return []
    found = set()
    for child in ext_dir.iterdir():
        low = child.name.lower()
        for prefix, name in AI_EXTENSIONS.items():
            if child.is_dir() and low.startswith(prefix):
                found.add(name)
    return sorted(found)


class ExtensionWatcher:
    def __init__(self, ext_dir: Path) -> None:
        self.ext_dir = ext_dir
        self._known: set[str] = set()

    def set_baseline(self, names: list[str]) -> None:
        self._known = set(names)

    def poll(self) -> list[Signal]:
        new = [n for n in scan_extensions(self.ext_dir) if n not in self._known]
        self._known.update(new)
        return [Signal(kind=Kind.EXTENSION, data={"names": new})] if new else []
