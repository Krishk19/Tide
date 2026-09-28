from tide_common.policy import Policy, PRESETS
from tide_common.protocol import Signal, Kind
from tide_common.rules import evaluate

POLICY = Policy.from_apps(PRESETS["networking"])


def win(process, title="", host=None, original_name=""):
    return Signal(kind=Kind.WINDOW, data={"hwnd": 1, "pid": 2, "process": process, "title": title,
                                         "host": host, "original_name": original_name})


def test_denied_host_closes_tab():
    r = evaluate(win("chrome.exe", "ChatGPT", "chatgpt.com"), POLICY)
    assert r.status == "hit"
    assert (r.hit.kind, r.hit.severity, r.hit.action, r.hit.title) == (
        "blocked_site", "critical", "close_tab", "ChatGPT — closed")


def test_unknown_host_goes_to_classifier():
    assert evaluate(win("chrome.exe", "Poe", "poe.com"), POLICY).status == "unknown"


def test_unreadable_address_bar_is_unknown_not_allowed():
    assert evaluate(win("msedge.exe", "Untitled", None), POLICY).status == "unknown"


def test_empty_address_bar_is_allowed():
    assert evaluate(win("chrome.exe", "New Tab", ""), POLICY).status == "allow"


def test_allowed_app():
    assert evaluate(win("Code.exe", "main.c - 22BCS107 - Visual Studio Code"), POLICY).status == "allow"


def test_unknown_app_is_unknown():
    assert evaluate(win("notegpt.exe", "NoteGPT"), POLICY).status == "unknown"


def test_denied_app_by_renamed_original_name_is_killed():
    r = evaluate(win("homework.exe", "Chat", original_name="ChatGPT.exe"), POLICY)
    assert (r.hit.kind, r.hit.action, r.hit.title) == ("denied_app", "kill", "ChatGPT — closed")


def test_process_signal_only_matters_when_denied():
    ok = Signal(kind=Kind.PROCESS, data={"pid": 5, "process": "svchost.exe", "original_name": ""})
    bad = Signal(kind=Kind.PROCESS, data={"pid": 6, "process": "WhatsApp.exe", "original_name": ""})
    assert evaluate(ok, POLICY).status == "allow"
    assert evaluate(bad, POLICY).hit.action == "kill"


def test_internet_is_allowed_by_default():
    assert evaluate(Signal(kind=Kind.NETWORK, data={"internet": True, "via": "Wi-Fi"}), POLICY).status == "allow"


def test_internet_overlays_when_blocked_and_offline_allows():
    blocked = Policy.from_apps(PRESETS["networking"], internet="blocked")
    on = evaluate(Signal(kind=Kind.NETWORK, data={"internet": True, "via": "Wi-Fi “Redmi”"}), blocked)
    assert (on.hit.kind, on.hit.severity, on.hit.action, on.hit.title) == (
        "internet", "critical", "overlay", "Internet via Wi-Fi “Redmi”")
    assert evaluate(Signal(kind=Kind.NETWORK, data={"internet": False}), blocked).status == "allow"


def test_clipboard_thresholds():
    small = Signal(kind=Kind.CLIPBOARD, data={"length": 50})
    big = Signal(kind=Kind.CLIPBOARD, data={"length": 250})
    match = Signal(kind=Kind.CLIPBOARD, data={"length": 250, "match_path": "D:\\old\\a.c", "match_pct": 90})
    assert evaluate(small, POLICY).status == "allow"
    assert (evaluate(big, POLICY).hit.severity, evaluate(big, POLICY).hit.title) == ("medium", "Large paste · 250 chars")
    assert evaluate(match, POLICY).hit.severity == "high"


def test_file_old_code_usb_lan_extension():
    assert evaluate(Signal(kind=Kind.FILE_OPEN, data={"path": "D:\\old\\a.c"}), POLICY).hit.title == "Pre-exam file opened"
    oc = evaluate(Signal(kind=Kind.OLD_CODE, data={"pct": 82}), POLICY).hit
    assert (oc.severity, oc.title) == ("high", "Old code reused · 82%")
    assert evaluate(Signal(kind=Kind.USB, data={"drive": "E:\\"}), POLICY).hit.severity == "high"
    assert evaluate(Signal(kind=Kind.LAN_PEER, data={"ip": "10.10.0.30"}), POLICY).hit.title == "Connection to 10.10.0.30"
    ext = evaluate(Signal(kind=Kind.EXTENSION, data={"names": ["GitHub Copilot"]}), POLICY).hit
    assert (ext.severity, ext.title) == ("medium", "GitHub Copilot installed")
    assert evaluate(Signal(kind=Kind.EXTENSION, data={"names": []}), POLICY).status == "allow"
