import base64

from tide_common.policy import PRESETS, Policy
from tide_common.protocol import Kind, Signal
from tide_agent.engine import Engine
from tide_agent.enforcer import Enforcer
from tide_agent.exam_folder import ExamFolder
from tide_agent.inventory import build_inventory
from tide_agent.platform import WindowInfo
from fakes import FakePlatform


class RecUI:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a))


def make(tmp_path, p=None):
    p = p or FakePlatform()
    ui, sent, submitted = RecUI(), [], []

    async def send(m):
        sent.append(m)
        return True

    async def submitter(data, auto):
        submitted.append((data, auto))

    e = Engine(p, ui, send, ExamFolder(tmp_path / "Exam" / "22BCS107"), submitter,
               tmp_path / "ext", server_ip="10.10.0.1")
    e.policy = Policy.from_apps(PRESETS["networking"])
    e.roll = "22BCS107"
    return e, p, ui, sent, submitted


def test_enforcer_close_tab_then_kill_if_still_there():
    p, ui = FakePlatform(), RecUI()
    p.hosts[5] = "chatgpt.com"
    r = Enforcer(p, ui, sleep=lambda s: None).act("close_tab", {"hwnd": 5, "pid": 9, "process": "chrome.exe",
                                                               "host": "chatgpt.com"}, "ChatGPT — closed")
    assert r == "killed_browser" and p.closed_tabs == [5] and p.killed == [9]
    assert ui.calls[-1] == ("block", ("ChatGPT — closed", False))


async def test_blocked_site_screenshot_before_close_and_flag(tmp_path):
    e, p, ui, sent, _ = make(tmp_path)
    order = []
    p.screenshot = lambda: order.append("shot") or b"\xff\xd8"
    p.close_tab = lambda hwnd: order.append("close")
    await e.on_signal(Signal(kind=Kind.WINDOW, data={"hwnd": 3, "pid": 4, "process": "chrome.exe",
                                                     "title": "ChatGPT", "host": "chatgpt.com"}))
    assert order == ["shot", "close"]
    flag, evidence = sent
    assert flag["t"] == "flag" and flag["title"] == "ChatGPT — closed" and flag["result"] == "closed"
    assert evidence == {"t": "evidence", "ref": flag["ref"], "jpeg_b64": base64.b64encode(b"\xff\xd8").decode()}


async def test_unknown_window_goes_to_server_allowed_is_event(tmp_path):
    e, *_, sent, _ = make(tmp_path)
    await e.on_signal(Signal(kind=Kind.WINDOW, data={"process": "chrome.exe", "title": "Poe", "host": "poe.com"}))
    await e.on_signal(Signal(kind=Kind.WINDOW, data={"process": "Code.exe", "title": "main.c - 22BCS107"}))
    await e.on_signal(Signal(kind=Kind.PROCESS, data={"pid": 1, "process": "svchost.exe"}))
    assert [m["t"] for m in sent] == ["signal", "event"]


async def test_internet_overlay_is_persistent_until_offline_even_without_server(tmp_path):
    """Review focus #4: enforcement is local; send() failing doesn't matter."""
    e, p, ui, sent, _ = make(tmp_path)

    async def offline_send(m):
        return False
    e.send = offline_send
    await e.on_signal(Signal(kind=Kind.NETWORK, data={"internet": True, "via": "Wi-Fi “Redmi”"}))
    assert ("block", ("Internet via Wi-Fi “Redmi”", True)) in ui.calls
    await e.on_signal(Signal(kind=Kind.NETWORK, data={"internet": False}))
    assert ui.calls[-1][0] == "unblock"


async def test_file_open_and_old_code(tmp_path):
    old = tmp_path / "D" / "old"
    old.mkdir(parents=True)
    code = "\n".join(f"int f{i}(int x) {{ return x * {i} + {i}; }}" for i in range(20))
    (old / "main.c").write_text(code)
    (old / "dsa_lab5.cpp").write_text(code)
    e, p, ui, sent, _ = make(tmp_path)
    e.inventory = build_inventory([tmp_path / "D"])
    # Review focus #3: the exam's own main.c (title contains the roll) is not "old"
    await e.on_signal(Signal(kind=Kind.WINDOW, data={"process": "Code.exe", "title": "main.c - 22BCS107 - Visual Studio Code"}))
    await e.on_signal(Signal(kind=Kind.WINDOW, data={"process": "Code.exe", "title": "dsa_lab5.cpp - old - Visual Studio Code"}))
    titles = [m["title"] for m in sent if m["t"] == "flag"]
    assert titles == ["Pre-exam file opened"]
    e.live = True
    e.folder.write_files([("main.c", b"int main(){}")])
    (e.folder.root / "main.c").write_text(code.replace("x", "y"))
    await e.snapshot()
    kinds = [m.get("kind") or m["t"] for m in sent[-3:]]
    assert "snapshot" in kinds and "old_code" in kinds


async def test_server_messages(tmp_path):
    e, p, ui, sent, submitted = make(tmp_path)
    await e.on_server({"t": "welcome", "_offset": 10.0, "seat_no": 7, "roll": "22BCS107", "set": None,
                       "policy": Policy.from_apps(["VS Code"]).to_dict(), "exam_state": "lobby", "ends_at": None})
    assert e.policy.apps == ("VS Code",)
    await e.on_server({"t": "start", "set": "A", "ends_at": 1010.0,
                       "files": [{"name": "q.txt", "b64": base64.b64encode(b"Q").decode()}]})
    assert (e.folder.root / "q.txt").read_bytes() == b"Q" and e.live
    assert ui.calls[-1][0] == "start" and ui.calls[-1][1][2] == 1000.0
    p.hosts[8] = "chatgpt.com"
    await e.on_server({"t": "act", "action": "kill", "target": {"pid": 77}, "reason": "NoteGPT — AI assistant", "flag_id": 5})
    assert p.killed == [77] and sent[-1]["t"] == "evidence" and sent[-1]["flag_id"] == 5
    await e.on_server({"t": "end", "reason": "time"})
    assert submitted and submitted[0][1] is True and e.done
    assert ui.calls[-1][0] == "done"
