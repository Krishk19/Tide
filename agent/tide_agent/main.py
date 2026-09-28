import asyncio
import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .discovery import discover, parse_server
from .engine import Engine
from .exam_folder import ExamFolder
from .inventory import default_roots
from .link import Link
from .outbox import Outbox
from .pairing import PairError, pair, submit
from .platform import Platform
from .preflight import preflight_checks, preflight_message, run_preflight, running_checks


@dataclass
class AgentConfig:
    server: str | None
    exam_root: Path
    ext_dir: Path
    state_dir: Path
    roots: list[Path] = field(default_factory=list)
    code: str | None = None
    roll: str | None = None
    seat: int | None = None

    @classmethod
    def from_args(cls, args, fake=None) -> "AgentConfig":
        default_root = Path("C:/Exam") if sys.platform == "win32" else Path.home() / "TideExam"
        exam_root = args.exam_root or Path(os.environ.get("TIDE_EXAM_ROOT", default_root))
        state = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Tide"
        return cls(server=args.server or os.environ.get("TIDE_SERVER"), exam_root=exam_root,
                   ext_dir=fake.ext_dir if fake else Path.home() / ".vscode" / "extensions",
                   state_dir=state, roots=[fake.old_dir] if fake else default_roots(),
                   code=args.code, roll=args.roll, seat=args.seat)


class AgentApp:
    def __init__(self, platform: Platform, ui, cfg: AgentConfig) -> None:
        self.p, self.ui, self.cfg = platform, ui, cfg
        self.loop: asyncio.AbstractEventLoop | None = None
        self.server: tuple[str, int] | None = None
        self.engine: Engine | None = None
        self.link: Link | None = None
        self._tasks: list[asyncio.Task] = []

    async def boot(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.server = parse_server(self.cfg.server) if self.cfg.server else await asyncio.to_thread(discover)
        self.ui.show_join(self.server[0] if self.server else None)

    async def join(self, code: str, roll: str, seat_no: int) -> dict:
        if self.engine is not None:
            return {"ok": True}
        if not self.server:
            self.server = await asyncio.to_thread(discover)
            if not self.server:
                return {"ok": False, "error": "Teacher not found. Check the LAN cable."}
        host, port = self.server
        base = f"http://{host}:{port}"
        try:
            r = await pair(base, code, roll, int(seat_no), socket.gethostname())
        except (PairError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        folder = ExamFolder(self.cfg.exam_root / r.roll)
        if hasattr(self.p, "exam_root"):
            self.p.exam_root, self.p.roll = self.cfg.exam_root, r.roll

        async def send(m):
            return await self.link.send(m)

        async def submitter(data, auto):
            await submit(base, r.token, data, auto)

        self.engine = Engine(self.p, self.ui, send, folder, submitter, self.cfg.ext_dir, server_ip=host)
        self.engine.roll = r.roll
        self.link = Link(f"ws://{host}:{port}/ws/agent", r.token, self.engine.on_server,
                         Outbox(self.cfg.state_dir / f"outbox-{r.roll}.jsonl"))
        self.ui.show_preflight(running_checks())
        self._tasks += [asyncio.create_task(self.link.run()), asyncio.create_task(self._preflight_loop()),
                        asyncio.create_task(self.engine.run())]
        return {"ok": True}

    async def _preflight_loop(self) -> None:
        await self.link.connected.wait()
        inventory = None
        while not self.engine.live:
            res = await asyncio.to_thread(run_preflight, self.p, self.cfg.ext_dir, self.cfg.roots,
                                          self.cfg.exam_root, inventory)
            inventory = self.engine.inventory = res.inventory
            self.engine.ext.set_baseline(res.extensions)
            self.ui.show_preflight(preflight_checks(res))
            await self.link.send(preflight_message(res))
            if not res.internet:
                return
            await asyncio.sleep(5)

    # called from the UI thread
    def join_from_ui(self, code, roll, seat) -> dict:
        return asyncio.run_coroutine_threadsafe(self.join(code, roll, seat), self.loop).result(timeout=20)

    def submit_from_ui(self) -> dict:
        asyncio.run_coroutine_threadsafe(self.engine.submit(auto=False), self.loop).result(timeout=60)
        return {"ok": True}

    async def run_forever(self) -> None:
        await self.boot()
        if self.cfg.code and self.cfg.roll and self.cfg.seat:
            result = await self.join(self.cfg.code, self.cfg.roll, self.cfg.seat)
            if not result["ok"]:
                self.ui.error(result["error"])
        while self.engine is None or not self.engine.done:
            await asyncio.sleep(0.5)
        await asyncio.sleep(10)
        self.ui.quit()
