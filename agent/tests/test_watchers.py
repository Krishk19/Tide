from tide_agent.inventory import build_inventory
from tide_agent.platform import AdapterInfo, Peer, ProcInfo, WindowInfo
from tide_agent.preflight import preflight_checks, preflight_message, run_preflight
from tide_agent.watchers import (ClipboardWatcher, ExtensionWatcher, LanWatcher, NetworkWatcher,
                                 ProcessWatcher, UsbWatcher, WindowWatcher, scan_extensions)
from fakes import FakePlatform


def test_window_watcher_emits_on_change_and_reads_host_once_per_title():
    p = FakePlatform()
    w = WindowWatcher(p)
    first = w.poll()
    assert first[0].data["process"] == "Code.exe" and first[0].data["host"] is None
    assert w.poll() == []
    p.window = WindowInfo(2, 20, "chrome.exe", "", "ChatGPT")
    p.hosts[2] = "chatgpt.com"
    got = w.poll()
    assert got[0].data["host"] == "chatgpt.com" and w.current_process == "chrome.exe"
    w.poll(); w.poll()
    assert p.host_reads == 1


def test_process_watcher_reports_new_processes():
    p = FakePlatform()
    w = ProcessWatcher(p)
    assert [s.data["process"] for s in w.poll()] == ["Code.exe"]
    p.procs[30] = ProcInfo(30, "WhatsApp.exe")
    assert [s.data["pid"] for s in w.poll()] == [30]
    assert w.poll() == []


def test_network_watcher_reports_internet_changes_with_via():
    p = FakePlatform()
    t = [0.0]
    w = NetworkWatcher(p, probe_every_s=5.0, clock=lambda: t[0])
    assert w.poll()[0].data["internet"] is False
    t[0] = 1.0
    p.ads["Wi-Fi"] = AdapterInfo("Wi-Fi", True, wifi=True, ssid="Redmi Note")
    p.online = True
    got = w.poll()                      # a new adapter forces an early probe
    assert got[0].data == {"internet": True, "via": "Wi-Fi “Redmi Note”", "adapters": ["Ethernet", "Wi-Fi"]}
    t[0] = 2.0
    assert w.poll() == []               # no change, probe not due


def test_lan_usb_clipboard():
    p = FakePlatform()
    lan = LanWatcher(p, "10.10.0.1")
    p.peers = [Peer("10.10.0.1", 8765), Peer("10.10.0.30", 445, "System")]
    assert [s.data["ip"] for s in lan.poll()] == ["10.10.0.30"]
    assert lan.poll() == []

    usb = UsbWatcher(p)
    assert usb.poll() == []
    p.drives = {"E:\\"}
    assert usb.poll()[0].data == {"drive": "E:\\"}

    exam = {"main.c": "x" * 300}
    clip = ClipboardWatcher(p, lambda: exam, lambda: None)
    assert clip.poll() == []            # first read is the baseline
    p.clip_seq, p.clip = 2, "y" * 250
    assert clip.poll()[0].data["length"] == 250
    p.clip_seq, p.clip = 3, "x" * 250   # copied from the exam's own file
    assert clip.poll() == []


def test_extensions(tmp_path):
    ext = tmp_path / "extensions"
    (ext / "github.copilot-1.200.0").mkdir(parents=True)
    (ext / "ms-vscode.cpptools-1.20").mkdir()
    assert scan_extensions(ext) == ["GitHub Copilot"]
    w = ExtensionWatcher(ext)
    w.set_baseline(["GitHub Copilot"])
    assert w.poll() == []
    (ext / "codeium.codeium-1.8").mkdir()
    assert w.poll()[0].data["names"] == ["Codeium"]


def test_preflight_kills_denied_and_reports(tmp_path):
    p = FakePlatform()
    p.procs[40] = ProcInfo(40, "discord.exe")
    p.online = True
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "a.c").write_text("int main() { return 0; }")
    r = run_preflight(p, tmp_path / "noext", [tmp_path], tmp_path / "Exam")
    assert p.killed == [40] and r.denied_closed == ["Discord"] and r.internet is True
    assert preflight_message(r)["inventory_count"] == 1
    states = {c["id"]: c["state"] for c in preflight_checks(r)}
    assert states == {"internet": "fail", "apps": "ok", "extensions": "ok", "files": "ok"}
