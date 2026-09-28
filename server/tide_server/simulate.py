"""Demo mode: 59 believable seats around the one real laptop (seat 7)."""
import asyncio
import json
import random
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from tide_common.policy import PRESETS

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.exam_service import add_file, create_exam, current_exam, go_live
from tide_server.live import push_seat, raise_flag
from tide_server.models import Exam, Flag, Seat, Snapshot
from tide_server.serialize import exam_policy

SIM_APPS = ["VS Code", "VS Code", "VS Code", "Wireshark", "Terminal", "CodeBlocks", "VMware", "Explorer"]
LATE_JOIN_S = {58: 4.0, 59: 8.0, 60: 12.0}
ASSETS = Path(__file__).parent / "demo_assets"

COPY_A = "\n".join(["#include <stdio.h>", "int main() {", "  int n, total = 0, x;", '  scanf("%d", &n);',
                    "  for (int i = 0; i < n; i++) {", '    scanf("%d", &x);',
                    "    if (x % 2 == 0) total += x; else total -= x;", "  }",
                    '  printf("%d\\n", total);', "  return 0;", "}"])
COPY_B = COPY_A.replace("total", "acc").replace("x", "val")


@dataclass(frozen=True)
class ScriptItem:
    at_s: float
    seat_no: int
    kind: str
    severity: str
    title: str
    source: str = "rule"
    label: str | None = None
    confidence: float | None = None
    action: str = "none"


SCRIPT = [
    ScriptItem(20, 14, "usb", "high", "USB drive inserted"),
    ScriptItem(35, 41, "blocked_site", "critical", "Claude — closed", action="close_tab"),
    ScriptItem(50, 23, "code_burst", "medium", "Code burst · +61 lines", source="server"),
    ScriptItem(65, 29, "lan_peer", "medium", "Connection to 10.10.0.30"),
    ScriptItem(80, 52, "jev", "medium", "NoteGPT — AI assistant", source="jev",
               label="ai_assistant", confidence=0.74),
    ScriptItem(95, 36, "agent_offline", "critical", "Agent offline", source="server"),
]


def seed_room(db: Session, exam: Exam, real_seat_no: int = 7, n: int = 60) -> None:
    t = clock.now()
    for no in range(1, n + 1):
        if no == real_seat_no:
            continue
        state = "lobby" if no in LATE_JOIN_S else "ready"
        pre = {"internet": False, "extensions": [], "denied_closed": [], "inventory_count": 40 + no}
        if no == 19 and exam_policy(exam).internet_blocked:
            state, pre["internet"] = "blocked", True
        seat = Seat(exam_id=exam.id, seat_no=no, roll=f"22BCS{100 + no}", state=state, simulated=True,
                    last_seen=t, fg_app=SIM_APPS[no % len(SIM_APPS)], preflight_json=json.dumps(pre))
        db.add(seat)
        db.commit()
        db.refresh(seat)
        if no == 45:
            db.add(Flag(seat_id=seat.id, ts=t, kind="ai_extension", severity="medium",
                        title="GitHub Copilot installed", source="rule"))
        if no in (14, 16):
            text = COPY_A if no == 14 else COPY_B
            db.add(Snapshot(seat_id=seat.id, ts=t, path="main.c", sha=str(no), text=text,
                            line_count=len(text.splitlines())))
    db.commit()


def bootstrap_demo(ctx: Ctx, mock_room: bool = False) -> int:
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None or exam.state == "ended":
            exam = create_exam(db, "CN Lab Test 3", 90 * 60, list(PRESETS["networking"]))
            for set_name in ("A", "B"):
                for f in sorted((ASSETS / f"set_{set_name}").iterdir()):
                    add_file(db, exam.id, set_name, f.name, f.read_bytes())
        if mock_room and db.exec(select(Seat).where(Seat.exam_id == exam.id,
                                                    Seat.simulated == True)).first() is None:  # noqa: E712
            seed_room(db, exam)
        return exam.id


class SimRoom:
    """Fills the current exam with 59 simulated students (the --mock room)."""

    def __init__(self, ctx: Ctx, exam_id: int | None = None, rng: random.Random | None = None) -> None:
        self.ctx, self.exam_id = ctx, exam_id
        self.rng = rng or random.Random(7)
        self.boot_at = clock.now()
        self.fired: set[int] = set()

    def _follow_current_exam(self) -> None:
        with self.ctx.db() as db:
            exam = current_exam(db)
            if exam is None or exam.id == self.exam_id:
                return
            if db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.simulated == True)).first() is None:  # noqa: E712
                seed_room(db, exam)
            self.exam_id, self.boot_at, self.fired = exam.id, clock.now(), set()

    async def tick(self) -> None:
        self._follow_current_exam()
        if self.exam_id is None:
            return
        t = clock.now()
        changed: list[int] = []
        with self.ctx.db() as db:
            exam = db.get(Exam, self.exam_id)
            seats = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.simulated == True)).all()  # noqa: E712
            for s in seats:
                if s.state != "offline":
                    s.last_seen = t
                if s.state == "lobby" and t - self.boot_at >= LATE_JOIN_S.get(s.seat_no, 1e9):
                    s.state = "ready"
                    changed.append(s.id)
                if exam.state == "live" and s.state == "ready":
                    go_live(db, exam, s)
                    changed.append(s.id)
                db.add(s)
            for s in self.rng.sample(list(seats), k=min(3, len(seats))):
                if s.state in ("ready", "live"):
                    s.fg_app = self.rng.choice(SIM_APPS)
                    db.add(s)
                    changed.append(s.id)
            db.commit()
            by_no = {s.seat_no: s.id for s in seats}
            started = exam.started_at if exam.state == "live" else None
        for seat_id in dict.fromkeys(changed):
            await push_seat(self.ctx, seat_id)
        if started is None:
            return
        for i, item in enumerate(SCRIPT):
            if i in self.fired or t - started < item.at_s or item.seat_no not in by_no:
                continue
            self.fired.add(i)
            seat_id = by_no[item.seat_no]
            if item.kind == "agent_offline":
                with self.ctx.db() as db:
                    s = db.get(Seat, seat_id)
                    s.resume_state, s.state = s.state, "offline"
                    db.add(s)
                    db.commit()
            await raise_flag(self.ctx, seat_id, kind=item.kind, severity=item.severity, title=item.title,
                             source=item.source, label=item.label, confidence=item.confidence,
                             action=item.action)


async def run_sim(room: SimRoom, interval: float = 3.0) -> None:
    while True:
        try:
            await room.tick()
        except Exception as e:
            print(f"[sim] {e!r}")
        await asyncio.sleep(interval)
