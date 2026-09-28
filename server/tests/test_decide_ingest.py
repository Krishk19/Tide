import base64
import json

from sqlmodel import select

from tide_server.classify.heuristics import Verdict
from tide_server.decide import decide
from tide_server.models import Event, Flag


def test_decide_table():
    assert decide(Verdict("ai_assistant", 0.96, 0.97, "jev"), True) == ("close_tab", "critical", True)
    assert decide(Verdict("ai_assistant", 0.96, 0.97, "jev"), False).action == "kill"
    assert decide(Verdict("ai_assistant", 0.96, 0.97, "jev", cached=True), True).action == "close_tab"
    assert decide(Verdict("ai_assistant", 0.70, 0.70, "heuristic"), True) == ("none", "medium", True)
    assert decide(Verdict("web_lookup", 0.95, 0.85, "jev"), True) == ("none", "high", True)
    assert decide(Verdict("allowed_tool", 0.99, 0.05, "jev"), False) == ("none", "info", False)


class StubPipeline:
    mode = "jev"

    def __init__(self, verdict):
        self.verdict = verdict

    async def classify(self, signal, apps):
        return self.verdict


POE = {"hwnd": 11, "pid": 22, "process": "chrome.exe", "title": "Poe", "host": "poe.com"}


async def test_unknown_signal_ai_high_confidence_acts(ctx, paired, hub):
    seat, _ = paired
    ctx.pipeline = StubPipeline(Verdict("ai_assistant", 0.96, 0.97, "jev"))
    await ctx.ingest.handle(seat.id, {"t": "signal", "kind": "window", "data": POE, "ts": 1.0})
    with ctx.db() as db:
        f = db.exec(select(Flag)).one()
    assert (f.title, f.source, f.label, f.confidence, f.action) == (
        "poe.com — AI assistant", "jev", "ai_assistant", 0.96, "close_tab")
    sid, act = hub.agent_msgs[-1]
    assert sid == seat.id and act["t"] == "act" and act["action"] == "close_tab"
    assert act["target"] == {"pid": 22, "hwnd": 11, "process": "chrome.exe", "host": "poe.com"}
    assert act["flag_id"] == f.id


async def test_unknown_signal_harmless_is_event_only(ctx, paired, hub):
    seat, _ = paired
    ctx.pipeline = StubPipeline(Verdict("other", 0.9, 0.1, "jev"))
    await ctx.ingest.handle(seat.id, {"t": "signal", "kind": "window",
                                      "data": {"process": "calc.exe", "title": "Calculator"}, "ts": 2.0})
    with ctx.db() as db:
        assert db.exec(select(Flag)).first() is None
        assert db.exec(select(Event)).all()[-1].kind == "window"
    assert hub.agent_msgs == []


async def test_agent_flag_then_evidence_by_ref(ctx, paired, hub):
    seat, _ = paired
    await ctx.ingest.handle(seat.id, {"t": "flag", "ref": "r1", "kind": "blocked_site",
                                      "severity": "critical", "title": "ChatGPT — closed",
                                      "data": {"host": "chatgpt.com"}, "ts": 3.0,
                                      "action": "close_tab", "result": "closed"})
    jpeg = base64.b64encode(b"\xff\xd8fakejpeg").decode()
    await ctx.ingest.handle(seat.id, {"t": "evidence", "ref": "r1", "jpeg_b64": jpeg})
    with ctx.db() as db:
        f = db.exec(select(Flag)).one()
    assert (f.source, f.action, f.screenshot) == ("rule", "close_tab", f"{f.id}.jpg")
    assert (ctx.settings.data_dir / "shots" / f"{f.id}.jpg").read_bytes() == b"\xff\xd8fakejpeg"
    assert json.loads(f.data_json)["result"] == "closed"
    assert [m["t"] for m in hub.console_msgs].count("flag") >= 2   # created, then updated with shot


async def test_event_is_timeline_only(ctx, paired, hub):
    seat, _ = paired
    await ctx.ingest.handle(seat.id, {"t": "event", "kind": "window",
                                      "data": {"process": "Code.exe", "title": "main.c"}, "ts": 4.0})
    assert hub.console_msgs[-1]["t"] == "event"
    assert hub.console_msgs[-1]["event"]["text"] == "VS Code"
