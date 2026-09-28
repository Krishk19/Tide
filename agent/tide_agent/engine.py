"""The agent's brain: watchers -> rules -> act locally / tell the server. Server messages come back here."""
import asyncio
import base64
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from tide_common.policy import Policy
from tide_common.protocol import SEVERITY_RANK, Kind, Signal, msg
from tide_common.rules import RuleHit, evaluate

from .clock import ServerClock
from .enforcer import Enforcer
from .exam_folder import ExamFolder
from .inventory import Inventory
from .platform import Platform
from .ui.port import UiPort
from .watchers import (ClipboardWatcher, ExtensionWatcher, LanWatcher, NetworkWatcher, ProcessWatcher,
                       UsbWatcher, WindowWatcher)

TICK_S = 0.5


class Engine:
    def __init__(self, p: Platform, ui: UiPort, send: Callable[[dict], Awaitable[bool]], folder: ExamFolder,
                 submitter: Callable[[bytes, bool], Awaitable[None]], ext_dir: Path, server_ip: str,
                 clock: ServerClock | None = None) -> None:
        self.p, self.ui, self.send, self.folder, self.submitter = p, ui, send, folder, submitter
        self.clock = clock or ServerClock()
        self.policy = Policy.from_apps([])
        self.enforcer = Enforcer(p, ui)
        self.inventory: Inventory | None = None
        self.seat_no, self.roll, self.set_name = 0, "", None
        self.live = False
        self.done = False
        self._reported: set[str] = set()
        self.window = WindowWatcher(p)
        self.procs = ProcessWatcher(p)
        self.net = NetworkWatcher(p)
        self.lan = LanWatcher(p, server_ip)
        self.usb = UsbWatcher(p)
        self.clip = ClipboardWatcher(p, folder.texts, lambda: self.inventory)
        self.ext = ExtensionWatcher(ext_dir)

    # ---- signals -------------------------------------------------------------------------------
    async def on_signal(self, sig: Signal) -> None:
        if self.done:
            return
        r = evaluate(sig, self.policy)
        if r.status == "hit":
            await self._hit(r.hit, sig)
            return
        if sig.kind == Kind.NETWORK and not sig.data.get("internet"):
            self.ui.unblock()
        if r.status == "unknown":
            if sig.kind == Kind.WINDOW:
                await self.send(msg("signal", kind=sig.kind, data=sig.data, ts=self.clock.now()))
            return
        if sig.kind in (Kind.WINDOW, Kind.NETWORK):
            await self.send(msg("event", kind=sig.kind, data=sig.data, ts=self.clock.now()))
        if sig.kind == Kind.WINDOW:
            await self._check_title(sig)

    async def _hit(self, hit: RuleHit, sig: Signal) -> None:
        shot = await asyncio.to_thread(self.p.screenshot) if SEVERITY_RANK[hit.severity] >= 1 else None
        target = {k: sig.data.get(k) for k in ("pid", "hwnd", "process", "host")}
        result = await asyncio.to_thread(self.enforcer.act, hit.action, target, hit.title, hit.kind == "internet")
        ref = uuid.uuid4().hex
        await self.send(msg("flag", ref=ref, kind=hit.kind, severity=hit.severity, title=hit.title,
                            data=sig.data, ts=self.clock.now(), action=hit.action, result=result))
        if shot:
            await self.send(msg("evidence", ref=ref, jpeg_b64=base64.b64encode(shot).decode()))

    async def _check_title(self, sig: Signal) -> None:
        title = sig.data.get("title") or ""
        if not self.inventory or (self.roll and self.roll.lower() in title.lower()):
            return
        path = self.inventory.match_title(title)
        if path and f"open:{path}" not in self._reported:
            self._reported.add(f"open:{path}")
            await self.on_signal(Signal(kind=Kind.FILE_OPEN, data={"path": path, "title": title}))

    # ---- server --------------------------------------------------------------------------------
    async def on_server(self, m: dict) -> None:
        t = m.get("t")
        if t == "welcome":
            self.clock.offset = m.get("_offset", 0.0)
            self.policy = Policy.from_dict(m.get("policy") or {})
            self.seat_no, self.roll = m.get("seat_no", 0), m.get("roll", "")
            if m.get("exam_state") == "live" and m.get("ends_at"):
                self.ui.set_ends_at(self.clock.to_local(m["ends_at"]))
        elif t == "start":
            files = [(f["name"], base64.b64decode(f["b64"])) for f in m.get("files") or []]
            await asyncio.to_thread(self.folder.write_files, files)
            first = not self.live
            self.set_name, self.live = m.get("set"), True
            if first:
                self.ui.start(self.seat_no, self.set_name, self.clock.to_local(m["ends_at"]), str(self.folder.root))
            else:
                self.ui.set_ends_at(self.clock.to_local(m["ends_at"]))
        elif t == "time":
            self.ui.set_ends_at(self.clock.to_local(m["ends_at"]))
        elif t == "notice":
            self.ui.notice(m.get("text", ""))
        elif t == "act":
            shot = await asyncio.to_thread(self.p.screenshot)
            await asyncio.to_thread(self.enforcer.act, m["action"], m.get("target") or {}, m.get("reason", ""))
            if shot:
                await self.send(msg("evidence", flag_id=m.get("flag_id"), jpeg_b64=base64.b64encode(shot).decode()))
        elif t == "end":
            await self.submit(auto=True)
        elif t == "auth_failed":
            self.ui.error("This seat was joined from another PC. Ask the invigilator.")

    # ---- loop ----------------------------------------------------------------------------------
    def _slow_polls(self) -> list[Signal]:
        return self.procs.poll() + self.net.poll() + self.lan.poll() + self.usb.poll()

    async def tick(self, n: int) -> None:
        if self.done:
            return
        sigs = await asyncio.to_thread(self.window.poll)
        if n % 2 == 0:
            sigs += await asyncio.to_thread(self.clip.poll)
        if n % 4 == 0:
            sigs += await asyncio.to_thread(self._slow_polls)
        if n % 120 == 0:
            sigs += await asyncio.to_thread(self.ext.poll)
        for s in sigs:
            await self.on_signal(s)
        if n % 6 == 0:
            await self.send(msg("heartbeat", fg=self.window.current_process))
        if self.live and n % 60 == 59:
            await self.snapshot()

    async def snapshot(self) -> None:
        files = await asyncio.to_thread(self.folder.changed_files)
        if not files:
            return
        await self.send(msg("snapshot", ts=self.clock.now(), files=files))
        if self.inventory is None:
            return
        for f in files:
            match = self.inventory.best_match(f["text"])
            if match and f"old:{match[0]}" not in self._reported:
                self._reported.add(f"old:{match[0]}")
                await self.on_signal(Signal(kind=Kind.OLD_CODE, data={"exam_path": f["path"],
                                                                      "source_path": match[0], "pct": match[1]}))

    async def run(self) -> None:
        n = 0
        while not self.done:
            try:
                await self.tick(n)
            except Exception as e:     # a flaky OS call must never stop the watchers
                print(f"[engine] {e!r}")
            n += 1
            await asyncio.sleep(TICK_S)

    async def submit(self, auto: bool) -> None:
        if self.done:
            return
        self.done = True
        await self.snapshot()
        data = await asyncio.to_thread(self.folder.zip_bytes)
        for attempt in range(3):
            try:
                await self.submitter(data, auto)
                self.ui.done(self.folder.file_count(), time.strftime("%H:%M"))
                return
            except Exception as e:
                self.ui.error(f"Submit failed, retrying… ({e})")
                await asyncio.sleep(2)
        self.done = False
        self.ui.error("Submit failed. Tell the invigilator — your files are safe in the exam folder.")
