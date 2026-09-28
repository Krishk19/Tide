from tide_server.burst import burst_lines
from tide_server.models import Snapshot
from tide_server.similarity import count_lines, total_lines
from tide_server.exam_service import go_live
from tide_server.live import deliver
import base64
import json

from sqlmodel import select

from tide_common.policy import BROWSERS
from tide_common.protocol import Signal, msg

from tide_server.classify.heuristics import LABEL_TEXT
from tide_server.decide import decide
from tide_server.live import push_flag, raise_flag
from tide_server.models import Exam, Flag
from tide_server.serialize import exam_policy
"""Everything an agent says, in one place. One `_on_<type>` method per message type."""
from typing import Any

from tide_common.policy import display_app

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.live import add_event, push_event, push_seat
from tide_server.models import Seat


def display_name(data: dict) -> str:
    if data.get("host"):
        return data["host"]
    process = data.get("process") or ""
    return display_app(process) if process else (data.get("title") or "Unknown")[:40]


class Ingest:
    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx

    async def handle(self, seat_id: int, m: dict[str, Any]) -> None:
        handler = getattr(self, f"_on_{m.get('t')}", None)
        if handler is not None:
            await handler(seat_id, m)

    async def _on_heartbeat(self, seat_id: int, m: dict[str, Any]) -> None:
        t = clock.now()
        with self.ctx.db() as db:
            seat = db.get(Seat, seat_id)
            was_offline = seat.state == "offline"
            gap = int(t - seat.last_seen)
            app_name = display_app(m.get("fg") or "") if m.get("fg") else seat.fg_app
            changed = was_offline or app_name != seat.fg_app
            seat.last_seen = t
            seat.fg_app = app_name
            if was_offline:
                seat.state = seat.resume_state or "live"
                seat.resume_state = ""
            db.add(seat)
            db.commit()
        if was_offline:
            await push_event(self.ctx, add_event(self.ctx, seat_id, "agent_back", {"gap": gap}))
        if changed:
            await push_seat(self.ctx, seat_id)


    async def _on_event(self, seat_id: int, m: dict[str, Any]) -> None:
        e = add_event(self.ctx, seat_id, m.get("kind", "event"), m.get("data") or {}, m.get("ts"))
        await push_event(self.ctx, e)

    async def _on_flag(self, seat_id: int, m: dict[str, Any]) -> None:
        data = dict(m.get("data") or {})
        if m.get("result"):
            data["result"] = m["result"]
        await raise_flag(self.ctx, seat_id, kind=m["kind"], severity=m["severity"], title=m["title"],
                         source="rule", data=data, action=m.get("action", "none"),
                         ref=m.get("ref"), ts=m.get("ts"))

    async def _on_signal(self, seat_id: int, m: dict[str, Any]) -> None:
        sig = Signal(kind=m["kind"], data=m.get("data") or {}, ts=m.get("ts") or clock.now())
        with self.ctx.db() as db:
            seat = db.get(Seat, seat_id)
            apps = exam_policy(db.get(Exam, seat.exam_id)).apps
        verdict = await self.ctx.pipeline.classify(sig, apps)
        is_browser = (sig.data.get("process") or "").lower() in BROWSERS
        d = decide(verdict, is_browser, self.ctx.settings.auto_act_min)
        if not d.flag:
            await push_event(self.ctx, add_event(self.ctx, seat_id, sig.kind, sig.data, sig.ts))
            return
        title = f"{display_name(sig.data)} — {LABEL_TEXT.get(verdict.label, verdict.label)}"
        flag = await raise_flag(self.ctx, seat_id, kind="jev" if verdict.source == "jev" else "heuristic",
                                severity=d.severity, title=title, source=verdict.source,
                                data={**sig.data, "verdict": verdict.raw or {}}, action=d.action,
                                label=verdict.label, confidence=verdict.confidence, ts=sig.ts)
        if d.action != "none":
            target = {k: sig.data.get(k) for k in ("pid", "hwnd", "process", "host")}
            await self.ctx.hub.to_agent(seat_id, msg("act", action=d.action, target=target,
                                                     reason=title, flag_id=flag.id))

    async def _on_evidence(self, seat_id: int, m: dict[str, Any]) -> None:
        with self.ctx.db() as db:
            if m.get("flag_id"):
                flag = db.get(Flag, m["flag_id"])
            else:
                flag = db.exec(select(Flag).where(Flag.seat_id == seat_id, Flag.ref == m.get("ref"))).first()
            if flag is None or flag.seat_id != seat_id:
                return
            shots = self.ctx.settings.data_dir / "shots"
            shots.mkdir(parents=True, exist_ok=True)
            (shots / f"{flag.id}.jpg").write_bytes(base64.b64decode(m["jpeg_b64"]))
            flag.screenshot = f"{flag.id}.jpg"
            db.add(flag)
            db.commit()
            flag_id = flag.id
        await push_flag(self.ctx, flag_id)

    async def _on_preflight(self, seat_id: int, m: dict[str, Any]) -> None:
        go = False
        with self.ctx.db() as db:
            seat = db.get(Seat, seat_id)
            exam = db.get(Exam, seat.exam_id)
            seat.preflight_json = json.dumps({k: m.get(k) for k in
                                              ("internet", "extensions", "denied_closed", "inventory_count")})
            if seat.state in ("lobby", "ready", "blocked"):
                if m.get("internet"):
                    seat.state = "blocked"
                elif exam.state == "live":
                    go_live(db, exam, seat)
                    go = True
                else:
                    seat.state = "ready"
            db.add(seat)
            db.commit()
            had_ext_flag = db.exec(select(Flag).where(Flag.seat_id == seat_id,
                                                      Flag.kind == "ai_extension")).first() is not None
        if m.get("extensions") and not had_ext_flag:
            await raise_flag(self.ctx, seat_id, kind="ai_extension", severity="medium",
                             title=f"{', '.join(m['extensions'])} installed", source="rule",
                             data={"names": m["extensions"]})
        for name in m.get("denied_closed") or []:
            await push_event(self.ctx, add_event(self.ctx, seat_id, "denied_closed", {"name": name}))
        await push_seat(self.ctx, seat_id)
        if go:
            await deliver(self.ctx, seat_id)

    async def _on_snapshot(self, seat_id: int, m: dict[str, Any]) -> None:
        ts = m.get("ts") or clock.now()
        with self.ctx.db() as db:
            before = total_lines(db, seat_id)
            for f in m.get("files") or []:
                text = f.get("text") or ""
                db.add(Snapshot(seat_id=seat_id, ts=ts, path=f["path"], sha=f.get("sha", ""),
                                text=text, line_count=count_lines(text)))
            db.commit()
            after = total_lines(db, seat_id)
        n = burst_lines(before, after)
        if n:
            await raise_flag(self.ctx, seat_id, kind="code_burst", severity="medium",
                             title=f"Code burst · +{n} lines", source="server", data={"lines": n}, ts=ts)
