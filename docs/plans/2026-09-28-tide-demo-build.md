# Tide Demo Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status: built.** Tasks 1-24 are implemented, committed on branch `rebuild`, and verified with 108 passing tests (25 common + 48 server + 29 agent, 1 skipped Windows-only + 6 console) plus a single-device rehearsal against the real server and live Jev. Task 25 is partially done: single-device rehearsal passed; the two-Windows-laptop rehearsal and real-hardware Windows verification are still open.

> **Changed after this plan (decision D11 in the spec):** internet is now a per-exam setting, default **allowed · monitored**. `Policy.internet` ("allowed" | "blocked") flows through the rules, agent pre-flight, server pre-flight gating, demo seeding and the Setup page. The offline-gating behaviour described in Tasks 9, 16 and 20 now applies only to *blocked* exams. Also fixed: the duplicate "Copilot installed" flag (the extension watcher waits for the pre-flight baseline) and a real agent taking over a simulated demo seat. Test total is now 114 (27 common + 51 server + 30 agent + 6 console).

**Goal:** Build the demo version of Tide: a Windows monitoring agent, a FastAPI teacher server with the Jev classifier, and a React teacher console, able to run the 4-minute demo in `docs/DEMO.md` on 1–2 laptops.

**Architecture:** A shared `tide_common` package holds the wire protocol, the policy (allow/deny lists) and the deterministic rules, so the agent and server agree by construction. The agent acts instantly on rule hits and sends everything else to the server. The server classifies unknown signals (rules → cache → Jev → heuristics), decides act/flag/log, keeps the exam clock, and pushes live state to the console over WebSocket. Windows-specific code sits behind one `Platform` interface, so all agent logic is tested on any OS with a fake.

**Tech Stack:** Python 3.12, FastAPI, SQLModel/SQLite, httpx, websockets, pywebview, pywin32, psutil, uiautomation, mss, Pillow, PyInstaller · React 18 + Vite + TypeScript, Vitest · pytest, pytest-asyncio.

**Spec:** `docs/specs/2026-09-28-tide-design.md` (how it works: `docs/ARCHITECTURE.md`, UI reference: `design/mock-ui.html`, demo: `docs/DEMO.md`)

## Global Constraints

- Windows 10/11 is the only agent target. Server and console must also run on macOS/Linux (dev machines).
- Python ≥ 3.12. Node ≥ 20.
- No Electron. The agent UI is pywebview (Edge WebView2).
- The server clock is the only clock: agents get an absolute `ends_at` plus a measured offset.
- Auto-act only when `activity ∈ {ai_assistant, communication, remote_or_file_share}` **and** confidence ≥ 0.90 **and** the verdict came from Jev (live or cached). Violation ≥ 0.80 → high flag; ≥ 0.60 → medium flag; else log only.
- Heartbeat every 3 s; no heartbeat for 10 s → seat offline + critical flag.
- Snapshots every 30 s; a single snapshot adding ≥ 40 lines → "Code burst" (medium).
- Clipboard text ≥ 200 chars that isn't from the exam folder → flag.
- Odd seat → Set A, even seat → Set B (Set A for everyone if Set B has no files).
- Questions are only delivered to seats whose pre-flight reported no internet.
- Screenshots are taken **before** any enforcement action, and only for severity ≥ medium.
- Copy is short: seat colours, one-line titles like `ChatGPT — closed`. UI matches `design/mock-ui.html`.
- Jev is optional at runtime. With no `JEV_API_KEY`, heuristics are used and the console shows "Offline heuristics".
- Every commit message ends with the `Co-Authored-By` line required by the repo's contributors.

## Review Focus

1. **Agent restarted mid-exam** (same roll + seat): re-pairing must succeed, the same set is re-delivered **without overwriting the student's edited files**, and the countdown resumes from the server's `ends_at`. Tests: Task 5 (re-pair), Task 9 (re-delivery), Task 15 (`write_files` never overwrites).
2. **Browser address bar unreadable** (UI Automation returns `None`): the window is `unknown`, not `allow`, so it still reaches Jev by title. Test: Task 2.
3. **Exam file with the same name as an old file** (`main.c` in `C:\Exam\22BCS107` and in `D:\old`): the VS Code title contains the roll folder, so no "Pre-exam file opened" false positive. Test: Task 17.
4. **Server unreachable while the student is on a hotspot:** local rules still overlay, and flags queue on disk and flush on reconnect (heartbeats are not queued). Tests: Task 13 (outbox), Task 17 (engine enforces with no server).
5. **Jev timeout or HTTP 500:** fall back to heuristics, and heuristics never auto-act (max confidence 0.70). Test: Task 7.

---

## File Structure

```
common/                          shared by agent + server
  pyproject.toml
  tide_common/
    protocol.py                  Signal, Kind, Severity, msg()
    policy.py                    app catalog, presets, deny lists, Policy
    rules.py                     evaluate(signal, policy) -> RuleResult
    fingerprint.py               normalize, winnowing fingerprints, similarity
  tests/

server/
  pyproject.toml
  tide_server/
    config.py                    Settings (env)
    clock.py                     now()  (patchable)
    models.py                    SQLModel tables
    db.py                        make_engine()
    ctx.py                       Ctx (shared services) + get_ctx
    hub.py                       WebSocket registry: agents + consoles
    serialize.py                 seat_out / flag_out / exam_out / seat_status
    exam_service.py              exams, files, pairing, start, extend, sets
    ingest.py                    agent message handling, raise_flag
    monitor.py                   offline detection, auto-end
    classify/
      describe.py                signal -> text for Jev, cache_key
      heuristics.py              keyword classifier (offline fallback)
      jev.py                     Jev HTTP client
      pipeline.py                cache -> Jev -> heuristics
    decide.py                    Verdict -> Decision
    burst.py                     code-burst rule
    similarity.py                cross-submission pairs, results rows, CSV
    discovery.py                 UDP responder
    simulate.py                  59 simulated seats + scripted events
    api/
      teacher.py                 REST for the console
      agent.py                   /api/pair, /api/submit, /ws/agent
      console.py                 /ws/console
    app.py                       create_app()
    __main__.py                  CLI: tide-server [--demo]
    demo_assets/set_A/*, set_B/*
  tests/

agent/
  pyproject.toml
  tide_agent/
    platform.py                  WindowInfo, ProcInfo, AdapterInfo, Peer, Platform protocol
    win/                         real Windows implementation (WinPlatform)
      __init__.py windows.py browser.py procs.py net.py devices.py input.py capture.py
    clock.py                     ServerClock, compute_offset
    outbox.py                    disk queue for offline messages
    link.py                      WebSocket client with reconnect
    discovery.py                 UDP broadcast client
    pairing.py                   POST /api/pair, POST /api/submit
    inventory.py                 pre-exam file index, title match, best_match
    exam_folder.py               C:\Exam\<roll> files, snapshots, zip
    watchers.py                  Window/Process/Network/Lan/Usb/Clipboard/Extension watchers
    preflight.py                 run_preflight()
    enforcer.py                  close tab / kill / overlay
    engine.py                    rules routing, schedules watchers, server messages
    ui/port.py                   UiPort protocol
    ui/webview_ui.py             pywebview implementation
    ui/web/                      index.html pill.html overlay.html style.css
    main.py                      AgentApp wiring
    __main__.py
  scripts/win_smoke.py           prints every Platform call on a real PC
  tide-agent.spec                PyInstaller spec
  tests/  (fakes.py + unit tests)

console/                         React + Vite
  src/ types.ts api.ts state.ts styles.css main.tsx App.tsx
       components/ TopBar.tsx SeatGrid.tsx AlertFeed.tsx SeatDrawer.tsx
       pages/ Login.tsx Setup.tsx Lobby.tsx Live.tsx Results.tsx
  src/state.test.ts
```

Dev setup (once, repo root):

```bash
python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e common -e "server[dev]" -e "agent[dev]"
```

---

## Phase 1 — Shared contracts (`common/`)

### Task 1: Protocol and policy

**Files:**
- Create: `common/pyproject.toml`, `common/tide_common/__init__.py`, `common/tide_common/protocol.py`, `common/tide_common/policy.py`
- Test: `common/tests/test_protocol.py`, `common/tests/test_policy.py`

**Interfaces:**
- Produces:
  - `Signal(kind: str, data: dict, ts: float)` (pydantic), `Kind.WINDOW|PROCESS|NETWORK|LAN_PEER|USB|CLIPBOARD|FILE_OPEN|OLD_CODE|EXTENSION`
  - `Severity = Literal["info","medium","high","critical"]`, `Action = Literal["none","close_tab","kill","overlay"]`, `SEVERITY_RANK: dict[str,int]`
  - `msg(t: str, **payload) -> dict`
  - `APP_CATALOG: dict[str, tuple[str,...]]`, `PRESETS: dict[str, tuple[str,...]]`, `BROWSERS`, `ALWAYS_ALLOWED`, `DENY_PROCESSES: dict[str,str]`, `DENY_HOSTS: dict[str,str]`, `LOCAL_HOSTS`, `AI_EXTENSIONS: dict[str,str]`, `CLIPBOARD_MIN = 200`
  - `host_match(host: str, table: dict[str,str]) -> str | None`, `display_app(process: str) -> str`
  - `Policy(apps: tuple[str,...], allowed_processes: frozenset[str], server_ip: str)` with `from_apps(apps, server_ip="")`, `is_allowed_process(name)`, `to_dict()`, `from_dict(d)`

- [x] **Step 1: Package metadata**

`common/pyproject.toml`:
```toml
[project]
name = "tide-common"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.8"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["tide_common"]
```
`common/tide_common/__init__.py`: empty file.

- [x] **Step 2: Write the failing tests**

`common/tests/test_protocol.py`:
```python
import time
from tide_common.protocol import Signal, Kind, msg, SEVERITY_RANK


def test_signal_defaults_ts_to_now():
    before = time.time()
    s = Signal(kind=Kind.WINDOW, data={"process": "code.exe"})
    assert before <= s.ts <= time.time()


def test_msg_builds_typed_dict():
    assert msg("heartbeat", state="live") == {"t": "heartbeat", "state": "live"}


def test_severity_rank_orders():
    assert SEVERITY_RANK["info"] < SEVERITY_RANK["medium"] < SEVERITY_RANK["high"] < SEVERITY_RANK["critical"]
```

`common/tests/test_policy.py`:
```python
from tide_common.policy import Policy, PRESETS, DENY_HOSTS, host_match, display_app


def test_from_apps_maps_catalog_names_to_processes():
    p = Policy.from_apps(["VS Code", "Wireshark"])
    assert "code.exe" in p.allowed_processes
    assert "wireshark.exe" in p.allowed_processes


def test_always_allowed_and_case_insensitive():
    p = Policy.from_apps([])
    assert p.is_allowed_process("Explorer.EXE")
    assert not p.is_allowed_process("code.exe")


def test_roundtrip_dict():
    p = Policy.from_apps(PRESETS["networking"], server_ip="10.10.0.1")
    assert Policy.from_dict(p.to_dict()) == p


def test_host_match_matches_subdomains_not_suffixes():
    assert host_match("chatgpt.com", DENY_HOSTS) == "ChatGPT"
    assert host_match("www.chatgpt.com", DENY_HOSTS) == "ChatGPT"
    assert host_match("notchatgpt.com", DENY_HOSTS) is None


def test_display_app():
    assert display_app("Code.exe") == "VS Code"
    assert display_app("weird.exe") == "weird"
```

- [x] **Step 3: Run tests to verify they fail**

Run: `pytest common/tests -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_common.protocol'`

- [x] **Step 4: Implement**

`common/tide_common/protocol.py`:
```python
"""Wire protocol shared by agent and server. See docs/ARCHITECTURE.md §6."""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "medium", "high", "critical"]
Action = Literal["none", "close_tab", "kill", "overlay"]
SEVERITY_RANK: dict[str, int] = {"info": 0, "medium": 1, "high": 2, "critical": 3}


class Kind:
    WINDOW = "window"          # hwnd, pid, process, exe, title, description, original_name, host
    PROCESS = "process"        # pid, process, exe, description, original_name
    NETWORK = "network"        # internet: bool, via: str, adapters: list[str]
    LAN_PEER = "lan_peer"      # ip, port, process
    USB = "usb"                # drive
    CLIPBOARD = "clipboard"    # length, preview, match_path?, match_pct?
    FILE_OPEN = "file_open"    # path, title
    OLD_CODE = "old_code"      # exam_path, source_path, pct
    EXTENSION = "extension"    # names: list[str]


class Signal(BaseModel):
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)


def msg(t: str, **payload: Any) -> dict[str, Any]:
    return {"t": t, **payload}
```

`common/tide_common/policy.py`:
```python
"""What is allowed, what is always blocked. Shared so agent and server agree."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

APP_CATALOG: dict[str, tuple[str, ...]] = {
    "VS Code": ("code.exe",),
    "CodeBlocks": ("codeblocks.exe",),
    "Terminal": ("windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe"),
    "Explorer": ("explorer.exe",),
    "Wireshark": ("wireshark.exe",),
    "VMware": ("vmware.exe", "vmplayer.exe", "vmware-vmx.exe"),
    "Notepad": ("notepad.exe", "notepad++.exe"),
}

PRESETS: dict[str, tuple[str, ...]] = {
    "networking": ("VS Code", "CodeBlocks", "Terminal", "Explorer", "Wireshark", "VMware", "Notepad"),
    "programming": ("VS Code", "CodeBlocks", "Terminal", "Explorer", "Notepad"),
}

# Browsers are allowed (PDFs open in Edge) but every site they show is checked.
BROWSERS = frozenset({"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"})

ALWAYS_ALLOWED = frozenset({
    "tide-agent.exe", "explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "lockapp.exe", "applicationframehost.exe",
    "textinputhost.exe", "systemsettings.exe", "msedgewebview2.exe",
})

DENY_PROCESSES: dict[str, str] = {
    "chatgpt.exe": "ChatGPT", "claude.exe": "Claude", "copilot.exe": "Copilot",
    "cursor.exe": "Cursor", "windsurf.exe": "Windsurf", "ollama.exe": "Ollama",
    "ollama app.exe": "Ollama", "lm studio.exe": "LM Studio", "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram", "discord.exe": "Discord", "anydesk.exe": "AnyDesk",
    "teamviewer.exe": "TeamViewer", "outlook.exe": "Outlook", "olk.exe": "Outlook",
    "slack.exe": "Slack", "zoom.exe": "Zoom",
}

# poe.com is intentionally NOT listed: the demo shows Jev catching it.
DENY_HOSTS: dict[str, str] = {
    "chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT", "claude.ai": "Claude",
    "gemini.google.com": "Gemini", "copilot.microsoft.com": "Copilot",
    "perplexity.ai": "Perplexity", "chat.deepseek.com": "DeepSeek", "grok.com": "Grok",
    "meta.ai": "Meta AI", "chat.mistral.ai": "Mistral", "web.whatsapp.com": "WhatsApp",
    "mail.google.com": "Gmail", "outlook.live.com": "Outlook", "drive.google.com": "Drive",
    "classroom.google.com": "Classroom",
}

LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "newtab", "new-tab-page", "extensions", "settings"})

AI_EXTENSIONS: dict[str, str] = {
    "github.copilot": "GitHub Copilot", "codeium.": "Codeium", "continue.": "Continue",
    "saoudrizwan.claude-dev": "Cline", "tabnine.": "Tabnine", "supermaven.": "Supermaven",
    "amazonwebservices.amazon-q": "Amazon Q", "rooveterinaryinc.roo-cline": "Roo Code",
    "google.geminicodeassist": "Gemini Code Assist",
}

CLIPBOARD_MIN = 200


def host_match(host: str, table: dict[str, str]) -> str | None:
    host = host.lower().strip(".")
    for domain, name in table.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def display_app(process: str) -> str:
    p = process.lower()
    for name, procs in APP_CATALOG.items():
        if p in procs:
            return name
    return process[:-4] if p.endswith(".exe") else process


@dataclass(frozen=True)
class Policy:
    apps: tuple[str, ...]
    allowed_processes: frozenset[str]
    server_ip: str = ""

    @classmethod
    def from_apps(cls, apps: Iterable[str], server_ip: str = "") -> "Policy":
        apps = tuple(sorted(apps))
        procs = frozenset(p for a in apps for p in APP_CATALOG.get(a, ()))
        return cls(apps=apps, allowed_processes=procs, server_ip=server_ip)

    def is_allowed_process(self, name: str) -> bool:
        n = name.lower()
        return n in self.allowed_processes or n in ALWAYS_ALLOWED

    def to_dict(self) -> dict[str, Any]:
        return {"apps": list(self.apps), "allowed_processes": sorted(self.allowed_processes),
                "server_ip": self.server_ip}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Policy":
        return cls(apps=tuple(d.get("apps", ())),
                   allowed_processes=frozenset(d.get("allowed_processes", ())),
                   server_ip=d.get("server_ip", ""))
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest common/tests -v`
Expected: 8 passed

- [x] **Step 6: Commit**

```bash
git add common
git commit -m "feat(common): wire protocol and exam policy"
```

### Task 2: Deterministic rules

**Files:**
- Create: `common/tide_common/rules.py`
- Test: `common/tests/test_rules.py`

**Interfaces:**
- Consumes: `Signal`, `Kind`, `Policy`, the deny tables from Task 1
- Produces:
  - `RuleHit(kind: str, severity: Severity, action: Action, title: str)`
  - `RuleResult(status: Literal["allow","hit","unknown"], hit: RuleHit | None = None)`
  - `evaluate(signal: Signal, policy: Policy) -> RuleResult`
  - Hit kinds: `blocked_site`, `denied_app`, `internet`, `usb`, `lan_peer`, `clipboard`, `file_open`, `old_code`, `ai_extension`

- [x] **Step 1: Write the failing tests**

`common/tests/test_rules.py`:
```python
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


def test_internet_overlays_and_offline_allows():
    on = evaluate(Signal(kind=Kind.NETWORK, data={"internet": True, "via": "Wi-Fi “Redmi”"}), POLICY)
    assert (on.hit.kind, on.hit.severity, on.hit.action, on.hit.title) == (
        "internet", "critical", "overlay", "Internet via Wi-Fi “Redmi”")
    assert evaluate(Signal(kind=Kind.NETWORK, data={"internet": False}), POLICY).status == "allow"


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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest common/tests/test_rules.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_common.rules'`

- [x] **Step 3: Implement**

`common/tide_common/rules.py`:
```python
"""Deterministic rules. Run on the agent (instant, offline-safe) — ARCHITECTURE §5.1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .policy import (BROWSERS, CLIPBOARD_MIN, DENY_HOSTS, DENY_PROCESSES, LOCAL_HOSTS,
                     Policy, host_match)
from .protocol import Action, Kind, Severity, Signal


@dataclass(frozen=True)
class RuleHit:
    kind: str
    severity: Severity
    action: Action
    title: str


@dataclass(frozen=True)
class RuleResult:
    status: Literal["allow", "hit", "unknown"]
    hit: RuleHit | None = None


ALLOW = RuleResult("allow")
UNKNOWN = RuleResult("unknown")


def _hit(kind: str, severity: Severity, action: Action, title: str) -> RuleResult:
    return RuleResult("hit", RuleHit(kind, severity, action, title))


def _denied_process(data: dict) -> str | None:
    for key in ("process", "original_name"):
        name = DENY_PROCESSES.get((data.get(key) or "").lower())
        if name:
            return name
    return None


def evaluate(signal: Signal, policy: Policy) -> RuleResult:
    d = signal.data
    k = signal.kind

    if k in (Kind.WINDOW, Kind.PROCESS):
        denied = _denied_process(d)
        if denied:
            return _hit("denied_app", "critical", "kill", f"{denied} — closed")
        if k == Kind.PROCESS:
            return ALLOW
        process = (d.get("process") or "").lower()
        if process in BROWSERS:
            host = d.get("host")
            if host is None:
                return UNKNOWN
            if host.lower() in LOCAL_HOSTS:
                return ALLOW
            name = host_match(host, DENY_HOSTS)
            if name:
                return _hit("blocked_site", "critical", "close_tab", f"{name} — closed")
            return UNKNOWN
        return ALLOW if policy.is_allowed_process(process) else UNKNOWN

    if k == Kind.NETWORK:
        if d.get("internet"):
            return _hit("internet", "critical", "overlay", f"Internet via {d.get('via') or 'network'}")
        return ALLOW
    if k == Kind.CLIPBOARD:
        if d.get("match_path"):
            return _hit("clipboard", "high", "none", f"Paste matches old file · {d.get('match_pct', 0)}%")
        if d.get("length", 0) >= CLIPBOARD_MIN:
            return _hit("clipboard", "medium", "none", f"Large paste · {d['length']} chars")
        return ALLOW
    if k == Kind.FILE_OPEN:
        return _hit("file_open", "high", "none", "Pre-exam file opened")
    if k == Kind.OLD_CODE:
        return _hit("old_code", "high", "none", f"Old code reused · {d.get('pct', 0)}%")
    if k == Kind.USB:
        return _hit("usb", "high", "none", "USB drive inserted")
    if k == Kind.LAN_PEER:
        return _hit("lan_peer", "medium", "none", f"Connection to {d.get('ip', '?')}")
    if k == Kind.EXTENSION:
        names = d.get("names") or []
        return _hit("ai_extension", "medium", "none", f"{', '.join(names)} installed") if names else ALLOW
    return ALLOW
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest common/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add common
git commit -m "feat(common): deterministic rules for local enforcement"
```

### Task 3: Code fingerprints and similarity

**Files:**
- Create: `common/tide_common/fingerprint.py`
- Test: `common/tests/test_fingerprint.py`

**Interfaces:**
- Produces: `normalize_code(text) -> str`, `tokens(text) -> list[str]`, `fingerprints(text, k=5, window=4) -> frozenset[int]`, `similarity(a: frozenset[int], b: frozenset[int]) -> float` (containment of the smaller set, 0.0–1.0)

Hashes use `zlib.crc32` because Python's `hash()` is salted per process, and the agent and server must produce identical fingerprints.

- [x] **Step 1: Write the failing tests**

`common/tests/test_fingerprint.py`:
```python
from tide_common.fingerprint import fingerprints, normalize_code, similarity, tokens

ORIGINAL = """
#include <stdio.h>
// count vowels
int main() {
    char s[100]; int count = 0;
    scanf("%s", s);
    for (int i = 0; s[i] != '\\0'; i++) {
        if (s[i]=='a'||s[i]=='e'||s[i]=='i'||s[i]=='o'||s[i]=='u') count++;
    }
    printf("%d\\n", count);
    return 0;
}
"""

RENAMED = """
#include <stdio.h>
int main() {
    char word[100]; int total = 0;   /* renamed */
    scanf("%s", word);
    for (int j = 0; word[j] != '\\0'; j++) {
        if (word[j]=='a'||word[j]=='e'||word[j]=='i'||word[j]=='o'||word[j]=='u') total++;
    }
    printf("%d\\n", total);
    return 0;
}
"""

UNRELATED = """
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
print(sum(fib(k) for k in range(10)))
"""


def test_normalize_strips_comments_and_whitespace():
    assert normalize_code("int  a; // hi\n/* x */ b") == "int a; b"


def test_identifiers_collapse_keywords_stay():
    assert tokens("int count = 0;") == ["int", "v", "=", "0", ";"]


def test_renamed_copy_is_similar():
    assert similarity(fingerprints(ORIGINAL), fingerprints(RENAMED)) >= 0.8


def test_unrelated_is_not_similar():
    assert similarity(fingerprints(ORIGINAL), fingerprints(UNRELATED)) < 0.3


def test_empty_is_zero():
    assert similarity(fingerprints(""), fingerprints(ORIGINAL)) == 0.0


def test_stable_across_calls():
    assert fingerprints(ORIGINAL) == fingerprints(ORIGINAL)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest common/tests/test_fingerprint.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [x] **Step 3: Implement**

`common/tide_common/fingerprint.py`:
```python
"""Winnowing fingerprints that survive renaming (MOSS-style). Used for old-code and peer similarity."""
from __future__ import annotations

import re
import zlib

KEYWORDS = frozenset("""
auto break case char const continue default do double else enum extern float for goto if int
long register return short signed sizeof static struct switch typedef union unsigned void volatile
while class public private protected new delete this template typename namespace using bool true
false include define import from def lambda yield pass raise try except finally with as in is not
and or none self print elif global nonlocal assert del async await string vector std cout cin endl
printf scanf main null boolean final extends implements interface package super throws select where
""".split())

_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/|^[ \t]*#(?![ \t]*include)[^\n]*", re.S | re.M)
_TOKEN = re.compile(r"[A-Za-z_]\w*|\d+|\S")


def normalize_code(text: str) -> str:
    text = _COMMENTS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(normalize_code(text)):
        low = t.lower()
        if t[0].isalpha() or t[0] == "_":
            out.append(low if low in KEYWORDS else "v")
        else:
            out.append(t)
    return out


def fingerprints(text: str, k: int = 5, window: int = 4) -> frozenset[int]:
    toks = tokens(text)
    if len(toks) < k:
        return frozenset()
    hashes = [zlib.crc32(" ".join(toks[i:i + k]).encode()) for i in range(len(toks) - k + 1)]
    if len(hashes) <= window:
        return frozenset(hashes)
    picked = set()
    for i in range(len(hashes) - window + 1):
        picked.add(min(hashes[i:i + window]))
    return frozenset(picked)


def similarity(a: frozenset[int], b: frozenset[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest common/tests -v`
Expected: all pass. If `test_normalize_strips_comments_and_whitespace` fails on the `#` handling, check that `_COMMENTS` keeps `#include` lines and strips whole-line `#` comments (Python) and other preprocessor lines.

- [x] **Step 5: Commit**

```bash
git add common
git commit -m "feat(common): rename-proof code fingerprints"
```

---
## Phase 2 — Teacher server (`server/`)

All server tests share this fixture file, created in Task 4 and extended later.

### Task 4: Server foundation — config, models, db, context, serializers

**Files:**
- Create: `server/pyproject.toml`, `server/tide_server/__init__.py`, `config.py`, `clock.py`, `models.py`, `db.py`, `hub.py`, `ctx.py`, `serialize.py`
- Test: `server/tests/conftest.py`, `server/tests/test_foundation.py`

**Interfaces:**
- Produces:
  - `Settings` fields: `data_dir, host, port, discovery_port, teacher_pin, heartbeat_timeout_s, auto_act_min, demo, background_tasks, console_dir, openrouter_api_key (env OPENROUTER_API_KEY), jev_model, jev_url`
  - `clock.now() -> float` (always call as `clock.now()` so tests can patch it)
  - Tables: `Exam, ExamFile, Seat, Event, Flag, Snapshot, Submission` (fields below)
  - `make_engine(data_dir: Path) -> Engine`
  - `Hub.add_agent/remove_agent/to_agent(seat_id, msg) -> bool`, `Hub.add_console/remove_console/to_console(msg)`
  - `Ctx(settings, engine, hub, teacher_tokens, pipeline, ingest, ended_seats)` with `.db() -> Session`; `get_ctx(request)`
  - `seat_status(seat, open_flags) -> "ok"|"warn"|"crit"|"off"|"wait"|"done"`, `seat_out`, `flag_out`, `exam_out`, `event_out`, `event_text`, `exam_policy(exam) -> Policy`

- [x] **Step 1: Package metadata**

`server/pyproject.toml`:
```toml
[project]
name = "tide-server"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "tide-common", "fastapi>=0.115", "uvicorn[standard]>=0.30", "sqlmodel>=0.0.22",
  "pydantic-settings>=2.4", "httpx>=0.27", "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[project.scripts]
tide-server = "tide_server.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["tide_server"]

[tool.hatch.build.targets.wheel.force-include]
"tide_server/demo_assets" = "tide_server/demo_assets"

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```
`server/tide_server/__init__.py`: empty.

- [x] **Step 2: Write the failing tests**

`server/tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient

from tide_common.policy import PRESETS
from tide_server.config import Settings
from tide_server.hub import Hub


class RecordingHub(Hub):
    def __init__(self):
        super().__init__()
        self.console_msgs: list[dict] = []
        self.agent_msgs: list[tuple[int, dict]] = []

    async def to_console(self, message):
        self.console_msgs.append(message)
        await super().to_console(message)

    async def to_agent(self, seat_id, message):
        self.agent_msgs.append((seat_id, message))
        return await super().to_agent(seat_id, message)


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path / "data", openrouter_api_key="",
                    background_tasks=False, console_dir=tmp_path / "no-console")


@pytest.fixture
def app(settings):
    from tide_server.app import create_app
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ctx(app):
    return app.state.ctx


@pytest.fixture
def hub(ctx):
    ctx.hub = RecordingHub()
    return ctx.hub


@pytest.fixture
def teacher(client):
    token = client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def exam(ctx):
    from tide_server.exam_service import create_exam
    with ctx.db() as db:
        return create_exam(db, "CN Lab Test 3", 90 * 60, list(PRESETS["networking"]))


@pytest.fixture
def paired(ctx, exam):
    from tide_server.exam_service import pair_seat
    with ctx.db() as db:
        seat, token = pair_seat(db, exam.join_code, "22bcs107", 7, "LAB3-PC07")
    return seat, token
```

`server/tests/test_foundation.py`:
```python
import json

from tide_server.models import Exam, Flag, Seat
from tide_server.serialize import exam_out, seat_status


def flag(sev, status="open"):
    return Flag(seat_id=1, ts=0, kind="x", severity=sev, title="t", source="rule", status=status)


def test_seat_status_matrix():
    s = Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="live")
    assert seat_status(s, []) == "ok"
    assert seat_status(s, [flag("medium")]) == "warn"
    assert seat_status(s, [flag("medium"), flag("high")]) == "crit"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="lobby"), []) == "wait"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="blocked"), []) == "crit"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="offline"), [flag("critical")]) == "off"
    assert seat_status(Seat(exam_id=1, seat_no=1, roll="R", token_hash="h", state="submitted"), [flag("critical")]) == "done"


def test_engine_creates_tables_and_roundtrips(ctx):
    with ctx.db() as db:
        e = Exam(title="T", duration_s=60, join_code="ABC234",
                 policy_json=json.dumps({"apps": ["VS Code"], "allowed_processes": ["code.exe"], "server_ip": ""}))
        db.add(e)
        db.commit()
        out = exam_out(e)
    assert out["join_code"] == "ABC234"
    assert out["apps"] == ["VS Code"]
    assert out["state"] == "lobby"
```

- [x] **Step 3: Run tests to verify they fail**

Run: `pytest server/tests -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_server.config'`

- [x] **Step 4: Implement**

`server/tide_server/config.py`:
```python
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TIDE_", env_file=(REPO_ROOT / ".env", REPO_ROOT / ".env.local", ".env", ".env.local"),
                                      extra="ignore", populate_by_name=True)

    data_dir: Path = Path("tide-data")
    host: str = "0.0.0.0"
    port: int = 8765
    discovery_port: int = 47800
    teacher_pin: str = "2468"
    heartbeat_timeout_s: float = 10.0
    auto_act_min: float = 0.90
    demo: bool = False
    background_tasks: bool = True
    console_dir: Path = REPO_ROOT / "console" / "dist"
    openrouter_api_key: str = Field(default="", validation_alias=AliasChoices(
        "OPENROUTER_API_KEY", "openrouter_api_key"))
    jev_model: str = "~typesafe/jev-latest"
    jev_url: str = "https://openrouter.ai/api/alpha/decisions"
```

`server/tide_server/clock.py`:
```python
import time


def now() -> float:
    return time.time()
```

`server/tide_server/models.py`:
```python
from sqlmodel import Field, SQLModel


class Exam(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    duration_s: int
    join_code: str = Field(index=True, unique=True)
    state: str = "lobby"                     # lobby | live | ended
    started_at: float | None = None
    ends_at: float | None = None
    policy_json: str = "{}"


class ExamFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    exam_id: int = Field(foreign_key="exam.id", index=True)
    set_name: str                            # "A" | "B"
    name: str
    data: bytes


class Seat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    exam_id: int = Field(foreign_key="exam.id", index=True)
    seat_no: int
    roll: str
    hostname: str = ""
    token_hash: str = Field(default="", index=True)
    set_name: str | None = None
    state: str = "lobby"                     # lobby | ready | blocked | live | offline | submitted
    resume_state: str = ""
    preflight_json: str = "{}"
    last_seen: float = 0.0
    ends_at_override: float | None = None
    fg_app: str = ""
    simulated: bool = False


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    kind: str
    data_json: str = "{}"


class Flag(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    kind: str
    severity: str
    title: str
    source: str                              # rule | jev | heuristic | server
    label: str | None = None
    confidence: float | None = None
    data_json: str = "{}"
    action: str = "none"
    screenshot: str | None = None
    status: str = "open"                     # open | dismissed | confirmed
    reviewed_at: float | None = None
    ref: str | None = Field(default=None, index=True)


class Snapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    path: str
    sha: str
    text: str
    line_count: int


class Submission(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seat_id: int = Field(index=True)
    ts: float
    file_name: str
    auto: bool = False
```

`server/tide_server/db.py`:
```python
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from tide_server import models  # noqa: F401  (registers tables)


def make_engine(data_dir: Path) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_dir / 'tide.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine
```

`server/tide_server/hub.py`:
```python
from typing import Any

from fastapi import WebSocket


class Hub:
    """Who is connected right now: one socket per seat, any number of consoles."""

    def __init__(self) -> None:
        self.agents: dict[int, WebSocket] = {}
        self.consoles: set[WebSocket] = set()

    def add_agent(self, seat_id: int, ws: WebSocket) -> None:
        self.agents[seat_id] = ws

    def remove_agent(self, seat_id: int, ws: WebSocket) -> None:
        if self.agents.get(seat_id) is ws:
            del self.agents[seat_id]

    async def to_agent(self, seat_id: int, message: dict[str, Any]) -> bool:
        ws = self.agents.get(seat_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            self.agents.pop(seat_id, None)
            return False

    def add_console(self, ws: WebSocket) -> None:
        self.consoles.add(ws)

    def remove_console(self, ws: WebSocket) -> None:
        self.consoles.discard(ws)

    async def to_console(self, message: dict[str, Any]) -> None:
        for ws in list(self.consoles):
            try:
                await ws.send_json(message)
            except Exception:
                self.consoles.discard(ws)
```

`server/tide_server/ctx.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import Request
from sqlalchemy import Engine
from sqlmodel import Session

from tide_server.config import Settings
from tide_server.hub import Hub

if TYPE_CHECKING:
    from tide_server.classify.pipeline import Pipeline
    from tide_server.ingest import Ingest


@dataclass
class Ctx:
    settings: Settings
    engine: Engine
    hub: Hub
    teacher_tokens: set[str] = field(default_factory=set)
    pipeline: "Pipeline | None" = None
    ingest: "Ingest | None" = None
    ended_seats: set[int] = field(default_factory=set)
    extras: dict[str, Any] = field(default_factory=dict)

    def db(self) -> Session:
        return Session(self.engine, expire_on_commit=False)


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx
```

`server/tide_server/serialize.py`:
```python
"""Shapes sent to the console. Keep in sync with console/src/types.ts."""
import json
from typing import Any

from tide_common.policy import Policy, display_app
from tide_common.protocol import SEVERITY_RANK

from tide_server.models import Event, Exam, Flag, Seat


def exam_policy(exam: Exam) -> Policy:
    return Policy.from_dict(json.loads(exam.policy_json or "{}"))


def seat_status(seat: Seat, open_flags: list[Flag]) -> str:
    if seat.state == "submitted":
        return "done"
    if seat.state == "offline":
        return "off"
    worst = max((SEVERITY_RANK[f.severity] for f in open_flags if f.status == "open"), default=0)
    if seat.state == "blocked" or worst >= 2:
        return "crit"
    if worst == 1:
        return "warn"
    if seat.state == "lobby":
        return "wait"
    return "ok"


def seat_out(seat: Seat, open_flags: list[Flag]) -> dict[str, Any]:
    return {"id": seat.id, "seat_no": seat.seat_no, "roll": seat.roll, "set": seat.set_name,
            "state": seat.state, "status": seat_status(seat, open_flags),
            "flags": len([f for f in open_flags if f.status == "open"]),
            "fg_app": seat.fg_app, "simulated": seat.simulated,
            "preflight": json.loads(seat.preflight_json or "{}")}


def flag_out(flag: Flag, seat_no: int) -> dict[str, Any]:
    return {"id": flag.id, "seat_id": flag.seat_id, "seat_no": seat_no, "ts": flag.ts,
            "kind": flag.kind, "severity": flag.severity, "title": flag.title,
            "source": flag.source, "label": flag.label, "confidence": flag.confidence,
            "action": flag.action, "status": flag.status, "has_shot": bool(flag.screenshot),
            "data": json.loads(flag.data_json or "{}")}


def exam_out(exam: Exam) -> dict[str, Any]:
    return {"id": exam.id, "title": exam.title, "duration_s": exam.duration_s,
            "join_code": exam.join_code, "state": exam.state, "started_at": exam.started_at,
            "ends_at": exam.ends_at, "apps": list(exam_policy(exam).apps)}


def event_text(kind: str, data: dict[str, Any]) -> str:
    if kind == "window":
        host = data.get("host")
        return host if host else display_app(data.get("process", ""))
    if kind == "network":
        return "Internet on" if data.get("internet") else "Offline"
    if kind == "joined":
        return "Joined"
    if kind == "start":
        return f"Set {data.get('set')} delivered · {data.get('files', 0)} files"
    if kind == "agent_back":
        return f"Agent back after {data.get('gap', 0)} s"
    if kind == "denied_closed":
        return f"{data.get('name')} closed at pre-flight"
    if kind == "teacher":
        return data.get("text", "")
    if kind == "submitted":
        return "Submitted" + (" (time up)" if data.get("auto") else "")
    return kind


def event_out(event: Event) -> dict[str, Any]:
    data = json.loads(event.data_json or "{}")
    return {"id": event.id, "seat_id": event.seat_id, "ts": event.ts, "kind": event.kind,
            "text": event_text(event.kind, data)}
```

Temporary `server/tide_server/app.py` so the fixture imports (replaced in Task 5):
```python
from fastapi import FastAPI

from tide_server.config import Settings
from tide_server.ctx import Ctx
from tide_server.db import make_engine
from tide_server.hub import Hub


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Tide")
    app.state.ctx = Ctx(settings=settings, engine=make_engine(settings.data_dir), hub=Hub())
    return app
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: 2 passed

- [x] **Step 6: Commit**

```bash
git add server
git commit -m "feat(server): settings, tables, hub, serializers"
```

### Task 5: Exams, question files, teacher login, seat pairing

**Files:**
- Create: `server/tide_server/exam_service.py`, `server/tide_server/live.py`, `server/tide_server/api/__init__.py`, `server/tide_server/api/teacher.py`, `server/tide_server/api/agent.py`
- Modify: `server/tide_server/app.py` (full replacement below)
- Test: `server/tests/test_pairing.py`

**Interfaces:**
- Consumes: Task 4 everything
- Produces:
  - `exam_service`: `JOIN_ALPHABET`, `new_join_code() -> str`, `hash_token(token) -> str`, `create_exam(db, title, duration_s, apps) -> Exam`, `add_file(db, exam_id, set_name, name, data) -> ExamFile`, `current_exam(db) -> Exam | None`, `open_flags(db, seat_id) -> list[Flag]`, `pair_seat(db, join_code, roll, seat_no, hostname) -> tuple[Seat, str]`, `seat_by_token(db, token) -> Seat | None`, `effective_end(exam, seat) -> float | None`, `PairError(status, message)`
  - `live`: `add_event(ctx, seat_id, kind, data, ts=None) -> Event`, `async push_seat(ctx, seat_id)`, `async push_event(ctx, event)`, `async push_flag(ctx, flag_id)`, `async raise_flag(ctx, seat_id, *, kind, severity, title, source, data=None, action="none", label=None, confidence=None, ref=None, ts=None) -> Flag`
  - HTTP: `POST /api/teacher/login {pin} -> {token}`; `require_teacher` dependency; `POST /api/teacher/exams {title, duration_min, apps}`; `POST /api/teacher/exams/{id}/files` (form `set_name`, file); `GET /api/teacher/exam -> {exam, files:[{name,set}]}`; `POST /api/pair {join_code, roll, seat_no, hostname} -> {token, seat_id, seat_no, roll, exam_title, server_time}`

- [x] **Step 1: Write the failing tests**

`server/tests/test_pairing.py`:
```python
from tide_server.exam_service import JOIN_ALPHABET, new_join_code, seat_by_token


def test_join_code_shape():
    code = new_join_code()
    assert len(code) == 6 and all(c in JOIN_ALPHABET for c in code)


def test_login_rejects_wrong_pin(client):
    assert client.post("/api/teacher/login", json={"pin": "0000"}).status_code == 401


def test_teacher_endpoints_need_token(client):
    assert client.get("/api/teacher/exam").status_code == 401


def test_create_exam_upload_files_and_read_back(teacher):
    r = teacher.post("/api/teacher/exams", json={"title": "CN Lab", "duration_min": 90,
                                                 "apps": ["VS Code", "Wireshark"]})
    assert r.status_code == 200
    exam = r.json()
    assert exam["duration_s"] == 5400 and len(exam["join_code"]) == 6
    up = teacher.post(f"/api/teacher/exams/{exam['id']}/files", data={"set_name": "A"},
                      files={"file": ("q.txt", b"Q1", "text/plain")})
    assert up.json() == {"name": "q.txt", "set": "A"}
    bad = teacher.post(f"/api/teacher/exams/{exam['id']}/files", data={"set_name": "C"},
                       files={"file": ("q.txt", b"Q1", "text/plain")})
    assert bad.status_code == 422
    got = teacher.get("/api/teacher/exam").json()
    assert got["exam"]["id"] == exam["id"]
    assert got["files"] == [{"name": "q.txt", "set": "A"}]


def test_pair_and_token_lookup(client, ctx, exam, hub):
    r = client.post("/api/pair", json={"join_code": exam.join_code.lower(), "roll": "22bcs107",
                                        "seat_no": 7, "hostname": "LAB3-PC07"})
    assert r.status_code == 200
    body = r.json()
    assert body["seat_no"] == 7 and body["roll"] == "22BCS107"
    with ctx.db() as db:
        assert seat_by_token(db, body["token"]).seat_no == 7
        assert seat_by_token(db, "nope") is None
    assert hub.console_msgs[-1]["t"] == "seat"


def test_bad_code_404(client, exam):
    r = client.post("/api/pair", json={"join_code": "ZZZZZZ", "roll": "x", "seat_no": 1})
    assert r.status_code == 404


def test_seat_taken_by_other_roll_409(client, exam):
    client.post("/api/pair", json={"join_code": exam.join_code, "roll": "A1", "seat_no": 3})
    r = client.post("/api/pair", json={"join_code": exam.join_code, "roll": "B2", "seat_no": 3})
    assert r.status_code == 409


def test_repair_same_roll_same_seat_rotates_token(client, ctx, exam):
    """Review focus #1: an agent restarted mid-exam must be able to rejoin."""
    first = client.post("/api/pair", json={"join_code": exam.join_code, "roll": "A1", "seat_no": 3}).json()
    second = client.post("/api/pair", json={"join_code": exam.join_code, "roll": "A1", "seat_no": 3}).json()
    assert second["seat_id"] == first["seat_id"]
    with ctx.db() as db:
        assert seat_by_token(db, first["token"]) is None
        assert seat_by_token(db, second["token"]).id == first["seat_id"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_pairing.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_server.exam_service'`

- [x] **Step 3: Implement**

`server/tide_server/exam_service.py`:
```python
import hashlib
import json
import secrets
from typing import Sequence

from sqlmodel import Session, select

from tide_common.policy import Policy

from tide_server import clock
from tide_server.models import Exam, ExamFile, Flag, Seat

JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I


class PairError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def new_join_code() -> str:
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(6))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_exam(db: Session, title: str, duration_s: int, apps: Sequence[str]) -> Exam:
    code = new_join_code()
    while db.exec(select(Exam).where(Exam.join_code == code)).first():
        code = new_join_code()
    exam = Exam(title=title, duration_s=duration_s, join_code=code,
                policy_json=json.dumps(Policy.from_apps(apps).to_dict()))
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def add_file(db: Session, exam_id: int, set_name: str, name: str, data: bytes) -> ExamFile:
    f = ExamFile(exam_id=exam_id, set_name=set_name, name=name, data=data)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def current_exam(db: Session) -> Exam | None:
    return db.exec(select(Exam).order_by(Exam.id.desc())).first()


def open_flags(db: Session, seat_id: int) -> list[Flag]:
    return list(db.exec(select(Flag).where(Flag.seat_id == seat_id, Flag.status == "open")).all())


def pair_seat(db: Session, join_code: str, roll: str, seat_no: int, hostname: str) -> tuple[Seat, str]:
    exam = db.exec(select(Exam).where(Exam.join_code == join_code.strip().upper())).first()
    if exam is None or exam.state == "ended":
        raise PairError(404, "Unknown join code")
    roll = roll.strip().upper()
    seat = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.seat_no == seat_no)).first()
    if seat and seat.roll != roll:
        raise PairError(409, f"Seat {seat_no} is taken")
    if seat and seat.state == "submitted":
        raise PairError(409, "Already submitted")
    token = secrets.token_urlsafe(32)
    seat = seat or Seat(exam_id=exam.id, seat_no=seat_no, roll=roll)
    seat.hostname = hostname
    seat.token_hash = hash_token(token)
    seat.last_seen = clock.now()
    db.add(seat)
    db.commit()
    db.refresh(seat)
    return seat, token


def effective_end(exam: Exam, seat: Seat) -> float | None:
    return seat.ends_at_override or exam.ends_at


def seat_by_token(db: Session, token: str) -> Seat | None:
    if not token:
        return None
    return db.exec(select(Seat).where(Seat.token_hash == hash_token(token))).first()
```

`server/tide_server/live.py`:
```python
"""Write-then-broadcast helpers. Every state change the console must see goes through here."""
import json
from typing import Any

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.exam_service import open_flags
from tide_server.models import Event, Flag, Seat
from tide_server.serialize import event_out, flag_out, seat_out


def add_event(ctx: Ctx, seat_id: int, kind: str, data: dict[str, Any] | None = None,
              ts: float | None = None) -> Event:
    with ctx.db() as db:
        e = Event(seat_id=seat_id, ts=ts or clock.now(), kind=kind, data_json=json.dumps(data or {}))
        db.add(e)
        db.commit()
        db.refresh(e)
        return e


async def push_seat(ctx: Ctx, seat_id: int) -> None:
    with ctx.db() as db:
        seat = db.get(Seat, seat_id)
        message = {"t": "seat", "seat": seat_out(seat, open_flags(db, seat_id))}
    await ctx.hub.to_console(message)


async def push_event(ctx: Ctx, event: Event) -> None:
    await ctx.hub.to_console({"t": "event", "event": event_out(event)})


async def push_flag(ctx: Ctx, flag_id: int) -> None:
    with ctx.db() as db:
        flag = db.get(Flag, flag_id)
        seat = db.get(Seat, flag.seat_id)
        message = {"t": "flag", "flag": flag_out(flag, seat.seat_no)}
    await ctx.hub.to_console(message)


async def raise_flag(ctx: Ctx, seat_id: int, *, kind: str, severity: str, title: str, source: str,
                     data: dict[str, Any] | None = None, action: str = "none",
                     label: str | None = None, confidence: float | None = None,
                     ref: str | None = None, ts: float | None = None) -> Flag:
    with ctx.db() as db:
        flag = Flag(seat_id=seat_id, ts=ts or clock.now(), kind=kind, severity=severity, title=title,
                    source=source, label=label, confidence=confidence,
                    data_json=json.dumps(data or {}), action=action, ref=ref)
        db.add(flag)
        db.commit()
        db.refresh(flag)
    await push_flag(ctx, flag.id)
    await push_seat(ctx, seat_id)
    return flag
```

`server/tide_server/api/__init__.py`: empty.

`server/tide_server/api/teacher.py`:
```python
import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import select

from tide_server.ctx import Ctx, get_ctx
from tide_server.exam_service import add_file, create_exam, current_exam
from tide_server.models import ExamFile
from tide_server.serialize import exam_out

router = APIRouter(prefix="/api/teacher")


class LoginIn(BaseModel):
    pin: str


class ExamIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    duration_min: int = Field(ge=5, le=300)
    apps: list[str]


@router.post("/login")
def login(body: LoginIn, ctx: Ctx = Depends(get_ctx)):
    if not secrets.compare_digest(body.pin, ctx.settings.teacher_pin):
        raise HTTPException(401, "Wrong PIN")
    token = secrets.token_urlsafe(24)
    ctx.teacher_tokens.add(token)
    return {"token": token}


def require_teacher(authorization: str = Header(""), ctx: Ctx = Depends(get_ctx)) -> Ctx:
    token = authorization.removeprefix("Bearer ").strip()
    if token not in ctx.teacher_tokens:
        raise HTTPException(401, "Login required")
    return ctx


@router.post("/exams")
def create(body: ExamIn, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        return exam_out(create_exam(db, body.title, body.duration_min * 60, body.apps))


@router.post("/exams/{exam_id}/files")
async def upload(exam_id: int, set_name: str = Form(...), file: UploadFile = File(...),
                 ctx: Ctx = Depends(require_teacher)):
    if set_name not in ("A", "B"):
        raise HTTPException(422, "set_name must be A or B")
    data = await file.read()
    with ctx.db() as db:
        f = add_file(db, exam_id, set_name, file.filename or "file", data)
    return {"name": f.name, "set": f.set_name}


@router.get("/exam")
def get_exam(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None:
            return {"exam": None, "files": []}
        files = db.exec(select(ExamFile).where(ExamFile.exam_id == exam.id)).all()
        return {"exam": exam_out(exam), "files": [{"name": f.name, "set": f.set_name} for f in files]}
```

`server/tide_server/api/agent.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tide_server import clock
from tide_server.ctx import Ctx, get_ctx
from tide_server.exam_service import PairError, pair_seat
from tide_server.live import add_event, push_event, push_seat
from tide_server.models import Exam

router = APIRouter()


class PairIn(BaseModel):
    join_code: str
    roll: str = Field(min_length=1, max_length=20)
    seat_no: int = Field(ge=1, le=200)
    hostname: str = ""


@router.post("/api/pair")
async def pair(body: PairIn, ctx: Ctx = Depends(get_ctx)):
    with ctx.db() as db:
        try:
            seat, token = pair_seat(db, body.join_code, body.roll, body.seat_no, body.hostname)
        except PairError as e:
            raise HTTPException(e.status, e.message)
        exam = db.get(Exam, seat.exam_id)
    await push_event(ctx, add_event(ctx, seat.id, "joined", {"hostname": body.hostname}))
    await push_seat(ctx, seat.id)
    return {"token": token, "seat_id": seat.id, "seat_no": seat.seat_no, "roll": seat.roll,
            "exam_title": exam.title, "server_time": clock.now()}
```

`server/tide_server/app.py` (replace):
```python
from fastapi import FastAPI

from tide_server.api import agent, teacher
from tide_server.config import Settings
from tide_server.ctx import Ctx
from tide_server.db import make_engine
from tide_server.hub import Hub


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Tide")
    app.state.ctx = Ctx(settings=settings, engine=make_engine(settings.data_dir), hub=Hub())
    app.include_router(teacher.router)
    app.include_router(agent.router)
    return app
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add server
git commit -m "feat(server): exams, question files, teacher login, seat pairing"
```

### Task 6: Agent WebSocket, heartbeats, offline detection

**Files:**
- Create: `server/tide_server/ingest.py`, `server/tide_server/monitor.py`
- Modify: `server/tide_server/api/agent.py` (add `/ws/agent`, `welcome_message`), `server/tide_server/app.py` (Ctx gets `ingest`)
- Test: `server/tests/test_agent_ws.py`

**Interfaces:**
- Consumes: `seat_by_token`, `live.*`, `exam_policy`
- Produces:
  - `Ingest(ctx)` with `async handle(seat_id, message)`; handler methods named `_on_<t>`. This task adds `_on_heartbeat`.
  - `welcome_message(db, seat) -> dict` = `{"t":"welcome","seat_no","roll","set","policy","server_time","exam_state","ends_at"}`
  - `async monitor.tick(ctx)` (uses `exam_service.effective_end`), `async monitor.run(ctx, interval=2.0)`
  - WS close code `4401` for a bad or missing hello.

- [x] **Step 1: Write the failing tests**

`server/tests/test_agent_ws.py`:
```python
import pytest
from starlette.websockets import WebSocketDisconnect

from tide_server import clock, monitor
from tide_server.models import Event, Flag, Seat
from sqlmodel import select


def test_bad_token_is_rejected(client, paired):
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_hello_gets_welcome_with_policy(client, paired):
    seat, token = paired
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token, "agent_version": "0.1", "local_time": 0})
        w = ws.receive_json()
    assert w["t"] == "welcome"
    assert w["seat_no"] == 7 and w["exam_state"] == "lobby"
    assert "code.exe" in w["policy"]["allowed_processes"]


def test_heartbeat_updates_last_seen_and_app(client, ctx, paired, monkeypatch):
    seat, token = paired
    monkeypatch.setattr(clock, "now", lambda: 5000.0)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token})
        ws.receive_json()
        ws.send_json({"t": "heartbeat", "fg": "Code.exe"})
        ws.send_json({"t": "heartbeat", "fg": "Code.exe"})   # second message proves the first was processed
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
    assert s.last_seen == 5000.0 and s.fg_app == "VS Code"


async def test_monitor_marks_offline_then_back(ctx, paired, hub, monkeypatch):
    seat, _ = paired
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
        s.state, s.last_seen = "live", 100.0
        db.add(s)
        db.commit()
    monkeypatch.setattr(clock, "now", lambda: 111.0)
    await monitor.tick(ctx)
    await monitor.tick(ctx)   # idempotent: still one flag
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
        flags = db.exec(select(Flag).where(Flag.kind == "agent_offline")).all()
    assert s.state == "offline" and s.resume_state == "live"
    assert len(flags) == 1 and flags[0].severity == "critical"

    monkeypatch.setattr(clock, "now", lambda: 130.0)
    await ctx.ingest.handle(seat.id, {"t": "heartbeat", "fg": "code.exe"})
    with ctx.db() as db:
        s = db.get(Seat, seat.id)
        back = db.exec(select(Event).where(Event.kind == "agent_back")).one()
    assert s.state == "live"
    assert '"gap": 30' in back.data_json
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_agent_ws.py -v`
Expected: FAIL (404 on `/ws/agent` / missing `monitor`)

- [x] **Step 3: Implement**

`server/tide_server/ingest.py`:
```python
"""Everything an agent says, in one place. One `_on_<type>` method per message type."""
from typing import Any

from tide_common.policy import display_app

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.live import add_event, push_event, push_seat
from tide_server.models import Seat


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
```

`server/tide_server/monitor.py`:
```python
"""Background checks: silent agents go grey; time-up seats get told to submit."""
import asyncio

from sqlmodel import select

from tide_common.protocol import msg

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.exam_service import current_exam, effective_end
from tide_server.live import raise_flag
from tide_server.models import Seat

WATCHED_STATES = ("lobby", "ready", "blocked", "live")


async def tick(ctx: Ctx) -> None:
    t = clock.now()
    went_offline: list[int] = []
    to_end: list[int] = []
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None:
            return
        seats = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.simulated == False)).all()  # noqa: E712
        for seat in seats:
            if seat.state in WATCHED_STATES and t - seat.last_seen > ctx.settings.heartbeat_timeout_s:
                seat.resume_state = seat.state
                seat.state = "offline"
                db.add(seat)
                went_offline.append(seat.id)
            end = effective_end(exam, seat)
            if (exam.state == "live" and seat.state == "live" and end and t >= end
                    and seat.id not in ctx.ended_seats):
                to_end.append(seat.id)
        if exam.state == "live" and exam.ends_at:
            latest = max([effective_end(exam, s) or 0 for s in seats] + [exam.ends_at])
            if t >= latest + 60:
                exam.state = "ended"
                db.add(exam)
        db.commit()
    for seat_id in went_offline:
        await raise_flag(ctx, seat_id, kind="agent_offline", severity="critical",
                         title="Agent offline", source="server")
    for seat_id in to_end:
        ctx.ended_seats.add(seat_id)
        await ctx.hub.to_agent(seat_id, msg("end", reason="time"))


async def run(ctx: Ctx, interval: float = 2.0) -> None:
    while True:
        try:
            await tick(ctx)
        except Exception as e:  # keep the loop alive during a demo
            print(f"[monitor] {e!r}")
        await asyncio.sleep(interval)
```

Add to `server/tide_server/api/agent.py` (new imports at top, new code at bottom):
```python
import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from sqlmodel import Session

from tide_common.protocol import msg

from tide_server.exam_service import current_exam, effective_end, seat_by_token
from tide_server.models import Seat
from tide_server.serialize import exam_policy


def welcome_message(db: Session, seat: Seat) -> dict:
    exam = db.get(Exam, seat.exam_id)
    policy = exam_policy(exam)
    return msg("welcome", seat_no=seat.seat_no, roll=seat.roll, set=seat.set_name,
               policy=policy.to_dict(), server_time=clock.now(), exam_state=exam.state,
               ends_at=effective_end(exam, seat) if exam.state == "live" else None)


@router.websocket("/ws/agent")
async def ws_agent(ws: WebSocket):
    ctx: Ctx = ws.app.state.ctx
    await ws.accept()
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=5)
    except Exception:
        await ws.close(code=4401)
        return
    with ctx.db() as db:
        seat = seat_by_token(db, hello.get("token", "")) if hello.get("t") == "hello" else None
        if seat is None:
            await ws.close(code=4401)
            return
        seat_id = seat.id
        welcome = welcome_message(db, seat)
    ctx.hub.add_agent(seat_id, ws)
    await ws.send_json(welcome)
    await ctx.ingest.handle(seat_id, {"t": "heartbeat"})
    try:
        while True:
            await ctx.ingest.handle(seat_id, await ws.receive_json())
    except WebSocketDisconnect:
        pass
    finally:
        ctx.hub.remove_agent(seat_id, ws)
```
(`current_exam` is imported now because Task 9 uses it in this file.)

`server/tide_server/app.py` (replace):
```python
from fastapi import FastAPI

from tide_server.api import agent, teacher
from tide_server.config import Settings
from tide_server.ctx import Ctx
from tide_server.db import make_engine
from tide_server.hub import Hub
from tide_server.ingest import Ingest


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = Ctx(settings=settings, engine=make_engine(settings.data_dir), hub=Hub())
    ctx.ingest = Ingest(ctx)
    app = FastAPI(title="Tide")
    app.state.ctx = ctx
    app.include_router(teacher.router)
    app.include_router(agent.router)
    return app
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add server
git commit -m "feat(server): agent websocket, heartbeats, offline detection"
```

### Task 7: Classifier pipeline — heuristics, Jev via OpenRouter, cache

**Files:**
- Create: `server/tide_server/classify/__init__.py`, `describe.py`, `heuristics.py`, `jev.py`, `pipeline.py`
- Test: `server/tests/test_classify.py`

**Interfaces:**
- Consumes: `Signal`, `display_app`
- Produces:
  - `Verdict(label: str, confidence: float, violation: float, source: "jev"|"heuristic", cached: bool = False, raw: dict | None = None)` (frozen dataclass, in `heuristics.py`)
  - `LABELS`, `LABEL_TEXT: dict[str,str]`
  - `describe(signal, apps) -> str`, `cache_key(signal) -> str`
  - `classify_heuristic(text) -> Verdict` (confidence ≤ 0.70, always)
  - `JevClassifier(url, key, model, client=None)` with `request_body(text) -> dict`, `parse(body) -> Verdict` (static), `async classify(text) -> Verdict`, raises `JevError`
  - `Pipeline(jev: JevClassifier | None)` with `.mode -> "jev"|"heuristics"`, `async classify(signal, apps) -> Verdict`, `.cache: dict[str, Verdict]`

**Jev over OpenRouter.** Endpoint `POST https://openrouter.ai/api/alpha/decisions`, header `Authorization: Bearer $OPENROUTER_API_KEY`, body `{"model", "state", "questions"}`. A `choice` answer returns `choice`, `confidence` and `probabilities`; a `noul` answer returns `noul` (probability of yes). Tide's `confidence` is the **probability of the chosen label**, which is what the 0.90 auto-act gate means. Jev's own `confidence` value is kept in `raw` for the evidence panel. Reference: https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request

- [x] **Step 1: Write the failing tests**

`server/tests/test_classify.py`:
```python
import json

import httpx
import pytest

from tide_common.protocol import Kind, Signal
from tide_server.classify.describe import cache_key, describe
from tide_server.classify.heuristics import classify_heuristic
from tide_server.classify.jev import JevClassifier, JevError
from tide_server.classify.pipeline import Pipeline

APPS = ["VS Code", "Wireshark"]
POE = Signal(kind=Kind.WINDOW, data={"process": "chrome.exe", "title": "Fast AI Chat - Poe",
                                     "host": "poe.com", "description": "Google Chrome"})

JEV_REPLY = {
    "id": "gen-dec-1", "model": "typesafe/jev-1.13-20260917", "provider": "TypeSafe",
    "answers": {
        "activity": {"type": "choice", "choice": "ai_assistant", "confidence": 0.81,
                     "probabilities": {"ai_assistant": 0.96, "web_lookup": 0.03, "other": 0.01}},
        "violation": {"type": "noul", "noul": 0.97},
    },
    "usage": {"input_tokens": 300, "output_tokens": 20, "cost": 0.00001},
}


def jev_with(handler):
    return JevClassifier("https://openrouter.ai/api/alpha/decisions", "k", "~typesafe/jev-latest",
                         client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_describe_includes_policy_and_event():
    text = describe(POE, APPS)
    assert "allowed = VS Code, Wireshark" in text
    assert 'title:   "Fast AI Chat - Poe"' in text and "host:    poe.com" in text


def test_cache_key_ignores_title_for_browsers():
    other_page = Signal(kind=Kind.WINDOW, data={**POE.data, "title": "Another chat - Poe"})
    assert cache_key(POE) == cache_key(other_page) == "chrome.exe|poe.com"


def test_heuristic_never_confident_enough_to_act():
    v = classify_heuristic(describe(POE, APPS))
    assert v.label == "ai_assistant" and v.source == "heuristic" and v.confidence <= 0.70
    assert classify_heuristic("process: game.exe title: Solitaire").label == "other"


def test_jev_request_body_shape():
    body = jev_with(lambda r: None).request_body("STATE")
    assert body["model"] == "~typesafe/jev-latest" and body["state"] == "STATE"
    assert body["questions"]["activity"]["type"] == "choice"
    assert "ai_assistant" in body["questions"]["activity"]["criteria"]
    assert body["questions"]["violation"]["type"] == "noul"
    assert set(body["questions"]["violation"]["criteria"]) == {"true", "false"}


def test_jev_parse_uses_choice_probability():
    v = JevClassifier.parse(JEV_REPLY)
    assert (v.label, v.confidence, v.violation, v.source) == ("ai_assistant", 0.96, 0.97, "jev")
    assert v.raw["jev_confidence"] == 0.81


async def test_jev_http_call_sends_auth():
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=JEV_REPLY)

    v = await jev_with(handler).classify("STATE")
    assert seen["auth"] == "Bearer k" and seen["body"]["state"] == "STATE"
    assert v.label == "ai_assistant"


async def test_jev_http_error_raises():
    with pytest.raises(JevError):
        await jev_with(lambda r: httpx.Response(500, text="boom")).classify("STATE")


async def test_pipeline_caches_jev_answers():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=JEV_REPLY)

    p = Pipeline(jev_with(handler))
    first = await p.classify(POE, APPS)
    second = await p.classify(POE, APPS)
    assert len(calls) == 1 and not first.cached and second.cached and second.source == "jev"


async def test_pipeline_falls_back_to_heuristics_on_jev_failure_and_retries_later():
    """Review focus #5."""
    p = Pipeline(jev_with(lambda r: httpx.Response(503)))
    v = await p.classify(POE, APPS)
    assert v.source == "heuristic" and cache_key(POE) not in p.cache


async def test_pipeline_without_key_is_heuristics_mode():
    p = Pipeline(None)
    assert p.mode == "heuristics"
    assert (await p.classify(POE, APPS)).source == "heuristic"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_classify.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_server.classify'`

- [x] **Step 3: Implement**

`server/tide_server/classify/__init__.py`: empty.

`server/tide_server/classify/heuristics.py`:
```python
"""Keyword fallback when Jev is unavailable. Deliberately capped below the auto-act threshold."""
import re
from dataclasses import dataclass, field
from typing import Any

LABELS = ("allowed_tool", "ai_assistant", "communication", "web_lookup", "remote_or_file_share", "other")
LABEL_TEXT = {"allowed_tool": "Allowed tool", "ai_assistant": "AI assistant",
              "communication": "Messaging", "web_lookup": "Web lookup",
              "remote_or_file_share": "Remote / file share", "other": "Other app"}


@dataclass(frozen=True)
class Verdict:
    label: str
    confidence: float
    violation: float
    source: str                 # "jev" | "heuristic"
    cached: bool = False
    raw: dict[str, Any] | None = field(default=None, compare=False)


_RULES: list[tuple[str, re.Pattern]] = [
    ("ai_assistant", re.compile(r"\b(gpt|chatgpt|ai|copilot|gemini|claude|llm|assistant|chatbot|"
                                r"poe|deepseek|perplexity|mistral|grok|notegpt|bard)\b")),
    ("communication", re.compile(r"\b(whatsapp|telegram|gmail|inbox|mail|outlook|messenger|"
                                 r"discord|slack|instagram|snapchat)\b")),
    ("remote_or_file_share", re.compile(r"\b(anydesk|teamviewer|rustdesk|drive|dropbox|"
                                        r"wetransfer|onedrive|remote)\b")),
    ("web_lookup", re.compile(r"\b(stackoverflow|geeksforgeeks|w3schools|github|google|bing|"
                              r"tutorialspoint|leetcode|search)\b")),
]


def classify_heuristic(text: str) -> Verdict:
    low = text.lower()
    for label, pattern in _RULES:
        if pattern.search(low):
            return Verdict(label, 0.70, 0.70, "heuristic")
    return Verdict("other", 0.30, 0.30, "heuristic")
```

`server/tide_server/classify/describe.py`:
```python
import re
from typing import Sequence

from tide_common.policy import BROWSERS
from tide_common.protocol import Signal


def describe(signal: Signal, apps: Sequence[str]) -> str:
    d = signal.data
    lines = [f"Exam policy: allowed = {', '.join(apps)}. Browsers may only show local files.",
             f"Event: {signal.kind}",
             f"  process: {d.get('process', '')}  ({d.get('description') or d.get('original_name') or ''})",
             f'  title:   "{d.get("title", "")}"']
    if d.get("host") is not None:
        lines.append(f"  host:    {d.get('host')}")
    return "\n".join(lines)


def cache_key(signal: Signal) -> str:
    d = signal.data
    process = (d.get("process") or "").lower()
    if process in BROWSERS and d.get("host"):
        return f"{process}|{d['host'].lower()}"
    title = re.sub(r"\d+", "#", (d.get("title") or "").lower())[:80]
    return f"{process}|{title}"
```

`server/tide_server/classify/jev.py`:
```python
"""Jev (TypeSafe) through OpenRouter's Decisions API."""
from typing import Any

import httpx

from .heuristics import Verdict

ACTIVITY_CRITERIA = {
    "allowed_tool": "An app the exam policy allows (editor, terminal, file explorer, packet analyzer, VM), or a local file.",
    "ai_assistant": "An AI chatbot, AI coding assistant, or any AI tool that answers questions or writes code.",
    "communication": "Messaging, chat, social media, or email.",
    "web_lookup": "Searching or reading websites for answers: search engines, Q&A, tutorials, code sites.",
    "remote_or_file_share": "Remote desktop, screen sharing, cloud drives, or file transfer.",
    "other": "Anything else, such as games, media, or system utilities.",
}


class JevError(Exception):
    pass


class JevClassifier:
    def __init__(self, url: str, key: str, model: str, client: httpx.AsyncClient | None = None,
                 timeout: float = 4.0) -> None:
        self.url, self.key, self.model = url, key, model
        self.client = client or httpx.AsyncClient(timeout=timeout)

    def request_body(self, text: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "state": text,
            "questions": {
                "activity": {"type": "choice", "instructions": "What is the student using right now?",
                             "criteria": ACTIVITY_CRITERIA},
                "violation": {"type": "noul", "instructions": "Does this break the exam policy?",
                              "criteria": {
                                  "true": "The student is using something the policy does not allow, or anything that could give outside help.",
                                  "false": "The student is using an allowed tool or doing ordinary local work."}},
            },
        }

    @staticmethod
    def parse(body: dict[str, Any]) -> Verdict:
        a = body["answers"]["activity"]
        choice = a["choice"]
        probs = a.get("probabilities") or {}
        confidence = float(probs.get(choice, a.get("confidence", 0.0)))
        violation = float(body["answers"]["violation"]["noul"])
        return Verdict(choice, round(confidence, 3), round(violation, 3), "jev",
                       raw={"jev_confidence": a.get("confidence"), "probabilities": probs,
                            "model": body.get("model")})

    async def classify(self, text: str) -> Verdict:
        try:
            r = await self.client.post(self.url, json=self.request_body(text),
                                       headers={"Authorization": f"Bearer {self.key}", "X-Title": "Tide"})
            r.raise_for_status()
            return self.parse(r.json())
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            raise JevError(repr(e)) from e
```

`server/tide_server/classify/pipeline.py`:
```python
from dataclasses import replace
from typing import Sequence

from tide_common.protocol import Signal

from .describe import cache_key, describe
from .heuristics import Verdict, classify_heuristic
from .jev import JevClassifier, JevError


class Pipeline:
    """cache -> Jev -> heuristics. Only Jev answers are cached, so a Jev outage heals itself."""

    def __init__(self, jev: JevClassifier | None) -> None:
        self.jev = jev
        self.cache: dict[str, Verdict] = {}
        self.last_error: str | None = None

    @property
    def mode(self) -> str:
        return "jev" if self.jev else "heuristics"

    async def classify(self, signal: Signal, apps: Sequence[str]) -> Verdict:
        key = cache_key(signal)
        if key in self.cache:
            return replace(self.cache[key], cached=True)
        text = describe(signal, apps)
        if self.jev is not None:
            try:
                verdict = await self.jev.classify(text)
                self.cache[key] = verdict
                self.last_error = None
                return verdict
            except JevError as e:
                self.last_error = str(e)
        return classify_heuristic(text)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add server
git commit -m "feat(server): Jev classifier via OpenRouter with cache and heuristic fallback"
```

### Task 8: Decisions and agent flags/signals/evidence

**Files:**
- Create: `server/tide_server/decide.py`
- Modify: `server/tide_server/ingest.py` (add `_on_flag`, `_on_signal`, `_on_event`, `_on_evidence`), `server/tide_server/app.py` (build the `Pipeline`)
- Test: `server/tests/test_decide_ingest.py`

**Interfaces:**
- Consumes: `Verdict`, `Pipeline`, `live.raise_flag`, `exam_policy`
- Produces:
  - `Decision(flag: bool, severity: str, action: str)`; `decide(verdict, is_browser, auto_act_min=0.90) -> Decision`; `AUTO_ACT_LABELS`
  - Agent → server messages handled: `flag {ref, kind, severity, title, data, ts, action, result}`, `signal {kind, data, ts}`, `event {kind, data, ts}`, `evidence {ref | flag_id, jpeg_b64}`
  - Server → agent: `act {action, target:{pid,hwnd,process,host}, reason, flag_id}`
  - Screenshots saved to `<data_dir>/shots/<flag_id>.jpg`; `Flag.screenshot` holds the file name

- [x] **Step 1: Write the failing tests**

`server/tests/test_decide_ingest.py`:
```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_decide_ingest.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_server.decide'`

- [x] **Step 3: Implement**

`server/tide_server/decide.py`:
```python
from typing import NamedTuple

from tide_server.classify.heuristics import Verdict

AUTO_ACT_LABELS = frozenset({"ai_assistant", "communication", "remote_or_file_share"})


class Decision(NamedTuple):
    action: str      # none | close_tab | kill
    severity: str    # info | medium | high | critical
    flag: bool


def decide(v: Verdict, is_browser: bool, auto_act_min: float = 0.90) -> Decision:
    if v.source == "jev" and v.label in AUTO_ACT_LABELS and v.confidence >= auto_act_min:
        return Decision("close_tab" if is_browser else "kill", "critical", True)
    if v.violation >= 0.80:
        return Decision("none", "high", True)
    if v.violation >= 0.60:
        return Decision("none", "medium", True)
    return Decision("none", "info", False)
```

Add to `server/tide_server/ingest.py` — new imports:
```python
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
```
New module-level helper and methods inside `class Ingest`:
```python
def display_name(data: dict) -> str:
    if data.get("host"):
        return data["host"]
    process = data.get("process") or ""
    return display_app(process) if process else (data.get("title") or "Unknown")[:40]
```
```python
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
```
(`json` is used by later tasks in this file; keep the import.)

`server/tide_server/app.py` (replace):
```python
from fastapi import FastAPI

from tide_server.api import agent, teacher
from tide_server.classify.jev import JevClassifier
from tide_server.classify.pipeline import Pipeline
from tide_server.config import Settings
from tide_server.ctx import Ctx
from tide_server.db import make_engine
from tide_server.hub import Hub
from tide_server.ingest import Ingest


def build_pipeline(settings: Settings) -> Pipeline:
    if not settings.openrouter_api_key:
        return Pipeline(None)
    return Pipeline(JevClassifier(settings.jev_url, settings.openrouter_api_key, settings.jev_model))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = Ctx(settings=settings, engine=make_engine(settings.data_dir), hub=Hub())
    ctx.pipeline = build_pipeline(settings)
    ctx.ingest = Ingest(ctx)
    app = FastAPI(title="Tide")
    app.state.ctx = ctx
    app.include_router(teacher.router)
    app.include_router(agent.router)
    return app
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add server
git commit -m "feat(server): decide act/flag/log and ingest agent flags, signals, evidence"
```

### Task 9: Start, sets, clock, pre-flight, teacher controls

**Files:**
- Modify: `server/tide_server/exam_service.py` (sets, start, extend, start message), `server/tide_server/live.py` (`deliver`), `server/tide_server/ingest.py` (`_on_preflight`), `server/tide_server/api/agent.py` (re-deliver on reconnect), `server/tide_server/api/teacher.py` (start/extend/notice/warn/force-submit)
- Test: `server/tests/test_start_clock.py`

**Interfaces:**
- Consumes: `effective_end(exam, seat)` (exam_service), `Hub.to_agent`
- Produces:
  - `set_for_seat(seat_no, available: set[str]) -> "A"|"B"`, `sets_available(db, exam_id) -> set[str]`, `go_live(db, exam, seat) -> None`, `start_exam(db, exam) -> list[int]` (seat ids to deliver), `extend(db, exam, seat_id: int | None, minutes: int) -> list[tuple[int, float]]`, `start_message(db, exam, seat) -> dict`
  - `live.deliver(ctx, seat_id)` sends `start {set, files:[{name,b64}], ends_at}` and logs a `start` event
  - Agent → server `preflight {internet, extensions, denied_closed, inventory_count}`
  - Server → agent `time {ends_at}`, `notice {text}`, `end {reason}`
  - HTTP: `POST /api/teacher/start`, `POST /api/teacher/extend {minutes, seat_id?}`, `POST /api/teacher/notice {text}`, `POST /api/teacher/seats/{id}/warn {text?}`, `POST /api/teacher/seats/{id}/force-submit`

- [x] **Step 1: Write the failing tests**

`server/tests/test_start_clock.py`:
```python
import base64

from sqlmodel import select

from tide_server import clock, monitor
from tide_server.exam_service import add_file, pair_seat, set_for_seat
from tide_server.models import Exam, Flag, Seat


def test_set_for_seat():
    assert set_for_seat(7, {"A", "B"}) == "A"
    assert set_for_seat(8, {"A", "B"}) == "B"
    assert set_for_seat(8, {"A"}) == "A"


def _seed(ctx, exam):
    with ctx.db() as db:
        add_file(db, exam.id, "A", "qA.txt", b"set A question")
        add_file(db, exam.id, "B", "qB.txt", b"set B question")
        seats = {n: pair_seat(db, exam.join_code, f"R{n}", n, "")[0].id for n in (7, 8, 9)}
    return seats


async def test_start_delivers_only_to_offline_ready_seats(ctx, teacher, exam, hub, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    seats = _seed(ctx, exam)
    await ctx.ingest.handle(seats[7], {"t": "preflight", "internet": False, "extensions": ["GitHub Copilot"],
                                       "denied_closed": [], "inventory_count": 12})
    await ctx.ingest.handle(seats[7], {"t": "preflight", "internet": False, "extensions": ["GitHub Copilot"],
                                       "denied_closed": [], "inventory_count": 12})
    await ctx.ingest.handle(seats[8], {"t": "preflight", "internet": False, "extensions": [],
                                       "denied_closed": ["WhatsApp"], "inventory_count": 3})
    await ctx.ingest.handle(seats[9], {"t": "preflight", "internet": True, "extensions": [],
                                       "denied_closed": [], "inventory_count": 0})
    r = teacher.post("/api/teacher/start")
    assert r.status_code == 200 and r.json()["ends_at"] == 1000.0 + 5400

    starts = {sid: m for sid, m in hub.agent_msgs if m["t"] == "start"}
    assert set(starts) == {seats[7], seats[8]}
    assert starts[seats[7]]["set"] == "A" and starts[seats[8]]["set"] == "B"
    assert base64.b64decode(starts[seats[8]]["files"][0]["b64"]) == b"set B question"
    with ctx.db() as db:
        assert db.get(Seat, seats[9]).state == "blocked"
        assert len(db.exec(select(Flag).where(Flag.kind == "ai_extension")).all()) == 1

    # seat 9 disconnects from the internet -> gets its questions late
    await ctx.ingest.handle(seats[9], {"t": "preflight", "internet": False, "extensions": [],
                                       "denied_closed": [], "inventory_count": 0})
    late = [m for sid, m in hub.agent_msgs if sid == seats[9] and m["t"] == "start"]
    assert late and late[0]["set"] == "A"


async def test_extend_per_seat_and_global(ctx, teacher, exam, hub, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    seats = _seed(ctx, exam)
    for n in (7, 8):
        await ctx.ingest.handle(seats[n], {"t": "preflight", "internet": False, "extensions": [],
                                           "denied_closed": [], "inventory_count": 0})
    teacher.post("/api/teacher/start")
    teacher.post("/api/teacher/extend", json={"minutes": 5, "seat_id": seats[7]})
    times = [(sid, m["ends_at"]) for sid, m in hub.agent_msgs if m["t"] == "time"]
    assert times == [(seats[7], 1000.0 + 5400 + 300)]
    teacher.post("/api/teacher/extend", json={"minutes": 5})
    with ctx.db() as db:
        assert db.get(Exam, exam.id).ends_at == 1000.0 + 5400 + 300
        assert db.get(Seat, seats[7]).ends_at_override == 1000.0 + 5400 + 600


async def test_monitor_ends_seats_when_time_is_up(ctx, teacher, exam, hub, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    seats = _seed(ctx, exam)
    await ctx.ingest.handle(seats[7], {"t": "preflight", "internet": False, "extensions": [],
                                       "denied_closed": [], "inventory_count": 0})
    teacher.post("/api/teacher/start")
    monkeypatch.setattr(clock, "now", lambda: 1000.0 + 5400)
    with ctx.db() as db:
        s = db.get(Seat, seats[7])
        s.last_seen = 1000.0 + 5400
        db.add(s)
        db.commit()
    await monitor.tick(ctx)
    await monitor.tick(ctx)
    ends = [sid for sid, m in hub.agent_msgs if m["t"] == "end"]
    assert ends == [seats[7]]


def test_reconnect_during_live_redelivers(client, ctx, exam, monkeypatch):
    """Review focus #1: a restarted agent gets its set and the server end time again."""
    monkeypatch.setattr(clock, "now", lambda: 1000.0)
    with ctx.db() as db:
        add_file(db, exam.id, "A", "qA.txt", b"A")
        seat, token = pair_seat(db, exam.join_code, "R7", 7, "")
    login = client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token})
        ws.receive_json()
        ws.send_json({"t": "preflight", "internet": False, "extensions": [], "denied_closed": [],
                      "inventory_count": 0})
        client.post("/api/teacher/start", headers={"Authorization": f"Bearer {login}"})
        assert ws.receive_json()["t"] == "start"
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_json({"t": "hello", "token": token})
        welcome = ws.receive_json()
        again = ws.receive_json()
    assert welcome["exam_state"] == "live" and welcome["ends_at"] == 1000.0 + 5400
    assert again["t"] == "start" and again["set"] == "A"


def test_warn_and_force_submit(teacher, ctx, paired, hub):
    seat, _ = paired
    teacher.post(f"/api/teacher/seats/{seat.id}/warn", json={"text": "Eyes on your screen"})
    teacher.post(f"/api/teacher/seats/{seat.id}/force-submit")
    kinds = [m["t"] for sid, m in hub.agent_msgs if sid == seat.id]
    assert kinds == ["notice", "end"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_start_clock.py -v`
Expected: FAIL, `ImportError: cannot import name 'set_for_seat'`

- [x] **Step 3: Implement**

Append to `server/tide_server/exam_service.py` (add `import base64` and `from tide_common.protocol import msg` to the imports):
```python
def set_for_seat(seat_no: int, available: set[str]) -> str:
    return "B" if seat_no % 2 == 0 and "B" in available else "A"


def sets_available(db: Session, exam_id: int) -> set[str]:
    return {f.set_name for f in db.exec(select(ExamFile).where(ExamFile.exam_id == exam_id)).all()}


def go_live(db: Session, exam: Exam, seat: Seat) -> None:
    seat.set_name = seat.set_name or set_for_seat(seat.seat_no, sets_available(db, exam.id))
    seat.state = "live"
    db.add(seat)


def start_exam(db: Session, exam: Exam) -> list[int]:
    t = clock.now()
    exam.state, exam.started_at, exam.ends_at = "live", t, t + exam.duration_s
    db.add(exam)
    ready = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.state == "ready")).all()
    for seat in ready:
        go_live(db, exam, seat)
    db.commit()
    return [s.id for s in ready]


def extend(db: Session, exam: Exam, seat_id: int | None, minutes: int) -> list[tuple[int, float]]:
    delta = minutes * 60
    changed: list[tuple[int, float]] = []
    if seat_id is None:
        exam.ends_at = (exam.ends_at or clock.now()) + delta
        db.add(exam)
        seats = db.exec(select(Seat).where(Seat.exam_id == exam.id)).all()
        for s in seats:
            if s.ends_at_override:
                s.ends_at_override += delta
                db.add(s)
        db.commit()
        return [(s.id, effective_end(exam, s)) for s in seats if s.state in ("live", "offline")]
    seat = db.get(Seat, seat_id)
    seat.ends_at_override = (effective_end(exam, seat) or clock.now()) + delta
    db.add(seat)
    db.commit()
    changed.append((seat.id, seat.ends_at_override))
    return changed


def start_message(db: Session, exam: Exam, seat: Seat) -> dict:
    files = db.exec(select(ExamFile).where(ExamFile.exam_id == exam.id,
                                           ExamFile.set_name == seat.set_name)).all()
    return msg("start", set=seat.set_name,
               files=[{"name": f.name, "b64": base64.b64encode(f.data).decode()} for f in files],
               ends_at=effective_end(exam, seat))
```

Append to `server/tide_server/live.py` (add `from tide_server.exam_service import start_message` and `from tide_server.models import Exam`):
```python
async def deliver(ctx: Ctx, seat_id: int) -> None:
    with ctx.db() as db:
        seat = db.get(Seat, seat_id)
        message = start_message(db, db.get(Exam, seat.exam_id), seat)
    await ctx.hub.to_agent(seat_id, message)
    await push_event(ctx, add_event(ctx, seat_id, "start", {"set": message["set"],
                                                           "files": len(message["files"])}))
    await push_seat(ctx, seat_id)
```

Add to `class Ingest` in `server/tide_server/ingest.py` (add `from tide_server.exam_service import go_live` and `from tide_server.live import deliver`):
```python
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
```

In `server/tide_server/api/agent.py`, inside `ws_agent`, replace the line `await ctx.ingest.handle(seat_id, {"t": "heartbeat"})` with:
```python
    await ctx.ingest.handle(seat_id, {"t": "heartbeat"})
    if welcome["exam_state"] == "live" and welcome["set"]:
        await deliver(ctx, seat_id)
```
and add `from tide_server.live import deliver` to its imports.

Append to `server/tide_server/api/teacher.py` (add imports `from tide_common.protocol import msg`, `from tide_server.exam_service import extend, start_exam`, `from tide_server.live import add_event, deliver, push_event`, `from tide_server.models import Exam, Seat`):
```python
class ExtendIn(BaseModel):
    minutes: int = Field(ge=1, le=120)
    seat_id: int | None = None


class TextIn(BaseModel):
    text: str = Field(default="Please keep your eyes on your own screen.", max_length=200)


def _exam(db) -> Exam:
    exam = current_exam(db)
    if exam is None:
        raise HTTPException(404, "No exam")
    return exam


@router.post("/start")
async def start(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        exam = _exam(db)
        if exam.state != "lobby":
            raise HTTPException(409, "Exam already started")
        seat_ids = start_exam(db, exam)
        out = exam_out(exam)
    await ctx.hub.to_console({"t": "exam", "exam": out})
    for seat_id in seat_ids:
        await deliver(ctx, seat_id)
    return out


@router.post("/extend")
async def extend_time(body: ExtendIn, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        exam = _exam(db)
        changed = extend(db, exam, body.seat_id, body.minutes)
        out = exam_out(exam)
    for seat_id, ends_at in changed:
        await ctx.hub.to_agent(seat_id, msg("time", ends_at=ends_at))
    if body.seat_id is None:
        await ctx.hub.to_console({"t": "exam", "exam": out})
    else:
        await push_event(ctx, add_event(ctx, body.seat_id, "teacher", {"text": f"+{body.minutes} min"}))
    return {"ok": True}


@router.post("/notice")
async def notice(body: TextIn, ctx: Ctx = Depends(require_teacher)):
    for seat_id in list(ctx.hub.agents):
        await ctx.hub.to_agent(seat_id, msg("notice", text=body.text))
    return {"ok": True}


@router.post("/seats/{seat_id}/warn")
async def warn(seat_id: int, body: TextIn, ctx: Ctx = Depends(require_teacher)):
    await ctx.hub.to_agent(seat_id, msg("notice", text=body.text))
    await push_event(ctx, add_event(ctx, seat_id, "teacher", {"text": "Warned"}))
    return {"ok": True}


@router.post("/seats/{seat_id}/force-submit")
async def force_submit(seat_id: int, ctx: Ctx = Depends(require_teacher)):
    ctx.ended_seats.add(seat_id)
    await ctx.hub.to_agent(seat_id, msg("end", reason="teacher"))
    await push_event(ctx, add_event(ctx, seat_id, "teacher", {"text": "Force submit"}))
    return {"ok": True}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add server
git commit -m "feat(server): start exam, odd/even sets, server clock, pre-flight gating, teacher controls"
```

### Task 10: Snapshots, code bursts, submissions, similarity, results

**Files:**
- Create: `server/tide_server/burst.py`, `server/tide_server/similarity.py`
- Modify: `server/tide_server/ingest.py` (`_on_snapshot`), `server/tide_server/api/agent.py` (`POST /api/submit`), `server/tide_server/api/teacher.py` (results endpoints), `server/tide_server/serialize.py` (`KIND_TEXT`)
- Test: `server/tests/test_results.py`

**Interfaces:**
- Consumes: `fingerprints`, `similarity` (tide_common)
- Produces:
  - `burst_lines(before: int, after: int, threshold: int = 40) -> int | None`
  - `count_lines(text) -> int`, `latest_texts(db, seat_id) -> dict[str,str]`, `total_lines(db, seat_id) -> int`, `compute_pairs(db, exam_id, min_pct=40) -> list[dict]`, `results(db, exam) -> dict`, `results_csv(data) -> str`
  - Agent → server `snapshot {ts, files:[{path, text, sha}]}`; `POST /api/submit` (form `token`, `auto`, file) → `{"ok": true}`
  - HTTP: `GET /api/teacher/results`, `GET /api/teacher/results.csv`
  - `KIND_TEXT: dict[str,str]` (flag kind → category label)

- [x] **Step 1: Write the failing tests**

`server/tests/test_results.py`:
```python
from sqlmodel import select

from tide_server.burst import burst_lines
from tide_server.exam_service import pair_seat
from tide_server.models import Flag, Seat
from tide_server.similarity import compute_pairs, results, results_csv

A = "\n".join(["int main() {", "  int total = 0;"] + [f"  total += arr[{i}] * weight[{i}];" for i in range(30)] + ["  return total;", "}"])
B = A.replace("total", "sum").replace("weight", "w")


def test_burst_rule():
    assert burst_lines(10, 55) == 45
    assert burst_lines(10, 40) is None
    assert burst_lines(0, 200) == 200


async def test_snapshot_burst_flags_big_jump_only(ctx, paired, hub):
    seat, _ = paired
    await ctx.ingest.handle(seat.id, {"t": "snapshot", "ts": 10, "files": [{"path": "main.c", "text": "x\n" * 5, "sha": "1"}]})
    await ctx.ingest.handle(seat.id, {"t": "snapshot", "ts": 40, "files": [{"path": "main.c", "text": "x\n" * 60, "sha": "2"}]})
    with ctx.db() as db:
        f = db.exec(select(Flag).where(Flag.kind == "code_burst")).one()
    assert f.title == "Code burst · +55 lines" and f.severity == "medium"


def test_submit_saves_zip_and_locks_seat(client, ctx, paired):
    seat, token = paired
    r = client.post("/api/submit", data={"token": token, "auto": "false"},
                    files={"file": ("s.zip", b"PK\x03\x04zip", "application/zip")})
    assert r.json() == {"ok": True}
    with ctx.db() as db:
        assert db.get(Seat, seat.id).state == "submitted"
    assert (ctx.settings.data_dir / "submissions" / "PC07_22BCS107.zip").read_bytes() == b"PK\x03\x04zip"
    assert client.post("/api/submit", data={"token": "bad"}, files={"file": ("s.zip", b"x")}).status_code == 401


async def test_pairs_and_results(ctx, exam):
    with ctx.db() as db:
        s1, _ = pair_seat(db, exam.join_code, "R1", 14, "")
        s2, _ = pair_seat(db, exam.join_code, "R2", 16, "")
        s3, _ = pair_seat(db, exam.join_code, "R3", 20, "")
    await ctx.ingest.handle(s1.id, {"t": "snapshot", "ts": 1, "files": [{"path": "main.c", "text": A, "sha": "a"}]})
    await ctx.ingest.handle(s2.id, {"t": "snapshot", "ts": 1, "files": [{"path": "main.c", "text": B, "sha": "b"}]})
    await ctx.ingest.handle(s3.id, {"t": "snapshot", "ts": 1, "files": [{"path": "main.py", "text": "print('hi')\n", "sha": "c"}]})
    with ctx.db() as db:
        pairs = compute_pairs(db, exam.id)
        data = results(db, exam)
    assert pairs[0]["a"] == 14 and pairs[0]["b"] == 16 and pairs[0]["pct"] >= 80
    rows = {r["seat_no"]: r for r in data["rows"]}
    assert rows[14]["max_match"] >= 80 and rows[20]["max_match"] is None
    csv = results_csv(data)
    assert csv.splitlines()[0] == "seat,roll,set,submitted_at,flags,max_match"
    assert "PC-14,R1" in csv


def test_results_endpoints(teacher, exam):
    assert teacher.get("/api/teacher/results").status_code == 200
    r = teacher.get("/api/teacher/results.csv")
    assert r.headers["content-type"].startswith("text/csv")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_results.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_server.burst'`

- [x] **Step 3: Implement**

`server/tide_server/burst.py`:
```python
def burst_lines(before: int, after: int, threshold: int = 40) -> int | None:
    """Snapshots are ≤30 s apart, so +40 lines in one snapshot is a paste, not typing.
    The agent never sends unchanged starter files, so the first snapshot counts too."""
    delta = after - before
    return delta if delta >= threshold else None
```

Add to `server/tide_server/serialize.py`:
```python
KIND_TEXT = {"blocked_site": "AI / blocked site", "denied_app": "Blocked app", "jev": "Jev flag",
             "heuristic": "Suspicious app", "internet": "Internet detected", "old_code": "Old code reused",
             "file_open": "Pre-exam file", "code_burst": "Code burst", "agent_offline": "Agent offline",
             "usb": "USB drive", "lan_peer": "LAN connection", "clipboard": "Large paste",
             "ai_extension": "AI extension"}
```

`server/tide_server/similarity.py`:
```python
import csv
import io
import json
from collections import Counter
from datetime import datetime
from itertools import combinations

from sqlmodel import Session, select

from tide_common.fingerprint import fingerprints, similarity

from tide_server.models import Exam, Flag, Seat, Snapshot, Submission
from tide_server.serialize import KIND_TEXT


def count_lines(text: str) -> int:
    return len(text.splitlines())


def latest_texts(db: Session, seat_id: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in db.exec(select(Snapshot).where(Snapshot.seat_id == seat_id).order_by(Snapshot.id)).all():
        out[s.path] = s.text
    return out


def total_lines(db: Session, seat_id: int) -> int:
    return sum(count_lines(t) for t in latest_texts(db, seat_id).values())


def compute_pairs(db: Session, exam_id: int, min_pct: int = 40) -> list[dict]:
    seats = db.exec(select(Seat).where(Seat.exam_id == exam_id)).all()
    fps = {}
    for s in seats:
        text = "\n".join(latest_texts(db, s.id).values())
        fp = fingerprints(text)
        if fp:
            fps[s.seat_no] = fp
    pairs = []
    for a, b in combinations(sorted(fps), 2):
        pct = round(similarity(fps[a], fps[b]) * 100)
        if pct >= min_pct:
            pairs.append({"a": a, "b": b, "b_path": None, "pct": pct})
    return sorted(pairs, key=lambda p: -p["pct"])


def results(db: Session, exam: Exam) -> dict:
    seats = db.exec(select(Seat).where(Seat.exam_id == exam.id).order_by(Seat.seat_no)).all()
    by_id = {s.id: s for s in seats}
    flags = [f for f in db.exec(select(Flag)).all() if f.seat_id in by_id and f.status != "dismissed"]
    pairs = compute_pairs(db, exam.id)
    for f in flags:
        if f.kind == "old_code":
            d = json.loads(f.data_json)
            pairs.append({"a": by_id[f.seat_id].seat_no, "b": None, "b_path": d.get("source_path"),
                          "pct": d.get("pct", 0)})
    pairs.sort(key=lambda p: -p["pct"])
    best: dict[int, int] = {}
    for p in pairs:
        for n in (p["a"], p["b"]):
            if n is not None:
                best[n] = max(best.get(n, 0), p["pct"])
    subs = {s.seat_id: s for s in db.exec(select(Submission)).all()}
    rows = []
    for s in seats:
        rows.append({"seat_id": s.id, "seat_no": s.seat_no, "roll": s.roll, "set": s.set_name,
                     "submitted_at": subs[s.id].ts if s.id in subs else None,
                     "flags": [{"kind": f.kind, "severity": f.severity, "title": f.title}
                               for f in flags if f.seat_id == s.id],
                     "max_match": best.get(s.seat_no)})
    counts = Counter(KIND_TEXT.get(f.kind, f.kind) for f in flags)
    return {"rows": rows, "pairs": pairs, "flag_counts": dict(counts.most_common())}


def results_csv(data: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["seat", "roll", "set", "submitted_at", "flags", "max_match"])
    for r in data["rows"]:
        at = datetime.fromtimestamp(r["submitted_at"]).strftime("%H:%M:%S") if r["submitted_at"] else ""
        w.writerow([f"PC-{r['seat_no']:02d}", r["roll"], r["set"] or "", at,
                    "; ".join(f["title"] for f in r["flags"]),
                    "" if r["max_match"] is None else r["max_match"]])
    return buf.getvalue()
```

Add to `class Ingest` (add imports `from tide_server.burst import burst_lines`, `from tide_server.models import Snapshot`, `from tide_server.similarity import count_lines, total_lines`; `Snapshot` is needed for the rows it adds):
```python
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
```

Add to `server/tide_server/api/agent.py` (imports: `from fastapi import File, Form, UploadFile`, `from tide_server.models import Submission`):
```python
@router.post("/api/submit")
async def submit(token: str = Form(...), auto: bool = Form(False), file: UploadFile = File(...),
                 ctx: Ctx = Depends(get_ctx)):
    data = await file.read()
    with ctx.db() as db:
        seat = seat_by_token(db, token)
        if seat is None:
            raise HTTPException(401, "Unknown seat")
        folder = ctx.settings.data_dir / "submissions"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"PC{seat.seat_no:02d}_{seat.roll}.zip"
        (folder / name).write_bytes(data)
        db.add(Submission(seat_id=seat.id, ts=clock.now(), file_name=name, auto=auto))
        seat.state = "submitted"
        db.add(seat)
        db.commit()
        seat_id = seat.id
    await push_event(ctx, add_event(ctx, seat_id, "submitted", {"auto": auto}))
    await push_seat(ctx, seat_id)
    return {"ok": True}
```

Add to `server/tide_server/api/teacher.py` (imports: `from fastapi import Response`, `from tide_server.similarity import results, results_csv`):
```python
@router.get("/results")
def get_results(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        return results(db, _exam(db))


@router.get("/results.csv")
def get_results_csv(ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        body = results_csv(results(db, _exam(db)))
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="tide-results.csv"'})
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add server
git commit -m "feat(server): snapshots, code bursts, submissions, similarity and results export"
```

### Task 11: Console feed, seat detail, flag review, evidence files

**Files:**
- Create: `server/tide_server/api/console.py`
- Modify: `server/tide_server/api/teacher.py` (`require_teacher` also reads `?token=`; add seat detail, flag review, shots, submission download, catalog), `server/tide_server/app.py` (include console router)
- Test: `server/tests/test_console.py`

**Interfaces:**
- Produces:
  - `/ws/console?token=` → first message `hello {exam, seats[], flags[], mode, server_time}`, then pushes `seat`, `flag`, `event`, `exam`
  - `GET /api/teacher/catalog -> {apps: [...], presets: {...}}`
  - `GET /api/teacher/seats/{id} -> {seat, timeline[], growth[{ts,lines}], files[{path,lines}]}`; timeline items are `{"type":"event", ...event_out}` or `{"type":"flag", ...flag_out}`, newest first
  - `PATCH /api/teacher/flags/{id} {status: "dismissed"|"confirmed"}`
  - `GET /api/teacher/shots/{flag_id}` (jpeg), `GET /api/teacher/submissions/{seat_id}` (zip)

- [x] **Step 1: Write the failing tests**

`server/tests/test_console.py`:
```python
import pytest
from starlette.websockets import WebSocketDisconnect


def login(client):
    return client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]


def test_console_ws_requires_token(client, exam):
    with client.websocket_connect("/ws/console?token=bad") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_console_hello_has_room(client, exam, paired):
    with client.websocket_connect(f"/ws/console?token={login(client)}") as ws:
        hello = ws.receive_json()
    assert hello["t"] == "hello" and hello["mode"] == "heuristics"
    assert hello["exam"]["join_code"] == exam.join_code
    assert [s["seat_no"] for s in hello["seats"]] == [7]


async def test_seat_detail_review_and_shot(teacher, ctx, paired):
    seat, _ = paired
    await ctx.ingest.handle(seat.id, {"t": "event", "kind": "window", "data": {"process": "code.exe"}, "ts": 5})
    await ctx.ingest.handle(seat.id, {"t": "flag", "ref": "r", "kind": "usb", "severity": "high",
                                      "title": "USB drive inserted", "data": {}, "ts": 6, "action": "none"})
    await ctx.ingest.handle(seat.id, {"t": "evidence", "ref": "r", "jpeg_b64": "/9j/AA=="})
    await ctx.ingest.handle(seat.id, {"t": "snapshot", "ts": 7, "files": [{"path": "main.c", "text": "a\nb\n", "sha": "1"}]})
    d = teacher.get(f"/api/teacher/seats/{seat.id}").json()
    assert d["seat"]["status"] == "crit"
    assert [i["type"] for i in d["timeline"]][:2] == ["flag", "event"]
    assert d["growth"] == [{"ts": 7, "lines": 2}] and d["files"] == [{"path": "main.c", "lines": 2}]
    flag_id = d["timeline"][0]["id"]
    token = teacher.headers["Authorization"].split()[1]
    assert teacher.get(f"/api/teacher/shots/{flag_id}?token={token}").status_code == 200
    r = teacher.patch(f"/api/teacher/flags/{flag_id}", json={"status": "dismissed"})
    assert r.json()["status"] == "dismissed"
    assert teacher.get(f"/api/teacher/seats/{seat.id}").json()["seat"]["status"] == "wait"


def test_catalog(teacher):
    c = teacher.get("/api/teacher/catalog").json()
    assert "Wireshark" in c["apps"] and "networking" in c["presets"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_console.py -v`
Expected: FAIL (404 on `/ws/console`)

- [x] **Step 3: Implement**

In `server/tide_server/api/teacher.py`, replace `require_teacher` with (add `Query` to the fastapi import):
```python
def require_teacher(authorization: str = Header(""), token: str = Query(""),
                    ctx: Ctx = Depends(get_ctx)) -> Ctx:
    tok = authorization.removeprefix("Bearer ").strip() or token
    if tok not in ctx.teacher_tokens:
        raise HTTPException(401, "Login required")
    return ctx
```
Then append (imports: `from fastapi.responses import FileResponse`, `from tide_common.policy import APP_CATALOG, PRESETS`, `from tide_server.exam_service import open_flags`, `from tide_server.live import push_flag, push_seat`, `from tide_server.models import Event, Flag, Snapshot, Submission`, `from tide_server.serialize import event_out, flag_out, seat_out`, `from tide_server import clock`):
```python
class ReviewIn(BaseModel):
    status: str = Field(pattern="^(dismissed|confirmed|open)$")


@router.get("/catalog")
def catalog(ctx: Ctx = Depends(require_teacher)):
    return {"apps": list(APP_CATALOG), "presets": {k: list(v) for k, v in PRESETS.items()}}


@router.get("/seats/{seat_id}")
def seat_detail(seat_id: int, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        seat = db.get(Seat, seat_id)
        if seat is None:
            raise HTTPException(404, "No seat")
        flags = db.exec(select(Flag).where(Flag.seat_id == seat_id)).all()
        events = db.exec(select(Event).where(Event.seat_id == seat_id)).all()
        timeline = ([{"type": "flag", **flag_out(f, seat.seat_no)} for f in flags] +
                    [{"type": "event", **event_out(e)} for e in events])
        timeline.sort(key=lambda i: (i["ts"], i["type"] == "flag"), reverse=True)
        growth, current = [], {}
        snaps = db.exec(select(Snapshot).where(Snapshot.seat_id == seat_id).order_by(Snapshot.id)).all()
        for s in snaps:
            current[s.path] = s.line_count
            total = sum(current.values())
            if growth and growth[-1]["ts"] == s.ts:
                growth[-1]["lines"] = total
            else:
                growth.append({"ts": s.ts, "lines": total})
        return {"seat": seat_out(seat, open_flags(db, seat_id)), "timeline": timeline,
                "growth": growth, "files": [{"path": p, "lines": n} for p, n in current.items()]}


@router.patch("/flags/{flag_id}")
async def review(flag_id: int, body: ReviewIn, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        flag = db.get(Flag, flag_id)
        if flag is None:
            raise HTTPException(404, "No flag")
        flag.status = body.status
        flag.reviewed_at = clock.now()
        db.add(flag)
        db.commit()
        seat_id = flag.seat_id
        seat_no = db.get(Seat, seat_id).seat_no
        out = flag_out(flag, seat_no)
    await push_flag(ctx, flag_id)
    await push_seat(ctx, seat_id)
    return out


@router.get("/shots/{flag_id}")
def shot(flag_id: int, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        flag = db.get(Flag, flag_id)
    if flag is None or not flag.screenshot:
        raise HTTPException(404, "No screenshot")
    return FileResponse(ctx.settings.data_dir / "shots" / flag.screenshot, media_type="image/jpeg")


@router.get("/submissions/{seat_id}")
def submission_file(seat_id: int, ctx: Ctx = Depends(require_teacher)):
    with ctx.db() as db:
        sub = db.exec(select(Submission).where(Submission.seat_id == seat_id)
                      .order_by(Submission.id.desc())).first()
    if sub is None:
        raise HTTPException(404, "No submission")
    return FileResponse(ctx.settings.data_dir / "submissions" / sub.file_name,
                        media_type="application/zip", filename=sub.file_name)
```

`server/tide_server/api/console.py`:
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import select

from tide_server import clock
from tide_server.ctx import Ctx
from tide_server.exam_service import current_exam, open_flags
from tide_server.models import Flag, Seat
from tide_server.serialize import exam_out, flag_out, seat_out

router = APIRouter()


def console_hello(ctx: Ctx) -> dict:
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None:
            return {"t": "hello", "exam": None, "seats": [], "flags": [], "mode": ctx.pipeline.mode,
                    "server_time": clock.now()}
        seats = db.exec(select(Seat).where(Seat.exam_id == exam.id).order_by(Seat.seat_no)).all()
        seat_no = {s.id: s.seat_no for s in seats}
        flags = db.exec(select(Flag).order_by(Flag.id.desc()).limit(300)).all()
        return {"t": "hello", "exam": exam_out(exam),
                "seats": [seat_out(s, open_flags(db, s.id)) for s in seats],
                "flags": [flag_out(f, seat_no[f.seat_id]) for f in flags if f.seat_id in seat_no],
                "mode": ctx.pipeline.mode, "server_time": clock.now()}


@router.websocket("/ws/console")
async def ws_console(ws: WebSocket, token: str = ""):
    ctx: Ctx = ws.app.state.ctx
    await ws.accept()
    if token not in ctx.teacher_tokens:
        await ws.close(code=4401)
        return
    ctx.hub.add_console(ws)
    try:
        await ws.send_json(console_hello(ctx))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ctx.hub.remove_console(ws)
```

In `server/tide_server/app.py`, change the import to `from tide_server.api import agent, console, teacher` and add `app.include_router(console.router)` after the agent router.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add server
git commit -m "feat(server): console feed, seat detail, flag review, evidence download"
```

### Task 12: LAN discovery, demo mode, CLI, static console

**Files:**
- Create: `server/tide_server/discovery.py`, `server/tide_server/simulate.py`, `server/tide_server/__main__.py`, `server/tide_server/demo_assets/set_A/questions.txt`, `server/tide_server/demo_assets/set_A/main.c`, `server/tide_server/demo_assets/set_B/questions.txt`, `server/tide_server/demo_assets/set_B/main.c`
- Modify: `server/tide_server/app.py` (final version below), `server/tide_server/api/teacher.py` (`POST /api/teacher/simulate`)
- Test: `server/tests/test_demo.py`

**Interfaces:**
- Produces:
  - UDP: client sends `b"TIDE?"` to port 47800 → server replies JSON `{"tide": 1, "port": 8765}`
  - `start_discovery(host, discovery_port, http_port) -> DatagramTransport`
  - `seed_room(db, exam, real_seat_no=7, n=60) -> None`, `SimRoom(ctx, exam_id, rng=None)` with `async tick()`, `run_sim(room, interval=3.0)`, `SCRIPT: list[ScriptItem]`, `bootstrap_demo(ctx) -> int`
  - `POST /api/teacher/simulate {seat_no, kind}` where kind ∈ `ai_site | jev_ai | internet | old_code | usb`
  - CLI `tide-server [--demo] [--port N] [--data DIR] [--no-browser]`

- [x] **Step 1: Write the failing tests**

`server/tests/test_demo.py`:
```python
import asyncio
import json
import socket

from fastapi.testclient import TestClient
from sqlmodel import select

from tide_server import clock
from tide_server.app import create_app
from tide_server.discovery import start_discovery
from tide_server.models import Flag, Seat
from tide_server.simulate import SCRIPT, SimRoom


async def test_discovery_replies():
    transport = await start_discovery("127.0.0.1", 0, 8765)
    port = transport.get_extra_info("sockname")[1]
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.sendto(b"TIDE?", ("127.0.0.1", port))
    data = await asyncio.wait_for(loop.sock_recv(sock, 1024), 2)
    transport.close()
    sock.close()
    assert json.loads(data) == {"tide": 1, "port": 8765}


def test_demo_boot_seeds_room(settings):
    app = create_app(settings.model_copy(update={"demo": True}))
    with TestClient(app):
        ctx = app.state.ctx
        with ctx.db() as db:
            seats = db.exec(select(Seat)).all()
    assert len(seats) == 59 and 7 not in {s.seat_no for s in seats}
    by_no = {s.seat_no: s for s in seats}
    assert by_no[19].state == "blocked" and by_no[58].state == "lobby"


async def test_sim_script_fires_after_start(settings, monkeypatch):
    app = create_app(settings.model_copy(update={"demo": True}))
    with TestClient(app) as client:
        ctx = app.state.ctx
        token = client.post("/api/teacher/login", json={"pin": "2468"}).json()["token"]
        monkeypatch.setattr(clock, "now", lambda: 1000.0)
        client.post("/api/teacher/start", headers={"Authorization": f"Bearer {token}"})
        room = SimRoom(ctx, ctx.extras["exam_id"])
        first = SCRIPT[0]
        monkeypatch.setattr(clock, "now", lambda: 1000.0 + first.at_s + 0.1)
        await room.tick()
        await room.tick()
        with ctx.db() as db:
            flags = db.exec(select(Flag).where(Flag.title == first.title)).all()
        assert len(flags) == 1


def test_simulate_endpoint(teacher, ctx, paired):
    r = teacher.post("/api/teacher/simulate", json={"seat_no": 7, "kind": "jev_ai"})
    assert r.status_code == 200
    with ctx.db() as db:
        f = db.exec(select(Flag)).one()
    assert (f.source, f.label, f.confidence) == ("jev", "ai_assistant", 0.96)
    assert teacher.post("/api/teacher/simulate", json={"seat_no": 7, "kind": "nope"}).status_code == 422
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest server/tests/test_demo.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_server.discovery'`

- [x] **Step 3: Implement**

`server/tide_server/discovery.py`:
```python
"""Answers 'TIDE?' broadcasts so agents find the teacher laptop without typing an IP."""
import asyncio
import json


class DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, http_port: int) -> None:
        self.reply = json.dumps({"tide": 1, "port": http_port}).encode()
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if data.strip() == b"TIDE?" and self.transport:
            self.transport.sendto(self.reply, addr)


async def start_discovery(host: str, discovery_port: int, http_port: int) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: DiscoveryProtocol(http_port), local_addr=(host, discovery_port), allow_broadcast=True)
    return transport
```

`server/tide_server/simulate.py`:
```python
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
        if no == 19:
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


def bootstrap_demo(ctx: Ctx) -> int:
    with ctx.db() as db:
        exam = current_exam(db)
        if exam is None or exam.state == "ended":
            exam = create_exam(db, "CN Lab Test 3", 90 * 60, list(PRESETS["networking"]))
            for set_name in ("A", "B"):
                for f in sorted((ASSETS / f"set_{set_name}").iterdir()):
                    add_file(db, exam.id, set_name, f.name, f.read_bytes())
        if db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.simulated == True)).first() is None:  # noqa: E712
            seed_room(db, exam)
        return exam.id


class SimRoom:
    def __init__(self, ctx: Ctx, exam_id: int, rng: random.Random | None = None) -> None:
        self.ctx, self.exam_id = ctx, exam_id
        self.rng = rng or random.Random(7)
        self.boot_at = clock.now()
        self.fired: set[int] = set()

    async def tick(self) -> None:
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
```

Demo assets (plain text, short):

`server/tide_server/demo_assets/set_A/questions.txt`:
```
CN Lab Test 3 — Set A (odd seats)                                90 minutes

Q1. Read N IPv4 addresses. For each, print its class (A, B, C, D or E)
    and whether it is private.
    Input:  3 / 10.1.2.3 / 172.20.0.1 / 8.8.8.8
    Output: A private / B private / A public

Q2. Open capture_A.txt. Count the ARP requests and print each sender IP.

Write your code in main.c in this folder. Press Submit in the Tide bar when done.
```
`server/tide_server/demo_assets/set_A/main.c`:
```c
#include <stdio.h>

int main(void) {
    /* Q1: your code here */
    return 0;
}
```
`server/tide_server/demo_assets/set_B/questions.txt`:
```
CN Lab Test 3 — Set B (even seats)                               90 minutes

Q1. Read N MAC addresses. For each, print unicast or multicast, and
    whether it is globally or locally administered.
    Input:  2 / 00:1A:2B:3C:4D:5E / 01:00:5E:00:00:FB
    Output: unicast global / multicast global

Q2. Open capture_B.txt. Count the DNS queries and print each domain.

Write your code in main.c in this folder. Press Submit in the Tide bar when done.
```
`server/tide_server/demo_assets/set_B/main.c`: same content as set A's `main.c`.

Add to `server/tide_server/api/teacher.py`:
```python
SIM_EVENTS = {
    "ai_site": dict(kind="blocked_site", severity="critical", title="ChatGPT — closed", source="rule", action="close_tab"),
    "jev_ai": dict(kind="jev", severity="critical", title="poe.com — AI assistant", source="jev",
                   label="ai_assistant", confidence=0.96, action="close_tab"),
    "internet": dict(kind="internet", severity="critical", title="Internet via Wi-Fi", source="rule", action="overlay"),
    "old_code": dict(kind="old_code", severity="high", title="Old code reused · 82%", source="rule",
                     data={"source_path": "D:\\old\\dsa_lab5.cpp", "pct": 82}),
    "usb": dict(kind="usb", severity="high", title="USB drive inserted", source="rule"),
}


class SimIn(BaseModel):
    seat_no: int
    kind: str


@router.post("/simulate")
async def simulate(body: SimIn, ctx: Ctx = Depends(require_teacher)):
    if body.kind not in SIM_EVENTS:
        raise HTTPException(422, f"kind must be one of {sorted(SIM_EVENTS)}")
    with ctx.db() as db:
        exam = _exam(db)
        seat = db.exec(select(Seat).where(Seat.exam_id == exam.id, Seat.seat_no == body.seat_no)).first()
    if seat is None:
        raise HTTPException(404, "No such seat")
    flag = await raise_flag(ctx, seat.id, **SIM_EVENTS[body.kind])
    return {"flag_id": flag.id}
```
(add `from tide_server.live import raise_flag`.)

`server/tide_server/app.py` (final):
```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tide_server import monitor
from tide_server.api import agent, console, teacher
from tide_server.classify.jev import JevClassifier
from tide_server.classify.pipeline import Pipeline
from tide_server.config import Settings
from tide_server.ctx import Ctx
from tide_server.db import make_engine
from tide_server.discovery import start_discovery
from tide_server.hub import Hub
from tide_server.ingest import Ingest
from tide_server.simulate import SimRoom, bootstrap_demo, run_sim


def build_pipeline(settings: Settings) -> Pipeline:
    if not settings.openrouter_api_key:
        return Pipeline(None)
    return Pipeline(JevClassifier(settings.jev_url, settings.openrouter_api_key, settings.jev_model))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = Ctx(settings=settings, engine=make_engine(settings.data_dir), hub=Hub())
    ctx.pipeline = build_pipeline(settings)
    ctx.ingest = Ingest(ctx)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks: list[asyncio.Task] = []
        transport = None
        if settings.demo:
            ctx.extras["exam_id"] = bootstrap_demo(ctx)
        if settings.background_tasks:
            tasks.append(asyncio.create_task(monitor.run(ctx)))
            if settings.demo:
                tasks.append(asyncio.create_task(run_sim(SimRoom(ctx, ctx.extras["exam_id"]))))
            try:
                transport = await start_discovery(settings.host, settings.discovery_port, settings.port)
            except OSError as e:
                print(f"[discovery] disabled: {e}")
        yield
        for t in tasks:
            t.cancel()
        if transport:
            transport.close()

    app = FastAPI(title="Tide", lifespan=lifespan)
    app.state.ctx = ctx
    app.include_router(teacher.router)
    app.include_router(agent.router)
    app.include_router(console.router)
    if settings.console_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.console_dir, html=True), name="console")
    return app
```

`server/tide_server/__main__.py`:
```python
import argparse
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from tide_server.app import create_app
from tide_server.config import Settings


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="tide-server", description="Tide teacher server + console")
    ap.add_argument("--demo", action="store_true", help="seed a demo exam and 59 simulated seats")
    ap.add_argument("--port", type=int)
    ap.add_argument("--data", type=Path, help="data folder (default ./tide-data)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    overrides = {k: v for k, v in {"demo": args.demo or None, "port": args.port,
                                   "data_dir": args.data}.items() if v is not None}
    settings = Settings(**overrides)
    app = create_app(settings)
    mode = "Jev via OpenRouter" if settings.openrouter_api_key else "offline heuristics (no OPENROUTER_API_KEY)"
    print(f"\n  Tide console  http://{lan_ip()}:{settings.port}   PIN {settings.teacher_pin}"
          f"\n  Classifier    {mode}\n  Demo mode     {'on' if settings.demo else 'off'}\n", flush=True)
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [f"http://localhost:{settings.port}"]).start()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest server/tests -v`
Expected: all pass

- [x] **Step 5: Smoke-run the server**

Run: `tide-server --demo --no-browser --data /tmp/tide-smoke` and in another shell `curl -s localhost:8765/api/teacher/login -H 'content-type: application/json' -d '{"pin":"2468"}'`
Expected: the banner prints; curl returns `{"token": "..."}`. Stop with Ctrl+C.

- [x] **Step 6: Commit**

```bash
git add server
git commit -m "feat(server): LAN discovery, demo mode with 59 simulated seats, CLI"
```

---
## Phase 3 — Student agent (`agent/`)

The agent's logic runs and is tested on any OS. Only `tide_agent/win/` needs Windows. `tide_agent/fake.py` is a simulated PC you drive by typing commands, used for single-device end-to-end testing on a Mac or Linux laptop.

### Task 13: Agent foundation — platform types, server clock, outbox, link

**Files:**
- Create: `agent/pyproject.toml`, `agent/tide_agent/__init__.py`, `agent/tide_agent/platform.py`, `agent/tide_agent/clock.py`, `agent/tide_agent/outbox.py`, `agent/tide_agent/link.py`
- Test: `agent/tests/test_link.py`

**Interfaces:**
- Produces:
  - `WindowInfo(hwnd, pid, process, exe, title, description="", original_name="")`, `ProcInfo(pid, name, exe="", description="", original_name="")`, `AdapterInfo(name, up, wifi=False, ssid=None)`, `Peer(ip, port, process="")` (frozen dataclasses)
  - `Platform` protocol: `foreground() -> WindowInfo | None`, `browser_host(hwnd, process) -> str | None` (`""` = empty/local page, `None` = unreadable), `processes() -> dict[int, ProcInfo]`, `kill(pid)`, `adapters() -> dict[str, AdapterInfo]`, `internet() -> bool`, `lan_peers(server_ip) -> list[Peer]`, `removable_drives() -> set[str]`, `clipboard_seq() -> int`, `clipboard_text() -> str | None`, `close_tab(hwnd)`, `screenshot() -> bytes | None`
  - `compute_offset(sent, server_time, received) -> float`; `ServerClock(offset=0.0)` with `now()`, `to_local(server_ts)`
  - `Outbox(path)` with `append(msg)`, `drain() -> list[dict]`
  - `Link(url, token, on_message, outbox, version="0.1.0")` with `async run()`, `async send(msg) -> bool`, `connected: asyncio.Event`, `offset: float`. `on_message` receives `welcome` with `_offset` added. On close code 4401 it calls `on_message({"t": "auth_failed"})` and stops.

- [x] **Step 1: Package metadata**

`agent/pyproject.toml`:
```toml
[project]
name = "tide-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "tide-common", "websockets>=13", "httpx>=0.27", "psutil>=6", "pywebview>=5.3", "Pillow>=10",
  "pywin32>=306; sys_platform == 'win32'",
  "uiautomation>=2.0.20; sys_platform == 'win32'",
  "mss>=9; sys_platform == 'win32'",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "pyinstaller>=6.10; sys_platform == 'win32'"]

[project.scripts]
tide-agent = "tide_agent.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["tide_agent"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```
`agent/tide_agent/__init__.py`: `__version__ = "0.1.0"`

- [x] **Step 2: Write the failing tests**

`agent/tests/test_link.py`:
```python
import asyncio
import json

import websockets

from tide_agent.clock import ServerClock, compute_offset
from tide_agent.link import Link
from tide_agent.outbox import Outbox


def test_compute_offset_uses_midpoint():
    assert compute_offset(sent=100.0, server_time=160.5, received=101.0) == 60.0


def test_server_clock_conversion():
    c = ServerClock(offset=60.0)
    assert c.to_local(1060.0) == 1000.0


def test_outbox_roundtrip(tmp_path):
    ob = Outbox(tmp_path / "o.jsonl")
    ob.append({"t": "flag", "n": 1})
    ob.append({"t": "flag", "n": 2})
    assert [m["n"] for m in ob.drain()] == [1, 2]
    assert ob.drain() == []


async def test_link_buffers_offline_then_flushes(tmp_path):
    """Review focus #4: flags raised while the server is unreachable arrive later; heartbeats don't."""
    received: list[dict] = []

    async def handler(ws):
        hello = json.loads(await ws.recv())
        assert hello["t"] == "hello" and hello["token"] == "tok"
        await ws.send(json.dumps({"t": "welcome", "server_time": 0.0, "policy": {}}))
        async for raw in ws:
            received.append(json.loads(raw))

    got: list[dict] = []

    async def on_message(m):
        got.append(m)

    link = Link("ws://127.0.0.1:1/ws/agent", "tok", on_message, Outbox(tmp_path / "o.jsonl"))
    assert await link.send({"t": "flag", "ref": "a"}) is False
    assert await link.send({"t": "heartbeat"}) is False

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        link.url = f"ws://127.0.0.1:{port}/ws/agent"
        task = asyncio.create_task(link.run())
        await asyncio.wait_for(link.connected.wait(), 5)
        assert await link.send({"t": "event", "n": 1}) is True
        await asyncio.sleep(0.2)
        task.cancel()
    assert got[0]["t"] == "welcome" and "_offset" in got[0]
    assert [m["t"] for m in received] == ["flag", "event"]


async def test_link_stops_on_4401(tmp_path):
    async def handler(ws):
        await ws.recv()
        await ws.close(code=4401)

    got: list[dict] = []

    async def on_message(m):
        got.append(m)

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        link = Link(f"ws://127.0.0.1:{port}/ws/agent", "bad", on_message, Outbox(tmp_path / "o.jsonl"))
        await asyncio.wait_for(link.run(), 5)
    assert got == [{"t": "auth_failed"}]
```

- [x] **Step 3: Run tests to verify they fail**

Run: `pytest agent/tests/test_link.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_agent.clock'`

- [x] **Step 4: Implement**

`agent/tide_agent/platform.py`:
```python
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
```

`agent/tide_agent/clock.py`:
```python
import time
from dataclasses import dataclass


def compute_offset(sent: float, server_time: float, received: float) -> float:
    """server_now - local_now, assuming the server stamped its reply halfway through the round trip."""
    return server_time - (sent + received) / 2


@dataclass
class ServerClock:
    offset: float = 0.0

    def now(self) -> float:
        return time.time() + self.offset

    def to_local(self, server_ts: float) -> float:
        return server_ts - self.offset
```

`agent/tide_agent/outbox.py`:
```python
import json
import threading
from pathlib import Path


class Outbox:
    """Messages that couldn't be sent. On disk, so they survive an agent restart."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, message: dict) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(message) + "\n")

    def drain(self) -> list[dict]:
        with self._lock:
            if not self.path.exists():
                return []
            lines = self.path.read_text(encoding="utf-8").splitlines()
            self.path.unlink()
        return [json.loads(line) for line in lines if line.strip()]
```

`agent/tide_agent/link.py`:
```python
import asyncio
import json
import time
from typing import Awaitable, Callable

import websockets

from tide_common.protocol import msg

from .clock import compute_offset
from .outbox import Outbox

NOT_BUFFERED = {"heartbeat"}


class Link:
    """One WebSocket to the teacher server, reconnecting forever. Sends while offline go to the outbox."""

    def __init__(self, url: str, token: str, on_message: Callable[[dict], Awaitable[None]],
                 outbox: Outbox, version: str = "0.1.0") -> None:
        self.url, self.token, self.on_message, self.outbox, self.version = url, token, on_message, outbox, version
        self.ws = None
        self.connected = asyncio.Event()
        self.offset = 0.0

    async def run(self) -> None:
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(self.url, open_timeout=5, ping_interval=10) as ws:
                    sent = time.time()
                    await ws.send(json.dumps(msg("hello", token=self.token, agent_version=self.version,
                                                 local_time=sent)))
                    welcome = json.loads(await ws.recv())
                    if welcome.get("t") != "welcome":
                        raise ConnectionError("expected welcome")
                    self.offset = compute_offset(sent, welcome["server_time"], time.time())
                    welcome["_offset"] = self.offset
                    self.ws = ws
                    backoff = 1.0
                    await self.on_message(welcome)
                    for pending in self.outbox.drain():
                        await ws.send(json.dumps(pending))
                    self.connected.set()
                    async for raw in ws:
                        await self.on_message(json.loads(raw))
            except websockets.ConnectionClosed as e:
                if e.rcvd is not None and e.rcvd.code == 4401:
                    self.ws = None
                    self.connected.clear()
                    await self.on_message({"t": "auth_failed"})
                    return
            except (OSError, asyncio.TimeoutError, ConnectionError, websockets.WebSocketException):
                pass
            finally:
                self.ws = None
                self.connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5.0)

    async def send(self, message: dict) -> bool:
        ws = self.ws
        if ws is not None:
            try:
                await ws.send(json.dumps(message))
                return True
            except Exception:
                pass
        if message.get("t") not in NOT_BUFFERED:
            self.outbox.append(message)
        return False
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest agent/tests/test_link.py -v`
Expected: 6 passed

- [x] **Step 6: Commit**

```bash
git add agent
git commit -m "feat(agent): platform interface, server clock, outbox, reconnecting link"
```

### Task 14: Server discovery and pairing client

**Files:**
- Create: `agent/tide_agent/discovery.py`, `agent/tide_agent/pairing.py`
- Test: `agent/tests/test_pairing.py`

**Interfaces:**
- Produces:
  - `discover(timeout=2.0, port=47800, targets=("255.255.255.255",)) -> tuple[str, int] | None`, `parse_server(text, default_port=8765) -> tuple[str, int]`
  - `PairResult(token, seat_id, seat_no, roll, exam_title, server_time)`, `PairError(message)`
  - `async pair(base_url, join_code, roll, seat_no, hostname, client=None) -> PairResult`
  - `async submit(base_url, token, zip_bytes, auto, client=None) -> None` (raises `PairError` on failure)

- [x] **Step 1: Write the failing tests**

`agent/tests/test_pairing.py`:
```python
import json
import socket
import threading

import httpx
import pytest

from tide_agent.discovery import discover, parse_server
from tide_agent.pairing import PairError, pair, submit


def test_parse_server():
    assert parse_server("10.10.0.1") == ("10.10.0.1", 8765)
    assert parse_server("10.10.0.1:9000") == ("10.10.0.1", 9000)


def test_discover_finds_responder():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def respond():
        data, addr = sock.recvfrom(64)
        if data == b"TIDE?":
            sock.sendto(json.dumps({"tide": 1, "port": 8765}).encode(), addr)

    threading.Thread(target=respond, daemon=True).start()
    assert discover(timeout=2, port=port, targets=("127.0.0.1",)) == ("127.0.0.1", 8765)
    sock.close()


def test_discover_times_out():
    assert discover(timeout=0.2, port=9, targets=("127.0.0.1",)) is None


async def test_pair_ok_and_error():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        if body["join_code"] == "BAD":
            return httpx.Response(404, json={"detail": "Unknown join code"})
        return httpx.Response(200, json={"token": "t", "seat_id": 1, "seat_no": 7, "roll": "R",
                                         "exam_title": "CN", "server_time": 1.0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    r = await pair("http://s:8765", "K7Q2XM", "r", 7, "PC", client=client)
    assert (r.token, r.seat_no) == ("t", 7)
    with pytest.raises(PairError, match="Unknown join code"):
        await pair("http://s:8765", "BAD", "r", 7, "PC", client=client)


async def test_submit_posts_zip():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    await submit("http://s:8765", "t", b"PKzip", False,
                 client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert b"PKzip" in seen["body"] and b'name="token"' in seen["body"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest agent/tests/test_pairing.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [x] **Step 3: Implement**

`agent/tide_agent/discovery.py`:
```python
import json
import socket


def parse_server(text: str, default_port: int = 8765) -> tuple[str, int]:
    host, _, port = text.strip().partition(":")
    return host, int(port) if port else default_port


def discover(timeout: float = 2.0, port: int = 47800,
             targets: tuple[str, ...] = ("255.255.255.255",)) -> tuple[str, int] | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        for target in targets:
            s.sendto(b"TIDE?", (target, port))
        data, addr = s.recvfrom(1024)
        return addr[0], int(json.loads(data)["port"])
    except (OSError, ValueError, KeyError):
        return None
    finally:
        s.close()
```

`agent/tide_agent/pairing.py`:
```python
from dataclasses import dataclass

import httpx


class PairError(Exception):
    pass


@dataclass(frozen=True)
class PairResult:
    token: str
    seat_id: int
    seat_no: int
    roll: str
    exam_title: str
    server_time: float


def _detail(r: httpx.Response) -> str:
    try:
        return str(r.json().get("detail") or r.text)
    except ValueError:
        return r.text or f"HTTP {r.status_code}"


async def pair(base_url: str, join_code: str, roll: str, seat_no: int, hostname: str,
               client: httpx.AsyncClient | None = None) -> PairResult:
    client = client or httpx.AsyncClient(timeout=8)
    try:
        r = await client.post(f"{base_url}/api/pair", json={"join_code": join_code, "roll": roll,
                                                               "seat_no": seat_no, "hostname": hostname})
    except httpx.HTTPError as e:
        raise PairError(f"Can't reach the teacher ({e.__class__.__name__})") from e
    if r.status_code != 200:
        raise PairError(_detail(r))
    b = r.json()
    return PairResult(b["token"], b["seat_id"], b["seat_no"], b["roll"], b["exam_title"], b["server_time"])


async def submit(base_url: str, token: str, zip_bytes: bytes, auto: bool,
                 client: httpx.AsyncClient | None = None) -> None:
    client = client or httpx.AsyncClient(timeout=30)
    try:
        r = await client.post(f"{base_url}/api/submit", data={"token": token, "auto": str(auto).lower()},
                              files={"file": ("submission.zip", zip_bytes, "application/zip")})
    except httpx.HTTPError as e:
        raise PairError(f"Submit failed ({e.__class__.__name__})") from e
    if r.status_code != 200:
        raise PairError(_detail(r))
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest agent/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add agent
git commit -m "feat(agent): LAN discovery and pairing/submit client"
```

### Task 15: Pre-exam file inventory and the exam folder

**Files:**
- Create: `agent/tide_agent/inventory.py`, `agent/tide_agent/exam_folder.py`
- Test: `agent/tests/test_files.py`

**Interfaces:**
- Consumes: `fingerprints`, `similarity`
- Produces:
  - `TEXT_EXTS`, `InvFile(path, name, fp)`, `Inventory(files)` with `.match_title(title) -> str | None`, `.best_match(text, min_pct=60) -> tuple[str, int] | None`
  - `build_inventory(roots, exclude=None, max_files=5000, max_bytes=200_000) -> Inventory`, `default_roots() -> list[Path]`
  - `ExamFolder(root)` with `write_files(files: list[tuple[str, bytes]]) -> int` (never overwrites; records starter shas), `texts() -> dict[str,str]`, `changed_files() -> list[{path,text,sha}]` (skips unchanged starter files), `file_count()`, `zip_bytes() -> bytes`

- [x] **Step 1: Write the failing tests**

`agent/tests/test_files.py`:
```python
import io
import zipfile

from tide_agent.exam_folder import ExamFolder
from tide_agent.inventory import build_inventory

OLD = "\n".join(["#include <stdio.h>", "int main() {", "  int a[100], n, best = 0;", '  scanf("%d", &n);',
                 "  for (int i = 0; i < n; i++) {", '    scanf("%d", &a[i]);', "    if (a[i] > best) best = a[i];",
                 "  }", '  printf("%d\\n", best);', "  return 0;", "}"])


def make_tree(tmp_path):
    old = tmp_path / "D" / "old"
    old.mkdir(parents=True)
    (old / "dsa_lab5.cpp").write_text(OLD)
    (old / "notes.pdf").write_bytes(b"%PDF")
    skipped = tmp_path / "D" / "node_modules"
    skipped.mkdir()
    (skipped / "x.js").write_text("ignored")
    exam = tmp_path / "Exam" / "22BCS107"
    exam.mkdir(parents=True)
    (exam / "main.c").write_text("int main(){}")
    return tmp_path / "D", tmp_path / "Exam"


def test_inventory_indexes_and_skips(tmp_path):
    root, exam = make_tree(tmp_path)
    inv = build_inventory([root, exam], exclude=exam)
    names = sorted(f.name for f in inv.files)
    assert names == ["dsa_lab5.cpp", "notes.pdf"]


def test_match_title_finds_old_file(tmp_path):
    root, exam = make_tree(tmp_path)
    inv = build_inventory([root], exclude=exam)
    assert inv.match_title("dsa_lab5.cpp - old - Visual Studio Code").endswith("dsa_lab5.cpp")
    assert inv.match_title("main.c - 22BCS107 - Visual Studio Code") is None


def test_best_match_survives_renaming(tmp_path):
    root, exam = make_tree(tmp_path)
    inv = build_inventory([root], exclude=exam)
    path, pct = inv.best_match(OLD.replace("best", "mx").replace("a[", "arr["))
    assert path.endswith("dsa_lab5.cpp") and pct >= 80
    assert inv.best_match("print('hello world')\n" * 3) is None


def test_exam_folder_never_overwrites_and_skips_starters(tmp_path):
    """Review focus #1: re-delivery after an agent restart must not wipe the student's work."""
    f = ExamFolder(tmp_path / "Exam" / "22BCS107")
    assert f.write_files([("questions.txt", b"Q1"), ("../evil.c", b"x")]) == 2
    assert (f.root / "evil.c").exists() and not (tmp_path / "Exam" / "evil.c").exists()
    assert f.changed_files() == []                      # starters unchanged -> nothing to send
    (f.root / "evil.c").write_text("int main(){ return 1; }")
    assert f.write_files([("evil.c", b"x")]) == 0      # re-delivery keeps the edit
    changed = f.changed_files()
    assert [c["path"] for c in changed] == ["evil.c"] and "return 1" in changed[0]["text"]
    assert f.changed_files() == []                      # nothing new since last call
    names = zipfile.ZipFile(io.BytesIO(f.zip_bytes())).namelist()
    assert sorted(names) == ["evil.c", "questions.txt"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest agent/tests/test_files.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [x] **Step 3: Implement**

`agent/tide_agent/inventory.py`:
```python
"""What code/doc files existed before the exam. Used to spot old solutions being opened or pasted."""
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tide_common.fingerprint import fingerprints, similarity

TEXT_EXTS = {".c", ".cpp", ".cc", ".h", ".hpp", ".py", ".java", ".js", ".ts", ".sql", ".txt", ".md",
             ".ipynb", ".cs", ".go", ".rs", ".sh"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".pptx"}
SKIP_DIRS = {"appdata", "node_modules", ".git", "windows", "program files", "program files (x86)",
             "$recycle.bin", "programdata", "system volume information", ".vscode", ".cache",
             "__pycache__", "site-packages", "venv", ".venv", "library"}
_FILENAME = re.compile(r"([\w\-.]+\.[A-Za-z0-9]{1,5})\b")


@dataclass(frozen=True)
class InvFile:
    path: str
    name: str
    fp: frozenset[int] = field(default=frozenset(), compare=False)


@dataclass
class Inventory:
    files: list[InvFile]

    def __post_init__(self) -> None:
        self._by_name: dict[str, list[str]] = {}
        for f in self.files:
            self._by_name.setdefault(f.name.lower(), []).append(f.path)

    def match_title(self, title: str) -> str | None:
        for token in _FILENAME.findall(title):
            paths = self._by_name.get(token.lower())
            if paths:
                return paths[0]
        return None

    def best_match(self, text: str, min_pct: int = 60) -> tuple[str, int] | None:
        fp = fingerprints(text)
        if not fp:
            return None
        best: tuple[str, int] | None = None
        for f in self.files:
            if f.fp:
                pct = round(similarity(fp, f.fp) * 100)
                if pct >= min_pct and (best is None or pct > best[1]):
                    best = (f.path, pct)
        return best


def build_inventory(roots: list[Path], exclude: Path | None = None, max_files: int = 5000,
                    max_bytes: int = 200_000) -> Inventory:
    files: list[InvFile] = []
    excluded = exclude.resolve() if exclude else None
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath).resolve()
            if excluded and (here == excluded or excluded in here.parents):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                ext = Path(name).suffix.lower()
                if ext not in TEXT_EXTS and ext not in DOC_EXTS:
                    continue
                path = Path(dirpath) / name
                fp: frozenset[int] = frozenset()
                if ext in TEXT_EXTS:
                    try:
                        if path.stat().st_size <= max_bytes:
                            fp = fingerprints(path.read_text(encoding="utf-8", errors="ignore"))
                    except OSError:
                        pass
                files.append(InvFile(str(path), name, fp))
                if len(files) >= max_files:
                    return Inventory(files)
    return Inventory(files)


def default_roots() -> list[Path]:
    home = Path.home()
    roots = [home / d for d in ("Desktop", "Documents", "Downloads", "OneDrive")]
    if sys.platform == "win32":
        import psutil
        for part in psutil.disk_partitions(all=False):
            mount = Path(part.mountpoint)
            if mount.drive.upper() != "C:":
                roots.append(mount)
    return roots
```

`agent/tide_agent/exam_folder.py`:
```python
import hashlib
import io
import zipfile
from pathlib import Path

from .inventory import TEXT_EXTS


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


class ExamFolder:
    """C:\\Exam\\<roll>. Questions arrive here; snapshots and the submission come from here."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._sent: dict[str, str] = {}

    def write_files(self, files: list[tuple[str, bytes]]) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        written = 0
        for name, data in files:
            target = self.root / Path(name).name
            self._sent.setdefault(target.name, _sha(data))
            if target.exists():
                continue
            target.write_bytes(data)
            written += 1
        return written

    def _text_files(self) -> list[Path]:
        if not self.root.exists():
            return []
        return [p for p in sorted(self.root.rglob("*"))
                if p.is_file() and p.suffix.lower() in TEXT_EXTS and p.stat().st_size <= 1_000_000]

    def texts(self) -> dict[str, str]:
        return {p.relative_to(self.root).as_posix(): p.read_text(encoding="utf-8", errors="ignore")
                for p in self._text_files()}

    def changed_files(self) -> list[dict]:
        out = []
        for p in self._text_files():
            rel = p.relative_to(self.root).as_posix()
            data = p.read_bytes()
            sha = _sha(data)
            if self._sent.get(rel) != sha:
                self._sent[rel] = sha
                out.append({"path": rel, "text": data.decode("utf-8", errors="ignore"), "sha": sha})
        return out

    def file_count(self) -> int:
        return sum(1 for p in self.root.rglob("*") if p.is_file()) if self.root.exists() else 0

    def zip_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            if self.root.exists():
                for p in sorted(self.root.rglob("*")):
                    if p.is_file():
                        z.write(p, p.relative_to(self.root).as_posix())
        return buf.getvalue()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest agent/tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add agent
git commit -m "feat(agent): pre-exam file inventory and exam folder"
```

### Task 16: Watchers and pre-flight

**Files:**
- Create: `agent/tide_agent/watchers.py`, `agent/tide_agent/preflight.py`, `agent/tests/fakes.py`
- Test: `agent/tests/test_watchers.py`

**Interfaces:**
- Consumes: `Platform` types, `Signal`, `Kind`, `BROWSERS`, `AI_EXTENSIONS`, `DENY_PROCESSES`, `CLIPBOARD_MIN`, `Inventory`
- Produces:
  - `WindowWatcher(p)` (`.poll() -> list[Signal]`, `.current_process: str`); re-reads the browser host only when the window or title changes
  - `ProcessWatcher(p)`, `NetworkWatcher(p, probe_every_s=5.0, clock=time.monotonic)`, `LanWatcher(p, server_ip)`, `UsbWatcher(p)`, `ClipboardWatcher(p, exam_texts: Callable[[], dict], inventory: Callable[[], Inventory | None])`, `ExtensionWatcher(ext_dir)` with `.set_baseline(names)`
  - `scan_extensions(ext_dir) -> list[str]`
  - `PreflightResult(internet, extensions, denied_closed, inventory)`, `run_preflight(p, ext_dir, roots, exam_root, inventory=None) -> PreflightResult`, `preflight_message(r) -> dict`, `preflight_checks(r) -> list[dict]` (`{id, label, detail, state: ok|warn|fail}`), `running_checks() -> list[dict]`
  - `tests/fakes.py: FakePlatform` with plain attributes: `window, hosts, procs, killed, ads, online, peers, drives, clip_seq, clip, closed_tabs, shot`

- [x] **Step 1: Write the fake and the failing tests**

`agent/tests/fakes.py`:
```python
from tide_agent.platform import AdapterInfo, ProcInfo, WindowInfo


class FakePlatform:
    def __init__(self):
        self.window: WindowInfo | None = WindowInfo(1, 10, "Code.exe", "C:/code.exe", "main.c - 22BCS107 - Visual Studio Code")
        self.hosts: dict[int, str | None] = {}
        self.host_reads = 0
        self.procs: dict[int, ProcInfo] = {10: ProcInfo(10, "Code.exe")}
        self.killed: list[int] = []
        self.ads = {"Ethernet": AdapterInfo("Ethernet", True), "Wi-Fi": AdapterInfo("Wi-Fi", False, wifi=True)}
        self.online = False
        self.peers = []
        self.drives: set[str] = set()
        self.clip_seq = 1
        self.clip: str | None = None
        self.closed_tabs: list[int] = []
        self.shot: bytes | None = b"\xff\xd8jpeg"

    def foreground(self): return self.window
    def browser_host(self, hwnd, process):
        self.host_reads += 1
        return self.hosts.get(hwnd)
    def processes(self): return dict(self.procs)
    def kill(self, pid):
        self.killed.append(pid)
        self.procs.pop(pid, None)
    def adapters(self): return dict(self.ads)
    def internet(self): return self.online
    def lan_peers(self, server_ip): return [p for p in self.peers if p.ip != server_ip]
    def removable_drives(self): return set(self.drives)
    def clipboard_seq(self): return self.clip_seq
    def clipboard_text(self): return self.clip
    def close_tab(self, hwnd): self.closed_tabs.append(hwnd)
    def screenshot(self): return self.shot
```

`agent/tests/test_watchers.py`:
```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest agent/tests/test_watchers.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_agent.watchers'`

- [x] **Step 3: Implement**

`agent/tide_agent/watchers.py`:
```python
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
```

`agent/tide_agent/preflight.py`:
```python
from dataclasses import dataclass
from pathlib import Path

from tide_common.policy import DENY_PROCESSES
from tide_common.protocol import msg

from .inventory import Inventory, build_inventory
from .platform import Platform
from .watchers import scan_extensions


@dataclass
class PreflightResult:
    internet: bool
    extensions: list[str]
    denied_closed: list[str]
    inventory: Inventory


def run_preflight(p: Platform, ext_dir: Path, roots: list[Path], exam_root: Path,
                  inventory: Inventory | None = None) -> PreflightResult:
    closed = []
    for pid, pi in p.processes().items():
        name = DENY_PROCESSES.get(pi.name.lower()) or DENY_PROCESSES.get(pi.original_name.lower())
        if name:
            p.kill(pid)
            closed.append(name)
    return PreflightResult(internet=p.internet(), extensions=scan_extensions(ext_dir),
                           denied_closed=sorted(set(closed)),
                           inventory=inventory or build_inventory(roots, exclude=exam_root))


def preflight_message(r: PreflightResult) -> dict:
    return msg("preflight", internet=r.internet, extensions=r.extensions, denied_closed=r.denied_closed,
               inventory_count=len(r.inventory.files))


def running_checks() -> list[dict]:
    return [{"id": i, "label": label, "detail": "", "state": "run"} for i, label in
            (("internet", "Offline"), ("apps", "Apps"), ("extensions", "AI extensions"), ("files", "Files"))]


def preflight_checks(r: PreflightResult) -> list[dict]:
    return [
        {"id": "internet", "label": "Internet on" if r.internet else "Offline",
         "detail": "Disconnect Wi-Fi / hotspot to continue" if r.internet else "No internet on any adapter",
         "state": "fail" if r.internet else "ok"},
        {"id": "apps", "label": "Apps",
         "detail": f"Closed {', '.join(r.denied_closed)}" if r.denied_closed else "Nothing blocked running",
         "state": "ok"},
        {"id": "extensions", "label": f"{', '.join(r.extensions)} found" if r.extensions else "AI extensions",
         "detail": "Teacher has been told" if r.extensions else "None installed",
         "state": "warn" if r.extensions else "ok"},
        {"id": "files", "label": "Files indexed", "detail": f"{len(r.inventory.files)} files", "state": "ok"},
    ]
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd agent && pytest tests -v && cd ..` (tests import `fakes` from the tests folder, so run from `agent/`)
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add agent
git commit -m "feat(agent): watchers and pre-flight"
```

### Task 17: Enforcer and engine

**Files:**
- Create: `agent/tide_agent/ui/__init__.py`, `agent/tide_agent/ui/port.py`, `agent/tide_agent/enforcer.py`, `agent/tide_agent/engine.py`
- Test: `agent/tests/test_engine.py`

**Interfaces:**
- Consumes: `evaluate`, `Policy`, watchers, `ExamFolder`, `Inventory`, `ServerClock`
- Produces:
  - `UiPort` protocol: `show_join(server: str | None, error: str | None = None)`, `show_preflight(checks)`, `start(seat_no, set_name, ends_at_local, folder)`, `set_ends_at(ends_at_local)`, `notice(text)`, `block(title, persistent=False)`, `unblock()`, `done(n_files, at)`, `error(text)`, `quit()`
  - `Enforcer(p, ui, sleep=time.sleep)` with `act(action, target, title, persistent=False) -> str` returning `none|killed|closed|killed_browser|shown`
  - `Engine(p, ui, send, folder, submitter, ext_dir, server_ip, clock=None)` with `on_signal(sig)`, `on_server(m)`, `tick(n)`, `run()`, `submit(auto)`, `snapshot()`; attributes `policy, inventory, live, done, seat_no, roll`

- [x] **Step 1: Write the failing tests**

`agent/tests/test_engine.py`:
```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd agent && pytest tests/test_engine.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_agent.engine'`

- [x] **Step 3: Implement**

`agent/tide_agent/ui/__init__.py`: empty.

`agent/tide_agent/ui/port.py`:
```python
from typing import Protocol


class UiPort(Protocol):
    """What the engine asks the screen to do. Implementations must be callable from any thread."""
    def show_join(self, server: str | None, error: str | None = None) -> None: ...
    def show_preflight(self, checks: list[dict]) -> None: ...
    def start(self, seat_no: int, set_name: str, ends_at_local: float, folder: str) -> None: ...
    def set_ends_at(self, ends_at_local: float) -> None: ...
    def notice(self, text: str) -> None: ...
    def block(self, title: str, persistent: bool = False) -> None: ...
    def unblock(self) -> None: ...
    def done(self, n_files: int, at: str) -> None: ...
    def error(self, text: str) -> None: ...
    def quit(self) -> None: ...
```

`agent/tide_agent/enforcer.py`:
```python
import time
from typing import Callable

from .platform import Platform
from .ui.port import UiPort


class Enforcer:
    def __init__(self, p: Platform, ui: UiPort, sleep: Callable[[float], None] = time.sleep) -> None:
        self.p, self.ui, self.sleep = p, ui, sleep

    def act(self, action: str, target: dict, title: str, persistent: bool = False) -> str:
        result = "none"
        if action == "kill" and target.get("pid"):
            self.p.kill(target["pid"])
            result = "killed"
        elif action == "close_tab" and target.get("hwnd"):
            self.p.close_tab(target["hwnd"])
            self.sleep(0.3)
            still = self.p.browser_host(target["hwnd"], target.get("process") or "")
            if still and still == target.get("host") and target.get("pid"):
                self.p.kill(target["pid"])
                result = "killed_browser"
            else:
                result = "closed"
        elif action == "overlay":
            result = "shown"
        if action != "none":
            self.ui.block(title, persistent)
        return result
```

`agent/tide_agent/engine.py`:
```python
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd agent && pytest tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add agent
git commit -m "feat(agent): engine routes rules, enforces locally, handles server messages"
```

### Task 18: Agent UI — headless and pywebview windows

**Files:**
- Create: `agent/tide_agent/ui/headless.py`, `agent/tide_agent/ui/webview_ui.py`, `agent/tide_agent/ui/web/style.css`, `agent/tide_agent/ui/web/index.html`, `agent/tide_agent/ui/web/pill.html`, `agent/tide_agent/ui/web/overlay.html`
- Test: `agent/tests/test_ui.py`

**Interfaces:**
- Consumes: `UiPort`
- Produces:
  - `HeadlessUI(out=print)`: implements `UiPort` by printing one line per call (used by `--headless` and tests)
  - `WebviewUI()`: implements `UiPort` with three windows (main 440×600, pill 460×60 top-centre always-on-top, overlay full-screen always-on-top hidden). `.bind(api)` exposes `join(code, roll, seat) -> {ok, error?}` and `submit() -> {ok}` to JS; `.run(func)` calls `webview.start(func)`.
  - JS globals in the pages: `tide.showJoin(server, error)`, `tide.showPreflight(checks)`, `tide.done(n, at)`, `tide.error(text)` (index); `tide.start(seat, set, endsAtMs)`, `tide.setEnds(endsAtMs)`, `tide.notice(text)` (pill); `tide.block(title, persistent)` (overlay)

Visuals follow `design/mock-ui.html` (student screens): the same tokens, `.agent` card, `.check`, `.pill`, `.block`.

- [x] **Step 1: Write the failing test**

`agent/tests/test_ui.py`:
```python
from tide_agent.ui.headless import HeadlessUI


def test_headless_prints_each_call():
    lines = []
    ui = HeadlessUI(out=lines.append)
    ui.show_join("10.10.0.1", None)
    ui.show_preflight([{"id": "internet", "label": "Offline", "detail": "", "state": "ok"}])
    ui.block("ChatGPT — closed", False)
    ui.done(3, "10:58")
    assert lines == ["[join] server=10.10.0.1", "[preflight] ok:Offline", "[block] ChatGPT — closed",
                     "[done] 3 files at 10:58"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd agent && pytest tests/test_ui.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [x] **Step 3: Implement**

`agent/tide_agent/ui/headless.py`:
```python
from typing import Callable


class HeadlessUI:
    def __init__(self, out: Callable[[str], None] = print) -> None:
        self.out = out

    def show_join(self, server, error=None): self.out(f"[join] server={server}" + (f" error={error}" if error else ""))
    def show_preflight(self, checks): self.out("[preflight] " + " ".join(f"{c['state']}:{c['label']}" for c in checks))
    def start(self, seat_no, set_name, ends_at_local, folder): self.out(f"[start] PC-{seat_no:02d} set {set_name} folder {folder}")
    def set_ends_at(self, ends_at_local): self.out(f"[time] ends_at={ends_at_local:.0f}")
    def notice(self, text): self.out(f"[notice] {text}")
    def block(self, title, persistent=False): self.out(f"[block] {title}" + (" (until offline)" if persistent else ""))
    def unblock(self): self.out("[unblock]")
    def done(self, n_files, at): self.out(f"[done] {n_files} files at {at}")
    def error(self, text): self.out(f"[error] {text}")
    def quit(self): self.out("[quit]")
```

`agent/tide_agent/ui/webview_ui.py`:
```python
import json
import threading
from pathlib import Path

import webview

WEB = Path(__file__).parent / "web"


class WebviewUI:
    def __init__(self) -> None:
        screen = webview.screens[0] if webview.screens else None
        sw, sh = (screen.width, screen.height) if screen else (1920, 1080)
        self._persistent = False
        self.main = webview.create_window("Tide", str(WEB / "index.html"), width=440, height=600, resizable=False)
        self.pill = webview.create_window("Tide timer", str(WEB / "pill.html"), width=460, height=60,
                                          x=(sw - 460) // 2, y=10, frameless=True, on_top=True,
                                          hidden=True, easy_drag=True, resizable=False)
        self.overlay = webview.create_window("Tide", str(WEB / "overlay.html"), width=sw, height=sh, x=0, y=0,
                                             frameless=True, on_top=True, hidden=True, resizable=False)

    def bind(self, api) -> None:
        self.main.expose(api.join)
        self.pill.expose(api.submit)

    def run(self, func) -> None:
        webview.start(func)

    @staticmethod
    def _js(win, fn: str, *args) -> None:
        win.evaluate_js(f"window.tide && tide.{fn}(...{json.dumps(list(args))})")

    def show_join(self, server, error=None): self._js(self.main, "showJoin", server, error)
    def show_preflight(self, checks): self._js(self.main, "showPreflight", checks)

    def start(self, seat_no, set_name, ends_at_local, folder):
        self.main.hide()
        self.pill.show()
        self._js(self.pill, "start", f"PC-{seat_no:02d}", f"Set {set_name}", ends_at_local * 1000)

    def set_ends_at(self, ends_at_local): self._js(self.pill, "setEnds", ends_at_local * 1000)
    def notice(self, text): self._js(self.pill, "notice", text)

    def block(self, title, persistent=False):
        self._persistent = persistent
        self._js(self.overlay, "block", title, persistent)
        self.overlay.show()
        if not persistent:
            threading.Timer(4.0, self._auto_hide).start()

    def _auto_hide(self):
        if not self._persistent:
            self.overlay.hide()

    def unblock(self):
        self._persistent = False
        self.overlay.hide()

    def done(self, n_files, at):
        self.pill.hide()
        self.main.show()
        self._js(self.main, "done", n_files, at)
        threading.Timer(10.0, self.quit).start()

    def error(self, text): self._js(self.main, "error", text)

    def quit(self):
        for w in (self.overlay, self.pill, self.main):
            try:
                w.destroy()
            except Exception:
                pass
```

`agent/tide_agent/ui/web/style.css` (tokens and components copied from `design/mock-ui.html`):
```css
:root{--bg:#F5F6F8;--surface:#fff;--ink:#0F172A;--muted:#64748B;--line:#E6E8EC;--brand:#0B7A83;--brand-2:#E6F4F5;
--ok:#16A34A;--ok-bg:#EAF7EE;--warn:#D97706;--warn-bg:#FDF3E3;--crit:#DC2626;--crit-bg:#FDECEC;
--font:"Segoe UI Variable","Segoe UI",system-ui,sans-serif;--mono:"Cascadia Code",Consolas,monospace}
*{box-sizing:border-box}html,body{margin:0;height:100%;font-family:var(--font);color:var(--ink);background:var(--surface);font-size:14px}
.body{padding:26px 28px;display:flex;flex-direction:column;gap:16px}
h1{font-size:22px;margin:0;letter-spacing:-.015em}
.sub{color:var(--muted)}
.lbl{display:block;font-size:12px;font-weight:600;color:var(--muted);margin:0 0 6px;text-transform:uppercase;letter-spacing:.05em}
.input{width:100%;border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:inherit}
.input.code{font-family:var(--mono);font-size:22px;font-weight:700;letter-spacing:.3em;text-transform:uppercase;text-align:center}
.two{display:grid;grid-template-columns:1fr 110px;gap:10px}
.btn{border:0;background:var(--brand);color:#fff;padding:12px 22px;border-radius:10px;font:inherit;font-weight:600;font-size:15px;cursor:pointer}
.btn[disabled]{opacity:.5}
.found{display:inline-flex;gap:8px;align-items:center;align-self:flex-start;background:var(--ok-bg);color:#15803D;font-size:12px;font-weight:600;padding:5px 10px;border-radius:99px}
.found.no{background:var(--warn-bg);color:#B45309}
.err{color:var(--crit);font-weight:500;min-height:1em}
.check{display:flex;align-items:center;gap:12px;padding:11px 12px;border-radius:10px}
.check .ci{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;flex:none;font-weight:700}
.check.ok .ci{background:var(--ok-bg);color:var(--ok)}
.check.warn{background:var(--warn-bg)}.check.warn .ci{background:#FBE3BF;color:var(--warn)}
.check.fail{background:var(--crit-bg)}.check.fail .ci{background:#F9CFCF;color:var(--crit)}
.check.run .ci{border:2px solid var(--line);border-top-color:var(--brand);animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.ct{font-weight:600}.cd{font-size:12px;color:var(--muted)}
.waiting{text-align:center;padding:14px;border-radius:10px;background:var(--bg);color:var(--muted);font-weight:500}
.done-ic{width:64px;height:64px;border-radius:50%;background:var(--ok-bg);color:var(--ok);display:grid;place-items:center;margin:20px auto 0;font-size:30px}
.hidden{display:none!important}
```

`agent/tide_agent/ui/web/index.html`:
```html
<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css"></head><body>
<section id="join" class="body">
  <h1>Join lab test</h1>
  <span id="server" class="found no">Looking for teacher…</span>
  <div><label class="lbl">Code</label><input id="code" class="input code" maxlength="6" autofocus></div>
  <div class="two">
    <div><label class="lbl">Roll no.</label><input id="roll" class="input" maxlength="20"></div>
    <div><label class="lbl">Seat</label><input id="seat" class="input" type="number" min="1" max="200"></div>
  </div>
  <div id="err" class="err"></div>
  <button id="go" class="btn">Join</button>
</section>
<section id="pre" class="body hidden">
  <h1>Getting ready</h1><div id="checks"></div>
  <div id="wait" class="waiting">Waiting for teacher to start</div>
</section>
<section id="fin" class="body hidden" style="text-align:center">
  <div class="done-ic">✓</div><h1>Submitted</h1><div id="finsub" class="sub"></div>
  <div class="sub" style="font-size:12px">You can leave. Tide closes in 10 s.</div>
</section>
<script>
const $ = id => document.getElementById(id);
const show = id => ["join","pre","fin"].forEach(s => $(s).classList.toggle("hidden", s !== id));
const ICON = {ok:"✓", warn:"!", fail:"✕", run:""};
window.tide = {
  showJoin(server, error) {
    show("join");
    $("server").textContent = server ? `Teacher found · ${server}` : "Teacher not found yet";
    $("server").classList.toggle("no", !server);
    $("err").textContent = error || "";
  },
  showPreflight(checks) {
    show("pre");
    $("checks").innerHTML = "";
    for (const c of checks) {
      const row = document.createElement("div");
      row.className = `check ${c.state}`;
      row.innerHTML = `<div class="ci"></div><div><div class="ct"></div><div class="cd"></div></div>`;
      row.querySelector(".ci").textContent = ICON[c.state] || "";
      row.querySelector(".ct").textContent = c.label;
      row.querySelector(".cd").textContent = c.detail;
      $("checks").appendChild(row);
    }
    const blocked = checks.some(c => c.state === "fail");
    $("wait").textContent = blocked ? "Fix the red item to continue" : "Waiting for teacher to start";
  },
  done(n, at) { show("fin"); $("finsub").textContent = `${n} files · ${at}`; },
  error(text) { $("err").textContent = text; },
};
$("seat").value = (location.hash.match(/seat=(\d+)/) || [])[1] || "";
$("go").onclick = async () => {
  $("go").disabled = true; $("err").textContent = "";
  const r = await window.pywebview.api.join($("code").value.trim(), $("roll").value.trim(), $("seat").value);
  $("go").disabled = false;
  if (!r.ok) $("err").textContent = r.error;
};
</script></body></html>
```

`agent/tide_agent/ui/web/pill.html`:
```html
<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css">
<style>
body{background:transparent;display:flex;align-items:center;justify-content:center}
.pill{display:flex;align-items:center;gap:14px;padding:7px 8px 7px 16px;border-radius:999px;background:#fff;box-shadow:0 6px 20px rgba(0,0,0,.25);font-size:13px;width:100%;height:100%}
.live{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px var(--ok-bg)}
.seat{font-weight:700}.set{color:var(--muted)}.sep{width:1px;height:18px;background:var(--line)}
.time{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;flex:1}
.time.low{color:var(--crit)}
.sub{background:var(--brand);color:#fff;border:0;border-radius:999px;padding:7px 14px;font-weight:600;cursor:pointer}
.note{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:var(--warn-bg);color:#92400E;font-weight:600;border-radius:999px;padding:0 16px;text-align:center}
</style></head><body>
<div class="pill pywebview-drag-region">
  <span class="live"></span><span id="seat" class="seat"></span><span id="set" class="set"></span>
  <span class="sep"></span><span id="time" class="time">--:--</span>
  <button id="sub" class="sub">Submit</button>
</div>
<div id="note" class="note"></div>
<script>
let ends = 0;
const pad = n => String(n).padStart(2, "0");
function render() {
  const s = Math.max(0, Math.round((ends - Date.now()) / 1000));
  const el = document.getElementById("time");
  el.textContent = `${Math.floor(s / 60)}:${pad(s % 60)}`;
  el.classList.toggle("low", s < 300);
}
setInterval(render, 500);
window.tide = {
  start(seat, set, endsMs) { document.getElementById("seat").textContent = seat; document.getElementById("set").textContent = set; ends = endsMs; render(); },
  setEnds(endsMs) { ends = endsMs; render(); },
  notice(text) { const n = document.getElementById("note"); n.textContent = text; n.style.display = "flex"; setTimeout(() => n.style.display = "none", 6000); },
};
document.getElementById("sub").onclick = async () => {
  const b = document.getElementById("sub");
  if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = "Sure?"; setTimeout(() => { b.dataset.armed = ""; b.textContent = "Submit"; }, 3000); return; }
  b.disabled = true; b.textContent = "Submitting…";
  await window.pywebview.api.submit();
};
</script></body></html>
```

`agent/tide_agent/ui/web/overlay.html`:
```html
<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css">
<style>
body{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;color:#fff;text-align:center;background:#B91C1C}
body.net{background:#0F172A}
.shield{width:84px;height:84px;border-radius:24px;background:rgba(255,255,255,.14);display:grid;place-items:center;font-size:40px}
h3{margin:0;font-size:34px;letter-spacing:-.02em}p{margin:0;opacity:.85;font-size:16px}
</style></head><body>
<div class="shield">⛔</div><h3 id="title">Blocked</h3><p id="sub">Reported to your invigilator.</p>
<script>
window.tide = {
  block(title, persistent) {
    document.body.classList.toggle("net", persistent);
    document.getElementById("title").textContent = persistent ? "Internet detected" : title;
    document.getElementById("sub").textContent = persistent ? "Disconnect Wi-Fi / hotspot to continue." : "Reported to your invigilator.";
  },
};
</script></body></html>
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd agent && pytest tests -v`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add agent
git commit -m "feat(agent): headless and pywebview UI (join, pre-flight, timer pill, block overlay)"
```

### Task 19: Windows platform

**Files:**
- Create: `agent/tide_agent/urlhost.py`, `agent/tide_agent/win/__init__.py`, `windows.py`, `browser.py`, `procs.py`, `net.py`, `devices.py`, `input.py`, `capture.py`, `agent/scripts/win_smoke.py`
- Test: `agent/tests/test_urlhost.py` (any OS), `agent/tests/test_win_smoke.py` (Windows only)

**Interfaces:**
- Produces: `host_from_value(address_bar_text) -> str` (pure); `WinPlatform()` implementing every `Platform` method

Implementation notes:
- UI Automation must be initialised per thread: wrap calls in `uiautomation.UIAutomationInitializerInThread()`.
- `SetForegroundWindow` from a background process is refused unless the process "just sent input", so press and release Alt first.
- UWP windows report `ApplicationFrameHost.exe`; the real process is a child window's PID.

- [x] **Step 1: Write the failing tests**

`agent/tests/test_urlhost.py`:
```python
from tide_agent.urlhost import host_from_value


def test_host_from_value():
    assert host_from_value("chatgpt.com") == "chatgpt.com"
    assert host_from_value("https://www.Poe.com/chat/x") == "www.poe.com"
    assert host_from_value("") == ""
    assert host_from_value("file:///C:/Exam/22BCS107/setA.pdf") == ""
    assert host_from_value("edge://newtab") == ""
    assert host_from_value("localhost:5173/x") == "localhost"
```

`agent/tests/test_win_smoke.py`:
```python
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_real_platform_calls():
    from tide_agent.win import WinPlatform
    p = WinPlatform()
    assert p.processes()
    assert any(a.up for a in p.adapters().values())
    assert isinstance(p.internet(), bool)
    assert isinstance(p.removable_drives(), set)
    assert isinstance(p.clipboard_seq(), int)
    shot = p.screenshot()
    assert shot is None or shot[:2] == b"\xff\xd8"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd agent && pytest tests/test_urlhost.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [x] **Step 3: Implement**

`agent/tide_agent/urlhost.py`:
```python
from urllib.parse import urlparse

LOCAL_SCHEMES = ("file:", "edge:", "chrome:", "about:", "brave:", "opera:", "view-source:")


def host_from_value(value: str) -> str:
    v = (value or "").strip()
    if not v or v.lower().startswith(LOCAL_SCHEMES):
        return ""
    if "://" not in v:
        v = "http://" + v
    return (urlparse(v).hostname or "").lower()
```

`agent/tide_agent/win/windows.py`:
```python
from functools import lru_cache

import psutil
import win32api
import win32gui
import win32process

from tide_agent.platform import WindowInfo


@lru_cache(maxsize=512)
def pe_info(exe: str) -> tuple[str, str]:
    try:
        lang, cp = win32api.GetFileVersionInfo(exe, "\\VarFileInfo\\Translation")[0]
        base = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\"
        desc = win32api.GetFileVersionInfo(exe, base + "FileDescription") or ""
        orig = win32api.GetFileVersionInfo(exe, base + "OriginalFilename") or ""
        return str(desc), str(orig)
    except Exception:
        return "", ""


def _real_pid(hwnd: int, pid: int, name: str) -> int:
    if name.lower() != "applicationframehost.exe":
        return pid
    found = []

    def cb(child, _):
        _, cpid = win32process.GetWindowThreadProcessId(child)
        if cpid != pid:
            found.append(cpid)
    try:
        win32gui.EnumChildWindows(hwnd, cb, None)
    except Exception:
        pass
    return found[0] if found else pid


def foreground() -> WindowInfo | None:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    title = win32gui.GetWindowText(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        name = psutil.Process(pid).name()
        pid = _real_pid(hwnd, pid, name)
        proc = psutil.Process(pid)
        name, exe = proc.name(), proc.exe()
    except psutil.Error:
        name, exe = "", ""
    desc, orig = pe_info(exe) if exe else ("", "")
    return WindowInfo(hwnd, pid, name, exe, title, desc, orig)
```

`agent/tide_agent/win/browser.py`:
```python
import uiautomation as auto

from tide_agent.urlhost import host_from_value

ADDRESS_NAMES = ("Address and search bar", "Search or enter web address", "Search with Google or enter address",
                 "Search or enter address", "Address field")


def browser_host(hwnd: int, process: str) -> str | None:
    try:
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            edit = None
            for name in ADDRESS_NAMES:
                c = root.EditControl(searchDepth=14, Name=name)
                if c.Exists(0, 0):
                    edit = c
                    break
            if edit is None:
                c = root.EditControl(searchDepth=14)
                edit = c if c.Exists(0, 0) else None
            if edit is None:
                return None
            return host_from_value(edit.GetValuePattern().Value)
    except Exception:
        return None
```

`agent/tide_agent/win/procs.py`:
```python
import psutil

from tide_agent.platform import ProcInfo
from tide_agent.win.windows import pe_info


def processes() -> dict[int, ProcInfo]:
    out = {}
    for p in psutil.process_iter(["pid", "name", "exe"]):
        exe = p.info.get("exe") or ""
        desc, orig = pe_info(exe) if exe else ("", "")
        out[p.info["pid"]] = ProcInfo(p.info["pid"], p.info.get("name") or "", exe, desc, orig)
    return out


def kill(pid: int) -> None:
    try:
        p = psutil.Process(pid)
        p.terminate()
        p.wait(1)
    except psutil.TimeoutExpired:
        p.kill()
    except psutil.Error:
        pass
```

`agent/tide_agent/win/net.py`:
```python
import ipaddress
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psutil

from tide_agent.platform import AdapterInfo, Peer

_ssid_cache: tuple[float, str | None] = (0.0, None)
_pool = ThreadPoolExecutor(max_workers=2)


def _ssid() -> str | None:
    global _ssid_cache
    if time.monotonic() - _ssid_cache[0] < 5:
        return _ssid_cache[1]
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
                             timeout=3, creationflags=subprocess.CREATE_NO_WINDOW).stdout
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
        ssid = m.group(1).strip() if m else None
    except Exception:
        ssid = None
    _ssid_cache = (time.monotonic(), ssid)
    return ssid


def adapters() -> dict[str, AdapterInfo]:
    out = {}
    for name, st in psutil.net_if_stats().items():
        if "loopback" in name.lower():
            continue
        wifi = any(k in name.lower() for k in ("wi-fi", "wifi", "wireless", "wlan"))
        out[name] = AdapterInfo(name, st.isup, wifi, _ssid() if wifi and st.isup else None)
    return out


def _http_probe() -> bool:
    try:
        r = httpx.get("http://www.msftconnecttest.com/connecttest.txt", timeout=1.5)
        return r.text.strip() == "Microsoft Connect Test"
    except Exception:
        return False


def _tcp_probe() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=1.5).close()
        return True
    except OSError:
        return False


def internet() -> bool:
    futures = [_pool.submit(_http_probe), _pool.submit(_tcp_probe)]
    return any(f.result() for f in futures)


def lan_peers(server_ip: str) -> list[Peer]:
    peers = []
    for c in psutil.net_connections("inet"):
        if c.status != psutil.CONN_ESTABLISHED or not c.raddr:
            continue
        ip = c.raddr.ip
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not addr.is_private or addr.is_loopback or ip == server_ip:
            continue
        try:
            name = psutil.Process(c.pid).name() if c.pid else ""
        except psutil.Error:
            name = ""
        peers.append(Peer(ip, c.raddr.port, name))
    return peers
```

`agent/tide_agent/win/devices.py`:
```python
import time

import psutil
import win32clipboard
import win32con


def removable_drives() -> set[str]:
    return {p.mountpoint for p in psutil.disk_partitions(all=False) if "removable" in p.opts}


def clipboard_seq() -> int:
    return win32clipboard.GetClipboardSequenceNumber()


def clipboard_text() -> str | None:
    for _ in range(3):
        try:
            win32clipboard.OpenClipboard()
        except Exception:
            time.sleep(0.05)
            continue
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()
    return None
```

`agent/tide_agent/win/input.py`:
```python
import time

import win32api
import win32con
import win32gui


def close_tab(hwnd: int) -> None:
    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)                     # unlock SetForegroundWindow
    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.05)
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("W"), 0, 0, 0)
    win32api.keybd_event(ord("W"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
```

`agent/tide_agent/win/capture.py`:
```python
import io

import mss
from PIL import Image


def screenshot(max_width: int = 1280) -> bytes | None:
    try:
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        img.thumbnail((max_width, max_width))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return buf.getvalue()
    except Exception:
        return None
```

`agent/tide_agent/win/__init__.py`:
```python
from tide_agent.win import browser, capture, devices, input, net, procs, windows


class WinPlatform:
    foreground = staticmethod(windows.foreground)
    browser_host = staticmethod(browser.browser_host)
    processes = staticmethod(procs.processes)
    kill = staticmethod(procs.kill)
    adapters = staticmethod(net.adapters)
    internet = staticmethod(net.internet)
    lan_peers = staticmethod(net.lan_peers)
    removable_drives = staticmethod(devices.removable_drives)
    clipboard_seq = staticmethod(devices.clipboard_seq)
    clipboard_text = staticmethod(devices.clipboard_text)
    close_tab = staticmethod(input.close_tab)
    screenshot = staticmethod(capture.screenshot)
```

`agent/scripts/win_smoke.py`:
```python
"""Run on a Windows PC: python agent/scripts/win_smoke.py  (switch windows while it runs)."""
import time

from tide_agent.win import WinPlatform

p = WinPlatform()
print("processes:", len(p.processes()))
print("adapters:", p.adapters())
print("internet:", p.internet())
print("usb:", p.removable_drives(), "clipboard seq:", p.clipboard_seq())
shot = p.screenshot()
print("screenshot bytes:", len(shot or b""))
for _ in range(20):
    w = p.foreground()
    host = p.browser_host(w.hwnd, w.process) if w else None
    print(f"{w.process if w else None!s:24} {host!s:22} {w.title[:60] if w else ''}")
    time.sleep(1)
```

- [x] **Step 4: Run tests**

Run: `cd agent && pytest tests -v`
Expected: all pass (the Windows smoke test is skipped off Windows).

- [x] **Step 5: Manual verification on Windows**

Run: `python agent/scripts/win_smoke.py`, then switch to Chrome on `chatgpt.com`, Edge with a local PDF, VS Code, and File Explorer.
Expected: Chrome prints host `chatgpt.com`; the Edge PDF prints host `""`; VS Code prints `Code.exe`; the screenshot size is > 20000 bytes; `internet: False` with the LAN cable only and `True` on Wi-Fi.

- [x] **Step 6: Commit**

```bash
git add agent
git commit -m "feat(agent): Windows platform (windows, browser URL, processes, network, devices, input, capture)"
```

### Task 20: Fake PC, app wiring, CLI, .exe build

**Files:**
- Create: `agent/tide_agent/fake.py`, `agent/tide_agent/main.py`, `agent/tide_agent/__main__.py`, `agent/tide-agent.spec`
- Test: `agent/tests/test_fake_e2e.py`

**Interfaces:**
- Consumes: everything above; the server from Phase 2 (in the test, via uvicorn in a thread)
- Produces:
  - `FakePlatform` (in `tide_agent/fake.py`, a scripted student PC) with `command(line) -> str`; commands: `code`, `ai`, `poe`, `app`, `wifi`, `wifi off`, `old`, `paste`, `usb`, `clip`, `help`
  - `AgentConfig(server, exam_root, ext_dir, state_dir, roots, code, roll, seat)`, `AgentApp(platform, ui, cfg)` with `async boot()`, `async join(code, roll, seat_no) -> dict`, `join_from_ui`, `submit_from_ui`, `async run_forever()`
  - CLI: `tide-agent [--server HOST[:PORT]] [--fake] [--headless --code C --roll R --seat N] [--exam-root DIR]`

- [x] **Step 1: Write the failing end-to-end test**

`agent/tests/test_fake_e2e.py` (spins up the real server in-process):
```python
import asyncio
import socket
import threading
import time

import httpx
import uvicorn

from tide_agent.fake import FakePlatform
from tide_agent.main import AgentApp, AgentConfig
from tide_agent.ui.headless import HeadlessUI


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def test_fake_student_end_to_end(tmp_path):
    from tide_server.app import create_app
    from tide_server.config import Settings
    port = free_port()
    settings = Settings(_env_file=None, data_dir=tmp_path / "srv", openrouter_api_key="", demo=True,
                        background_tasks=False, console_dir=tmp_path / "none", port=port)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(base_url=base) as http:
        for _ in range(50):
            try:
                tok = (await http.post("/api/teacher/login", json={"pin": "2468"})).json()["token"]
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.1)
        H = {"Authorization": f"Bearer {tok}"}
        code = (await http.get("/api/teacher/exam", headers=H)).json()["exam"]["join_code"]

        lines = []
        fake = FakePlatform(tmp_path / "home")
        cfg = AgentConfig(server=f"127.0.0.1:{port}", exam_root=tmp_path / "Exam", ext_dir=fake.ext_dir,
                          state_dir=tmp_path / "state", roots=[fake.old_dir])
        app = AgentApp(fake, HeadlessUI(out=lines.append), cfg)
        await app.boot()
        assert (await app.join(code, "22bcs107", 7))["ok"]
        for _ in range(100):
            if any(l.startswith("[preflight] ok:Offline") for l in lines):
                break
            await asyncio.sleep(0.05)
        await http.post("/api/teacher/start", headers=H)
        for _ in range(100):
            if any(l.startswith("[start]") for l in lines):
                break
            await asyncio.sleep(0.05)
        assert (tmp_path / "Exam" / "22BCS107" / "questions.txt").exists()

        fake.command("ai")
        await asyncio.sleep(1.2)
        assert any("ChatGPT — closed" in l for l in lines)
        seats = (await http.get("/api/teacher/results", headers=H)).json()["rows"]
        me = next(r for r in seats if r["seat_no"] == 7)
        assert any(f["title"] == "ChatGPT — closed" for f in me["flags"])

        await app.engine.submit(auto=False)
        assert any(l.startswith("[done]") for l in lines)
    server.should_exit = True
    time.sleep(0.2)
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd agent && pytest tests/test_fake_e2e.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'tide_agent.fake'`

- [x] **Step 3: Implement**

`agent/tide_agent/fake.py`:
```python
"""A pretend student PC for dev on any OS. Type commands in the terminal to act out cheats."""
import io
import sys
import threading
from pathlib import Path

from .platform import AdapterInfo, Peer, ProcInfo, WindowInfo

OLD_CODE = "\n".join(["#include <stdio.h>", "#include <string.h>", "int is_private(int a, int b) {",
                      "    if (a == 10) return 1;", "    if (a == 172 && b >= 16 && b <= 31) return 1;",
                      "    if (a == 192 && b == 168) return 1;", "    return 0;", "}",
                      "char cls(int a) {", "    if (a < 128) return 'A';", "    if (a < 192) return 'B';",
                      "    if (a < 224) return 'C';", "    if (a < 240) return 'D';", "    return 'E';", "}",
                      "int main(void) {", "    int n, a, b, c, d;", '    scanf("%d", &n);',
                      "    while (n--) {", '        scanf("%d.%d.%d.%d", &a, &b, &c, &d);',
                      '        printf("%c %s\\n", cls(a), is_private(a, b) ? "private" : "public");',
                      "    }", "    return 0;", "}"])

HELP = "commands: code | ai | poe | app | wifi | wifi off | old | paste | usb | clip | help"


class FakePlatform:
    def __init__(self, home: Path, exam_root: Path | None = None, roll: str = "22BCS107") -> None:
        self.home = home
        self.old_dir = home / "old"
        self.old_dir.mkdir(parents=True, exist_ok=True)
        (self.old_dir / "dsa_lab5.cpp").write_text(OLD_CODE)
        self.ext_dir = home / ".vscode" / "extensions"
        (self.ext_dir / "github.copilot-1.250.0").mkdir(parents=True, exist_ok=True)
        self.exam_root, self.roll = exam_root, roll
        self._lock = threading.Lock()
        self.code_window()
        self.host: str | None = None
        self.procs = {1: ProcInfo(1, "explorer.exe"), 10: ProcInfo(10, "Code.exe")}
        self.wifi_on = False
        self.drives: set[str] = set()
        self.clip_seq, self.clip = 1, None
        self.log: list[str] = []

    # --- scripted actions -------------------------------------------------
    def code_window(self, title: str | None = None) -> None:
        self.window = WindowInfo(100, 10, "Code.exe", "C:/VS Code/Code.exe",
                                 title or f"main.c - {getattr(self, 'roll', '22BCS107')} - Visual Studio Code",
                                 "Visual Studio Code", "Code.exe")
        self.host = None

    def command(self, line: str) -> str:
        cmd = line.strip().lower()
        with self._lock:
            if cmd == "code":
                self.code_window()
            elif cmd == "ai":
                self.window, self.host = WindowInfo(200, 20, "chrome.exe", "", "ChatGPT", "Google Chrome"), "chatgpt.com"
                self.procs[20] = ProcInfo(20, "chrome.exe")
            elif cmd == "poe":
                self.window, self.host = WindowInfo(201, 20, "chrome.exe", "", "Fast AI Chat - Poe", "Google Chrome"), "poe.com"
                self.procs[20] = ProcInfo(20, "chrome.exe")
            elif cmd == "app":
                self.window = WindowInfo(300, 30, "notegpt.exe", "C:/Users/s/NoteGPT/notegpt.exe",
                                         "NoteGPT - AI Notes & Answers", "NoteGPT")
                self.procs[30] = ProcInfo(30, "notegpt.exe")
            elif cmd == "wifi":
                self.wifi_on = True
            elif cmd == "wifi off":
                self.wifi_on = False
            elif cmd == "old":
                self.code_window("dsa_lab5.cpp - old - Visual Studio Code")
            elif cmd == "paste":
                if self.exam_root:
                    (self.exam_root / self.roll / "main.c").write_text(OLD_CODE.replace("cls", "klass"))
            elif cmd == "usb":
                self.drives = {"E:\\"}
            elif cmd == "clip":
                self.clip_seq, self.clip = self.clip_seq + 1, OLD_CODE
            else:
                return HELP
        return f"ok: {cmd}"

    def read_stdin_forever(self) -> None:
        def loop():
            print(HELP, flush=True)
            for line in sys.stdin:
                print(self.command(line), flush=True)
        threading.Thread(target=loop, daemon=True).start()

    # --- Platform -----------------------------------------------------------
    def foreground(self): return self.window
    def browser_host(self, hwnd, process): return self.host
    def processes(self): return dict(self.procs)

    def kill(self, pid):
        with self._lock:
            self.procs.pop(pid, None)
            self.log.append(f"kill {pid}")
            if self.window.pid == pid:
                self.code_window()

    def adapters(self):
        return {"Ethernet": AdapterInfo("Ethernet", True),
                "Wi-Fi": AdapterInfo("Wi-Fi", self.wifi_on, True, "Redmi Note" if self.wifi_on else None)}

    def internet(self): return self.wifi_on
    def lan_peers(self, server_ip): return []
    def removable_drives(self): return set(self.drives)
    def clipboard_seq(self): return self.clip_seq
    def clipboard_text(self): return self.clip

    def close_tab(self, hwnd):
        with self._lock:
            self.log.append(f"close_tab {hwnd}")
            self.code_window()

    def screenshot(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return None
        img = Image.new("RGB", (640, 360), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 640, 28], fill="#DEE1E6")
        d.text((12, 8), self.host or self.window.title, fill="#333")
        d.text((220, 170), self.window.title, fill="#111")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return buf.getvalue()
```

`agent/tide_agent/main.py`:
```python
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
```

`agent/tide_agent/__main__.py`:
```python
import argparse
import asyncio
import sys
from pathlib import Path


class _Api:
    def __init__(self, app):
        self.app = app

    def join(self, code, roll, seat):
        return self.app.join_from_ui(code, roll, seat)

    def submit(self):
        return self.app.submit_from_ui()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="tide-agent", description="Tide student agent")
    ap.add_argument("--server", help="teacher HOST[:PORT] (skips LAN discovery)")
    ap.add_argument("--fake", action="store_true", help="simulated PC for dev on any OS; type commands here")
    ap.add_argument("--headless", action="store_true", help="no windows; print UI events")
    ap.add_argument("--code")
    ap.add_argument("--roll")
    ap.add_argument("--seat", type=int)
    ap.add_argument("--exam-root", type=Path)
    args = ap.parse_args(argv)

    from .main import AgentApp, AgentConfig
    if args.fake:
        from .fake import FakePlatform
        platform = FakePlatform(Path.home() / "TideFakePC")
        platform.read_stdin_forever()
    elif sys.platform == "win32":
        from .win import WinPlatform
        platform = WinPlatform()
    else:
        sys.exit("The Tide agent runs on Windows. Use --fake to simulate a student PC.")
    cfg = AgentConfig.from_args(args, fake=platform if args.fake else None)

    if args.headless:
        from .ui.headless import HeadlessUI
        asyncio.run(AgentApp(platform, HeadlessUI(), cfg).run_forever())
        return
    from .ui.webview_ui import WebviewUI
    ui = WebviewUI()
    app = AgentApp(platform, ui, cfg)
    ui.bind(_Api(app))
    ui.run(lambda: asyncio.run(app.run_forever()))


if __name__ == "__main__":
    main()
```

`agent/tide-agent.spec` (PyInstaller, build on Windows):
```python
# pyinstaller agent/tide-agent.spec  ->  dist/tide-agent.exe
a = Analysis(["tide_agent/__main__.py"], pathex=["."],
             datas=[("tide_agent/ui/web", "tide_agent/ui/web")],
             hiddenimports=["tide_agent.win", "uiautomation", "webview.platforms.edgechromium"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="tide-agent", console=False, onefile=True,
          icon="../design/tide.ico")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd agent && pytest tests -v`
Expected: all pass, including `test_fake_student_end_to_end` (~3 s).

- [x] **Step 5: Manual run in fake mode (any OS)**

Terminal 1: `tide-server --demo`. Terminal 2: `tide-agent --fake --server 127.0.0.1`.
Join with the code from the console, roll `22BCS107`, seat `7`. Press **Start** in the console, then type `ai`, `poe`, `wifi`, `wifi off`, `old`, `paste`, one per line, in terminal 2.
Expected: each one appears on seat 7 in the console within ~2 s (`poe` shows "Jev 0.9x" when `OPENROUTER_API_KEY` is set).

- [x] **Step 6: Build the .exe (Windows)**

Run: `cd agent && pyinstaller tide-agent.spec`
Expected: `agent/dist/tide-agent.exe` exists and opens the Join window on double-click.

- [x] **Step 7: Commit**

```bash
git add agent
git commit -m "feat(agent): fake PC mode, app wiring, CLI, PyInstaller spec"
```

---
## Phase 4 — Teacher console (`console/`)

React + Vite + TypeScript, no UI library. Visual source of truth: `design/mock-ui.html`. In dev, Vite proxies `/api` and `/ws` to the server on :8765. For the demo, `npm run build` writes `console/dist`, and the server serves it at `/`.

### Task 21: Console scaffold, types, API client, room state

**Files:**
- Create: `console/package.json`, `console/tsconfig.json`, `console/vite.config.ts`, `console/index.html`, `console/src/types.ts`, `console/src/api.ts`, `console/src/state.ts`, `console/src/styles.css`
- Test: `console/src/state.test.ts`

**Interfaces:**
- Consumes: server JSON shapes from `serialize.py` (Task 4) and `/ws/console` (Task 11)
- Produces:
  - Types `Status, Seat, Flag, Exam, EventItem, ServerMsg, Room`
  - `emptyRoom`, `reduce(room, msg, nowSec?) -> Room`, `openAlerts(room) -> Flag[]`, `counts(room) -> {ok, warn, crit, off}`, `remaining(exam, offset, nowSec?) -> number`, `fmtClock(sec) -> string`, `seatsGrid(room, size=60) -> (Seat | {seat_no, placeholder: true})[]`
  - `auth.{token,set,clear}`, `api.*` (one function per endpoint), `connect(onMsg) -> () => void`

- [x] **Step 1: Scaffold**

`console/package.json`:
```json
{
  "name": "tide-console",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1" },
  "devDependencies": {
    "@types/react": "^18.3.3", "@types/react-dom": "^18.3.0", "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4", "vite": "^5.4.0", "vitest": "^2.0.5"
  }
}
```
`console/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext",
    "moduleResolution": "Bundler", "jsx": "react-jsx", "strict": true, "noEmit": true,
    "skipLibCheck": true, "isolatedModules": true, "types": ["vite/client"]
  },
  "include": ["src"]
}
```
`console/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8765", "/ws": { target: "ws://localhost:8765", ws: true } },
  },
});
```
`console/index.html`:
```html
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" href="/logo.svg" /><title>Tide</title></head>
  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```
Copy `design/logo.svg` to `console/public/logo.svg`.

`console/src/styles.css`: copy the whole `<style>` block of `design/mock-ui.html` **except** the rules under the comments `mock switcher`, `student: desktop frame`, `fake VS Code`, `timer pill`, `block overlay`, and `.screen`/`.screen.on`, `.done-ic`, and the `fake screenshots` group. Then append:
```css
.shot img{width:100%;display:block;border-radius:8px;border:1px solid var(--line)}
.login{max-width:360px;margin:12vh auto;padding:28px;display:flex;flex-direction:column;gap:14px}
.seat.placeholder{border:1.5px dashed #D5DAE1;background:transparent;cursor:default}
.seat.placeholder .no{color:#C2C9D2}
.chip.warnchip .dot{background:var(--warn)}
.menu{position:relative}
.menu-list{position:absolute;right:0;top:44px;background:var(--surface);border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);padding:6px;z-index:70;min-width:200px}
.menu-list button{display:block;width:100%;text-align:left;border:0;background:transparent;padding:8px 10px;border-radius:8px}
.menu-list button:hover{background:var(--bg)}
```

- [x] **Step 2: Write the failing test**

`console/src/state.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { counts, emptyRoom, fmtClock, openAlerts, reduce, remaining, seatsGrid } from "./state";
import type { Flag, Seat } from "./types";

const seat = (id: number, status: Seat["status"]): Seat => ({
  id, seat_no: id, roll: `R${id}`, set: "A", state: "live", status, flags: 0, fg_app: "VS Code",
  simulated: false, preflight: {},
});
const flag = (id: number, severity: Flag["severity"], status: Flag["status"] = "open", ts = id): Flag => ({
  id, seat_id: 1, seat_no: 1, ts, kind: "x", severity, title: `f${id}`, source: "rule", label: null,
  confidence: null, action: "none", status, has_shot: false, data: {},
});

describe("room state", () => {
  it("hello replaces the room and measures clock offset", () => {
    const r = reduce(emptyRoom, { t: "hello", exam: null, seats: [seat(1, "ok")], flags: [flag(1, "high")],
      mode: "jev", server_time: 1010 }, 1000);
    expect(r.seats[1].status).toBe("ok");
    expect(r.clockOffset).toBe(10);
    expect(r.mode).toBe("jev");
  });

  it("seat and flag updates upsert", () => {
    let r = reduce(emptyRoom, { t: "seat", seat: seat(2, "ok") });
    r = reduce(r, { t: "seat", seat: seat(2, "crit") });
    r = reduce(r, { t: "flag", flag: flag(5, "critical") });
    expect(r.seats[2].status).toBe("crit");
    expect(Object.keys(r.flags)).toEqual(["5"]);
  });

  it("open alerts: newest first, no info, no reviewed", () => {
    let r = emptyRoom;
    for (const f of [flag(1, "medium"), flag(2, "info"), flag(3, "high", "dismissed"), flag(4, "critical")])
      r = reduce(r, { t: "flag", flag: f });
    expect(openAlerts(r).map((f) => f.id)).toEqual([4, 1]);
  });

  it("counts buckets", () => {
    let r = emptyRoom;
    for (const s of [seat(1, "ok"), seat(2, "done"), seat(3, "warn"), seat(4, "crit"), seat(5, "off"), seat(6, "wait")])
      r = reduce(r, { t: "seat", seat: s });
    expect(counts(r)).toEqual({ ok: 2, warn: 1, crit: 1, off: 1 });
  });

  it("grid fills to 60 with placeholders", () => {
    const r = reduce(emptyRoom, { t: "seat", seat: seat(7, "ok") });
    const g = seatsGrid(r);
    expect(g.length).toBe(60);
    expect("placeholder" in g[0]).toBe(true);
    expect(g[6]).toMatchObject({ id: 7 });
  });

  it("clock helpers", () => {
    expect(fmtClock(42 * 60 + 18)).toBe("42:18");
    expect(fmtClock(0)).toBe("0:00");
    const exam = { id: 1, title: "t", duration_s: 60, join_code: "X", state: "live" as const, started_at: 0,
      ends_at: 1100, apps: [] };
    expect(remaining(exam, 10, 1000)).toBe(90);
    expect(remaining(null, 0, 1000)).toBe(0);
  });
});
```

- [x] **Step 3: Run test to verify it fails**

Run: `cd console && npm install && npm test`
Expected: FAIL, cannot resolve `./state`

- [x] **Step 4: Implement**

`console/src/types.ts`:
```ts
export type Status = "ok" | "warn" | "crit" | "off" | "wait" | "done";
export type Severity = "info" | "medium" | "high" | "critical";

export interface Seat {
  id: number; seat_no: number; roll: string; set: string | null; state: string; status: Status;
  flags: number; fg_app: string; simulated: boolean;
  preflight: { internet?: boolean; extensions?: string[]; denied_closed?: string[]; inventory_count?: number };
}
export interface Flag {
  id: number; seat_id: number; seat_no: number; ts: number; kind: string; severity: Severity; title: string;
  source: string; label: string | null; confidence: number | null; action: string;
  status: "open" | "dismissed" | "confirmed"; has_shot: boolean; data: Record<string, unknown>;
}
export interface Exam {
  id: number; title: string; duration_s: number; join_code: string; state: "lobby" | "live" | "ended";
  started_at: number | null; ends_at: number | null; apps: string[];
}
export interface EventItem { id: number; seat_id: number; ts: number; kind: string; text: string }
export type ServerMsg =
  | { t: "hello"; exam: Exam | null; seats: Seat[]; flags: Flag[]; mode: string; server_time: number }
  | { t: "seat"; seat: Seat } | { t: "flag"; flag: Flag } | { t: "event"; event: EventItem }
  | { t: "exam"; exam: Exam } | { t: "connected"; value: boolean };
export interface Room {
  exam: Exam | null; seats: Record<number, Seat>; flags: Record<number, Flag>; mode: string;
  clockOffset: number; lastEvent: EventItem | null; connected: boolean;
}
export type TimelineItem = ({ type: "event" } & EventItem) | ({ type: "flag" } & Flag);
export interface SeatDetail { seat: Seat; timeline: TimelineItem[]; growth: { ts: number; lines: number }[];
  files: { path: string; lines: number }[] }
export interface Results {
  rows: { seat_id: number; seat_no: number; roll: string; set: string | null; submitted_at: number | null;
    flags: { kind: string; severity: Severity; title: string }[]; max_match: number | null }[];
  pairs: { a: number; b: number | null; b_path: string | null; pct: number }[];
  flag_counts: Record<string, number>;
}
```

`console/src/state.ts`:
```ts
import type { Exam, Flag, Room, Seat, ServerMsg } from "./types";

export const emptyRoom: Room = { exam: null, seats: {}, flags: {}, mode: "heuristics", clockOffset: 0,
  lastEvent: null, connected: false };

const nowSec = () => Date.now() / 1000;

export function reduce(room: Room, m: ServerMsg, now = nowSec()): Room {
  switch (m.t) {
    case "hello":
      return { ...room, exam: m.exam, mode: m.mode, clockOffset: m.server_time - now, connected: true,
        seats: Object.fromEntries(m.seats.map((s) => [s.id, s])),
        flags: Object.fromEntries(m.flags.map((f) => [f.id, f])) };
    case "seat": return { ...room, seats: { ...room.seats, [m.seat.id]: m.seat } };
    case "flag": return { ...room, flags: { ...room.flags, [m.flag.id]: m.flag } };
    case "event": return { ...room, lastEvent: m.event };
    case "exam": return { ...room, exam: m.exam };
    case "connected": return { ...room, connected: m.value };
  }
}

export function openAlerts(room: Room): Flag[] {
  return Object.values(room.flags).filter((f) => f.status === "open" && f.severity !== "info")
    .sort((a, b) => b.ts - a.ts || b.id - a.id);
}

export function counts(room: Room) {
  const c = { ok: 0, warn: 0, crit: 0, off: 0 };
  for (const s of Object.values(room.seats)) {
    if (s.status === "ok" || s.status === "done") c.ok++;
    else if (s.status === "warn") c.warn++;
    else if (s.status === "crit") c.crit++;
    else if (s.status === "off") c.off++;
  }
  return c;
}

export function seatsGrid(room: Room, size = 60): (Seat | { seat_no: number; placeholder: true })[] {
  const byNo = new Map(Object.values(room.seats).map((s) => [s.seat_no, s]));
  const max = Math.max(size, ...byNo.keys());
  return Array.from({ length: max }, (_, i) => byNo.get(i + 1) ?? { seat_no: i + 1, placeholder: true as const });
}

export function remaining(exam: Exam | null, offset: number, now = nowSec()): number {
  if (!exam?.ends_at) return 0;
  return Math.max(0, Math.round(exam.ends_at - (now + offset)));
}

export function fmtClock(sec: number): string {
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}
```

`console/src/api.ts`:
```ts
import type { Exam, Results, SeatDetail, ServerMsg } from "./types";

let token = localStorage.getItem("tide_token") ?? "";
export const auth = {
  get token() { return token; },
  set(t: string) { token = t; localStorage.setItem("tide_token", t); },
  clear() { token = ""; localStorage.removeItem("tide_token"); },
};

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const r = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body && !isForm ? { "Content-Type": "application/json" } : {}) },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) { auth.clear(); location.reload(); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail);
  return r.json();
}

export const api = {
  async login(pin: string) {
    const r = await fetch("/api/teacher/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }) });
    if (!r.ok) throw new Error("Wrong PIN");
    auth.set((await r.json()).token);
  },
  catalog: () => req<{ apps: string[]; presets: Record<string, string[]> }>("GET", "/api/teacher/catalog"),
  exam: () => req<{ exam: Exam | null; files: { name: string; set: string }[] }>("GET", "/api/teacher/exam"),
  createExam: (title: string, duration_min: number, apps: string[]) =>
    req<Exam>("POST", "/api/teacher/exams", { title, duration_min, apps }),
  upload: (examId: number, setName: string, file: File) => {
    const f = new FormData(); f.append("set_name", setName); f.append("file", file);
    return req("POST", `/api/teacher/exams/${examId}/files`, f);
  },
  start: () => req<Exam>("POST", "/api/teacher/start"),
  extend: (minutes: number, seat_id?: number) => req("POST", "/api/teacher/extend", { minutes, seat_id }),
  notice: (text: string) => req("POST", "/api/teacher/notice", { text }),
  warn: (seatId: number) => req("POST", `/api/teacher/seats/${seatId}/warn`, {}),
  forceSubmit: (seatId: number) => req("POST", `/api/teacher/seats/${seatId}/force-submit`),
  seat: (seatId: number) => req<SeatDetail>("GET", `/api/teacher/seats/${seatId}`),
  review: (flagId: number, status: "dismissed" | "confirmed") => req("PATCH", `/api/teacher/flags/${flagId}`, { status }),
  results: () => req<Results>("GET", "/api/teacher/results"),
  simulate: (seat_no: number, kind: string) => req("POST", "/api/teacher/simulate", { seat_no, kind }),
  shotUrl: (flagId: number) => `/api/teacher/shots/${flagId}?token=${token}`,
  csvUrl: () => `/api/teacher/results.csv?token=${token}`,
  submissionUrl: (seatId: number) => `/api/teacher/submissions/${seatId}?token=${token}`,
};

export function connect(onMsg: (m: ServerMsg) => void): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/console?token=${token}`);
    ws.onmessage = (e) => onMsg(JSON.parse(e.data));
    ws.onclose = () => { onMsg({ t: "connected", value: false }); if (!stopped) setTimeout(open, 1500); };
  };
  open();
  return () => { stopped = true; ws?.close(); };
}
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd console && npm test`
Expected: 6 passed

- [x] **Step 6: Commit**

```bash
git add console
git commit -m "feat(console): scaffold, types, API client, room state"
```

### Task 22: Shell, login, Setup and Lobby

**Files:**
- Create: `console/src/main.tsx`, `console/src/App.tsx`, `console/src/components/TopBar.tsx`, `console/src/components/SeatGrid.tsx`, `console/src/pages/Login.tsx`, `console/src/pages/Setup.tsx`, `console/src/pages/Lobby.tsx`

**Interfaces:**
- Produces: `type Page = "setup" | "lobby" | "live" | "results"`; `<TopBar room page onPage>{right-side controls}</TopBar>`; `<SeatGrid room mode="lobby"|"live" filter? onOpen?>`; `<Setup onCreated>`, `<Lobby room onStarted>`

- [x] **Step 1: Implement**

`console/src/main.tsx`:
```tsx
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<App />);
```

`console/src/App.tsx`:
```tsx
import { useEffect, useReducer, useState } from "react";
import { auth, connect } from "./api";
import { emptyRoom, reduce } from "./state";
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Lobby from "./pages/Lobby";
import Live from "./pages/Live";
import Results from "./pages/Results";
import SeatDrawer from "./components/SeatDrawer";

export type Page = "setup" | "lobby" | "live" | "results";

function pageFor(state?: string): Page {
  return state === "lobby" ? "lobby" : state === "live" ? "live" : state === "ended" ? "results" : "setup";
}

export default function App() {
  const [authed, setAuthed] = useState(Boolean(auth.token));
  const [room, dispatch] = useReducer(reduce, emptyRoom);
  const [page, setPage] = useState<Page | null>(null);
  const [drawer, setDrawer] = useState<number | null>(null);

  useEffect(() => (authed ? connect(dispatch) : undefined), [authed]);
  useEffect(() => { if (room.connected && page === null) setPage(pageFor(room.exam?.state)); }, [room.connected, room.exam, page]);
  useEffect(() => { if (room.exam?.state === "live" && page === "lobby") setPage("live"); }, [room.exam?.state, page]);

  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  const p = page ?? "setup";
  const common = { room, page: p, onPage: setPage, onOpen: setDrawer };
  return (
    <>
      {p === "setup" && <Setup {...common} onCreated={() => setPage("lobby")} />}
      {p === "lobby" && <Lobby {...common} />}
      {p === "live" && <Live {...common} />}
      {p === "results" && <Results {...common} />}
      <SeatDrawer seatId={drawer} room={room} onClose={() => setDrawer(null)} />
    </>
  );
}
```

`console/src/components/TopBar.tsx`:
```tsx
import type { ReactNode } from "react";
import type { Page } from "../App";
import type { Room } from "../types";

const STEPS: Page[] = ["setup", "lobby", "live", "results"];
const LABEL: Record<Page, string> = { setup: "Setup", lobby: "Lobby", live: "Live", results: "Results" };

export default function TopBar({ room, page, onPage, children }:
  { room: Room; page: Page; onPage: (p: Page) => void; children?: ReactNode }) {
  const jev = room.mode === "jev";
  return (
    <header className="topbar">
      <div className="logo"><img src="/logo.svg" width={26} height={26} alt="" />Tide</div>
      {room.exam && <div className="exam-name">{room.exam.title}</div>}
      <div className="steps">
        {STEPS.map((s) => <button key={s} className={s === page ? "on" : ""} onClick={() => onPage(s)}>{LABEL[s]}</button>)}
      </div>
      <div className="spacer" />
      {!room.connected && <span className="chip warnchip"><span className="dot" />Reconnecting…</span>}
      <span className={`chip ${jev ? "" : "warnchip"}`}><span className="dot" />{jev ? "Jev live" : "Offline heuristics"}</span>
      {children}
    </header>
  );
}
```

`console/src/components/SeatGrid.tsx`:
```tsx
import { seatsGrid } from "../state";
import type { Room, Seat } from "../types";

function lobbyNote(s: Seat): string {
  if (s.state === "blocked") return "Internet on";
  if (s.preflight.extensions?.length) return `${s.preflight.extensions[0].replace("GitHub ", "")} found`;
  if (s.state === "lobby") return "Checking…";
  return "Ready";
}

export default function SeatGrid({ room, mode, filter = "all", onOpen }:
  { room: Room; mode: "lobby" | "live"; filter?: string; onOpen?: (id: number) => void }) {
  return (
    <div className="seats">
      {seatsGrid(room).map((s) => {
        if ("placeholder" in s)
          return <div key={`p${s.seat_no}`} className="seat placeholder"><span className="no">{String(s.seat_no).padStart(2, "0")}</span></div>;
        const cls = ["seat", s.status, !s.simulated ? "real" : "", filter !== "all" && s.status !== filter ? "dim" : ""].join(" ");
        return (
          <div key={s.id} className={cls} onClick={() => onOpen?.(s.id)}>
            <span className="no">{String(s.seat_no).padStart(2, "0")}</span>
            <span className="roll">{s.roll.slice(-3)}</span>
            {mode === "live" && s.flags > 0 && <span className="badge">{s.flags}</span>}
            <span className="now">{mode === "lobby" ? lobbyNote(s) : s.status === "done" ? "Submitted" : s.fg_app}</span>
          </div>
        );
      })}
    </div>
  );
}
```

`console/src/pages/Login.tsx`:
```tsx
import { useState } from "react";
import { api } from "../api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  return (
    <form className="card login" onSubmit={async (e) => {
      e.preventDefault();
      try { await api.login(pin); onDone(); } catch { setErr("Wrong PIN"); }
    }}>
      <div className="logo"><img src="/logo.svg" width={26} height={26} alt="" />Tide</div>
      <label className="lbl">Teacher PIN</label>
      <input className="input mono" autoFocus inputMode="numeric" value={pin} onChange={(e) => setPin(e.target.value)} />
      {err && <div style={{ color: "var(--crit)" }}>{err}</div>}
      <button className="btn primary lg">Open console</button>
    </form>
  );
}
```

`console/src/pages/Setup.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import TopBar from "../components/TopBar";
import type { Page } from "../App";
import type { Room } from "../types";

const ICON: Record<string, [string, string]> = {
  "VS Code": ["#0078D4", "VS"], CodeBlocks: ["#C2410C", "CB"], Terminal: ["#334155", ">_"], Explorer: ["#F5B400", "E"],
  Wireshark: ["#1679A7", "W"], VMware: ["#6D28D9", "VM"], Notepad: ["#0EA5E9", "N"],
};

export default function Setup({ room, page, onPage, onCreated }:
  { room: Room; page: Page; onPage: (p: Page) => void; onCreated: () => void; onOpen: (id: number) => void }) {
  const [title, setTitle] = useState("CN Lab Test");
  const [minutes, setMinutes] = useState(90);
  const [catalog, setCatalog] = useState<{ apps: string[]; presets: Record<string, string[]> } | null>(null);
  const [preset, setPreset] = useState("networking");
  const [apps, setApps] = useState<Set<string>>(new Set());
  const [files, setFiles] = useState<{ A: File[]; B: File[] }>({ A: [], B: [] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { api.catalog().then((c) => { setCatalog(c); setApps(new Set(c.presets.networking)); }); }, []);
  const choose = (p: string) => { setPreset(p); if (catalog?.presets[p]) setApps(new Set(catalog.presets[p])); };
  const toggle = (a: string) => { const n = new Set(apps); n.has(a) ? n.delete(a) : n.add(a); setApps(n); setPreset("custom"); };

  async function create() {
    setBusy(true); setErr("");
    try {
      const exam = await api.createExam(title, minutes, [...apps]);
      for (const s of ["A", "B"] as const) for (const f of files[s]) await api.upload(exam.id, s, f);
      onCreated();
    } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  }

  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage} />
      <div className="card setup">
        <h1>New lab test</h1>
        <div className="sub">Questions stay here until you press Start.</div>
        <div className="row">
          <div><label className="lbl">Title</label><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div><label className="lbl">Duration</label>
            <div className="stepper"><button onClick={() => setMinutes(Math.max(5, minutes - 5))}>−</button>
              <div>{minutes} min</div><button onClick={() => setMinutes(Math.min(300, minutes + 5))}>+</button></div></div>
        </div>
        <hr className="sep" />
        <label className="lbl">Question sets</label>
        <div className="sets">
          {(["A", "B"] as const).map((s) => (
            <label key={s} className="drop">
              <div className="hd"><h2>Set {s}</h2><span className="tag">{s === "A" ? "Odd seats · 1, 3, 5…" : "Even seats · 2, 4, 6…"}</span></div>
              {files[s].map((f) => <div key={f.name} className="file">{f.name}</div>)}
              <span className="addfile">+ Add files</span>
              <input type="file" multiple hidden onChange={(e) => setFiles({ ...files, [s]: [...files[s], ...Array.from(e.target.files ?? [])] })} />
            </label>
          ))}
        </div>
        <hr className="sep" />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <label className="lbl" style={{ margin: 0 }}>Allowed apps</label>
          <div className="seg">{["networking", "programming", "custom"].map((p) =>
            <button key={p} className={preset === p ? "on" : ""} onClick={() => choose(p)}>{p[0].toUpperCase() + p.slice(1)}</button>)}</div>
        </div>
        <div className="apps">{catalog?.apps.map((a) => (
          <span key={a} className={`app ${apps.has(a) ? "" : "off"}`} onClick={() => toggle(a)}>
            <span className="ic" style={{ background: ICON[a]?.[0] ?? "#64748B" }}>{ICON[a]?.[1] ?? a[0]}</span>{a}</span>))}</div>
        <div className="blocked"><div><b>Always blocked:</b> AI assistants, messengers, email, remote desktop, internet.{" "}
          <span style={{ opacity: 0.7 }}>Browsers only for local files. Unknown apps are checked by Jev.</span></div></div>
        {err && <div style={{ color: "var(--crit)", marginTop: 12 }}>{err}</div>}
        <div className="setup-foot"><button className="btn primary lg" disabled={busy || !title} onClick={create}>
          {busy ? "Creating…" : "Create & open lobby"}</button></div>
      </div>
    </section>
  );
}
```

`console/src/pages/Lobby.tsx`:
```tsx
import { api } from "../api";
import SeatGrid from "../components/SeatGrid";
import TopBar from "../components/TopBar";
import type { Page } from "../App";
import type { Room } from "../types";

export default function Lobby({ room, page, onPage, onOpen }:
  { room: Room; page: Page; onPage: (p: Page) => void; onOpen: (id: number) => void }) {
  const seats = Object.values(room.seats);
  const joined = seats.filter((s) => s.state !== "lobby").length;
  const ready = seats.filter((s) => s.state === "ready").length;
  const exam = room.exam;
  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage} />
      <div className="page lobby">
        <div className="card joincard">
          <div className="sub">Join code</div>
          <div className="code">{exam?.join_code ?? "——————"}</div>
          <div className="sub mono" style={{ fontSize: 12, marginTop: -10 }}>Students: open Tide, enter this code</div>
          <hr className="sep" style={{ margin: "4px 0" }} />
          <div className="joined">{joined}<small> / 60</small></div>
          <div className="bar"><i style={{ width: `${Math.min(100, (joined / 60) * 100)}%` }} /></div>
          <div className="legend">
            <span><i style={{ background: "var(--ok)" }} />Ready</span><span><i style={{ background: "var(--warn)" }} />Check</span>
            <span><i style={{ background: "var(--crit)" }} />Internet</span><span><i style={{ border: "1.5px dashed #C2C9D2" }} />Waiting</span>
          </div>
          <button className="btn primary lg" style={{ justifyContent: "center" }} disabled={!exam || exam.state !== "lobby" || ready === 0}
            onClick={() => api.start()}>Start exam · {Math.round((exam?.duration_s ?? 0) / 60)} min</button>
          <div className="sub" style={{ fontSize: 12 }}>Red seats won't receive questions.</div>
        </div>
        <div className="card grid-card">
          <div className="grid-head"><h2>Seats</h2><span className="sub">· pre-flight</span></div>
          <SeatGrid room={room} mode="lobby" onOpen={onOpen} />
        </div>
      </div>
    </section>
  );
}
```

- [x] **Step 2: Type-check**

Run: `cd console && npx tsc --noEmit`
Expected: errors only for the missing `Live`, `Results`, `SeatDrawer` modules (built in Tasks 23–24). No other errors.

- [x] **Step 3: Commit**

```bash
git add console
git commit -m "feat(console): shell, login, setup and lobby"
```

### Task 23: Live room — grid, alert feed, clock, controls

**Files:**
- Create: `console/src/components/AlertFeed.tsx`, `console/src/pages/Live.tsx`

**Interfaces:**
- Consumes: `openAlerts`, `counts`, `remaining`, `fmtClock`, `api.extend/notice/simulate`
- Produces: `<AlertFeed room onOpen>`, `<Live room page onPage onOpen>`

- [x] **Step 1: Implement**

`console/src/components/AlertFeed.tsx`:
```tsx
import { openAlerts } from "../state";
import type { Room } from "../types";

const SEV_CLASS = { critical: "crit", high: "crit", medium: "warn", info: "off" } as const;
const time = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

export default function AlertFeed({ room, onOpen }: { room: Room; onOpen: (seatId: number) => void }) {
  const alerts = openAlerts(room);
  return (
    <div className="card feed">
      <div className="feed-hd"><h2>Alerts</h2><span className="sub">· {alerts.length} open</span></div>
      <div className="feed-list">
        {alerts.map((a) => (
          <div key={a.id} className={`alert ${a.kind === "agent_offline" ? "off" : SEV_CLASS[a.severity]}`} onClick={() => onOpen(a.seat_id)}>
            <div className="sico">{String(a.seat_no).padStart(2, "0")}</div>
            <div>
              <div className="t">{a.title}</div>
              <div className="m">PC-{String(a.seat_no).padStart(2, "0")}
                {a.source === "jev" && <span className="src jev">Jev {a.confidence?.toFixed(2)}</span>}
                {a.source === "rule" && <span className="src rule">Rule</span>}
                {(a.action === "close_tab" || a.action === "kill") && <span className="acted">Auto-closed</span>}
              </div>
            </div>
            <time>{time(a.ts)}</time>
          </div>
        ))}
        {alerts.length === 0 && <div className="sub" style={{ padding: 18 }}>All quiet.</div>}
      </div>
    </div>
  );
}
```

`console/src/pages/Live.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import AlertFeed from "../components/AlertFeed";
import SeatGrid from "../components/SeatGrid";
import TopBar from "../components/TopBar";
import { counts, fmtClock, remaining } from "../state";
import type { Page } from "../App";
import type { Room } from "../types";

const SIM = [["ai_site", "ChatGPT closed"], ["jev_ai", "Jev: AI site"], ["internet", "Internet on"],
  ["old_code", "Old code reused"], ["usb", "USB drive"]] as const;

export default function Live({ room, page, onPage, onOpen }:
  { room: Room; page: Page; onPage: (p: Page) => void; onOpen: (id: number) => void }) {
  const [, tick] = useState(0);
  const [filter, setFilter] = useState("all");
  const [menu, setMenu] = useState(false);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  const c = counts(room);
  const real = Object.values(room.seats).find((s) => !s.simulated);
  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage}>
        <div className="clock">{fmtClock(remaining(room.exam, room.clockOffset))}</div>
        <button className="btn" onClick={() => api.extend(5)}>+ 5 min</button>
        <button className="btn" onClick={() => { const t = prompt("Notice to all students"); if (t) api.notice(t); }}>Notice</button>
        <div className="menu">
          <button className="btn" onClick={() => setMenu(!menu)}>Simulate</button>
          {menu && <div className="menu-list">{SIM.map(([k, label]) => (
            <button key={k} onClick={() => { setMenu(false); api.simulate(real?.seat_no ?? 7, k); }}>{label} · PC-{String(real?.seat_no ?? 7).padStart(2, "0")}</button>))}</div>}
        </div>
      </TopBar>
      <div className="page">
        <div className="summary">
          {([["ok", "Working", "var(--ok)"], ["warn", "Review", "var(--warn)"], ["crit", "Alert", "var(--crit)"], ["off", "Offline", "var(--off)"]] as const)
            .map(([k, label, color]) => (
              <div key={k} className="card stat"><div className="sw" style={{ background: color }} />
                <div><div className="n">{c[k]}</div><div className="l">{label}</div></div></div>))}
        </div>
        <div className="live">
          <div className="card grid-card">
            <div className="grid-head"><h2>Lab</h2><span className="sub">· {Object.keys(room.seats).length} seats</span>
              <div className="spacer" />
              <div className="filters">{([["all", "All"], ["crit", "Alert"], ["warn", "Review"], ["off", "Offline"]] as const).map(([f, label]) => (
                <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>{label}</button>))}</div>
            </div>
            <SeatGrid room={room} mode="live" filter={filter} onOpen={onOpen} />
          </div>
          <AlertFeed room={room} onOpen={onOpen} />
        </div>
      </div>
    </section>
  );
}
```

- [x] **Step 2: Type-check**

Run: `cd console && npx tsc --noEmit`
Expected: only the `Results` and `SeatDrawer` import errors remain.

- [x] **Step 3: Commit**

```bash
git add console
git commit -m "feat(console): live room grid, alert feed, clock and controls"
```

### Task 24: Seat drawer and Results

**Files:**
- Create: `console/src/components/SeatDrawer.tsx`, `console/src/pages/Results.tsx`

**Interfaces:**
- Consumes: `api.seat/review/warn/extend/forceSubmit/shotUrl/results/csvUrl/submissionUrl`
- Produces: `<SeatDrawer seatId room onClose>` (reloads when that seat's flags or events change), `<Results room page onPage onOpen>`

- [x] **Step 1: Implement**

`console/src/components/SeatDrawer.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Room, SeatDetail, TimelineItem } from "../types";

const t = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
const DOT = { critical: "crit", high: "crit", medium: "warn", info: "info" } as const;
const STATUS = { ok: "Working", warn: "Review", crit: "Alert", off: "Offline", wait: "Waiting", done: "Submitted" } as const;

function Item({ i, reload }: { i: TimelineItem; reload: () => void }) {
  if (i.type === "event")
    return <div className={`ev ${i.kind === "start" || i.kind === "joined" ? "brand" : "info"}`}><div className="h"><time>{t(i.ts)}</time><span className="x">{i.text}</span></div></div>;
  const acted = i.action === "close_tab" || i.action === "kill";
  return (
    <div className={`ev ${DOT[i.severity]}`}>
      <div className="h"><time>{t(i.ts)}</time><span className="x">{i.title}</span></div>
      <div className="card">
        {i.has_shot && <div className="shot"><img src={api.shotUrl(i.id)} alt="screenshot" /></div>}
        {i.source === "jev" && i.confidence != null && (
          <div className="conf"><span className="src jev">Jev</span>{i.label}
            <div className="meter"><i style={{ width: `${i.confidence * 100}%` }} /></div><b>{i.confidence.toFixed(2)}</b></div>)}
        <div className="fl-act">
          {acted ? <span className="acted">Auto-closed</span> : <span className="src rule">{i.source === "jev" ? "Jev" : "Rule"}</span>}
          <span className="spacer" />
          {i.status === "open" ? <>
            <button className="btn" onClick={() => api.review(i.id, "dismissed").then(reload)}>Dismiss</button>
            <button className="btn danger" onClick={() => api.review(i.id, "confirmed").then(reload)}>Confirm</button>
          </> : <span className="sub">{i.status}</span>}
        </div>
      </div>
    </div>
  );
}

function Growth({ d }: { d: SeatDetail }) {
  const g = d.growth;
  if (g.length < 2) return <div className="sub">Not enough snapshots yet.</div>;
  const t0 = g[0].ts, t1 = g[g.length - 1].ts || t0 + 1, max = Math.max(...g.map((p) => p.lines), 1);
  const x = (ts: number) => ((ts - t0) / Math.max(1, t1 - t0)) * 500;
  const y = (n: number) => 160 - (n / max) * 140;
  const pts = g.map((p) => `${x(p.ts)},${y(p.lines)}`).join(" ");
  const bursts = d.timeline.filter((i) => i.type === "flag" && i.kind === "code_burst");
  return (
    <svg viewBox="0 0 500 170" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke="#0B7A83" strokeWidth={2.5} />
      {bursts.map((b) => <line key={b.id} x1={x(b.ts)} x2={x(b.ts)} y1={10} y2={165} stroke="#DC2626" strokeDasharray="4 4" />)}
    </svg>
  );
}

export default function SeatDrawer({ seatId, room, onClose }: { seatId: number | null; room: Room; onClose: () => void }) {
  const [d, setD] = useState<SeatDetail | null>(null);
  const [tab, setTab] = useState<"tl" | "code">("tl");
  const version = seatId ? Object.values(room.flags).filter((f) => f.seat_id === seatId).map((f) => `${f.id}${f.status}${f.has_shot}`).join()
    + (room.lastEvent?.seat_id === seatId ? room.lastEvent.id : "") : "";
  const reload = () => { if (seatId) api.seat(seatId).then(setD); };
  useEffect(() => { setD(null); setTab("tl"); }, [seatId]);
  useEffect(reload, [seatId, version]);
  const s = d?.seat;
  return (
    <>
      <div className={`scrim ${seatId ? "on" : ""}`} onClick={onClose} />
      <aside className={`drawer ${seatId ? "on" : ""}`}>
        {s && <>
          <div className="dr-hd">
            <div className="dr-title"><span className="big">PC-{String(s.seat_no).padStart(2, "0")}</span>
              <span className={`status-pill ${s.status === "off" ? "warn" : s.status}`}>{STATUS[s.status]}</span>
              <div className="spacer" /><button className="btn ghost" onClick={onClose}>✕</button></div>
            <div className="dr-meta"><span className="mono">{s.roll}</span><span>Set {s.set ?? "—"}</span><span>Now: {s.fg_app || "—"}</span></div>
            <div className="dr-actions">
              <button className="btn" onClick={() => api.warn(s.id)}>Warn</button>
              <button className="btn" onClick={() => api.extend(5, s.id)}>+ 5 min</button>
              <button className="btn danger" onClick={() => confirm("Force submit this seat?") && api.forceSubmit(s.id)}>Force submit</button>
            </div>
          </div>
          <div className="tabs">
            <button className={tab === "tl" ? "on" : ""} onClick={() => setTab("tl")}>Timeline</button>
            <button className={tab === "code" ? "on" : ""} onClick={() => setTab("code")}>Code</button>
          </div>
          <div className="dr-body">
            {tab === "tl" ? <div className="tl">{d!.timeline.map((i) => <Item key={`${i.type}${i.id}`} i={i} reload={reload} />)}</div> : <>
              <div className="card chart"><h2>Lines in exam folder</h2><Growth d={d!} /></div>
              <div className="files">{d!.files.map((f) => <div key={f.path} className="file">{f.path}<span className="spacer" /><span className="sub">{f.lines} lines</span></div>)}</div>
            </>}
          </div>
        </>}
      </aside>
    </>
  );
}
```

`console/src/pages/Results.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api } from "../api";
import TopBar from "../components/TopBar";
import type { Page } from "../App";
import type { Results as R, Room } from "../types";

export default function Results({ room, page, onPage, onOpen }:
  { room: Room; page: Page; onPage: (p: Page) => void; onOpen: (id: number) => void }) {
  const [r, setR] = useState<R | null>(null);
  useEffect(() => { api.results().then(setR); }, [room.flags]);
  const submitted = r?.rows.filter((x) => x.submitted_at).length ?? 0;
  const sev = (s: string) => (s === "medium" ? "warn" : "crit");
  return (
    <section>
      <TopBar room={room} page={page} onPage={onPage}>
        <span className="chip">{submitted}/{r?.rows.length ?? 0} submitted</span>
        <a className="btn primary" href={api.csvUrl()}>Export CSV</a>
      </TopBar>
      <div className="page results">
        <div className="card" style={{ overflow: "hidden" }}>
          <table>
            <thead><tr><th>Seat</th><th>Roll</th><th>Set</th><th>Submitted</th><th>Flags</th><th>Max match</th><th /></tr></thead>
            <tbody>{r?.rows.map((x) => (
              <tr key={x.seat_id} onClick={() => onOpen(x.seat_id)} style={{ cursor: "pointer" }}>
                <td><b>PC-{String(x.seat_no).padStart(2, "0")}</b></td><td className="mono">{x.roll}</td><td>{x.set ?? "—"}</td>
                <td>{x.submitted_at ? new Date(x.submitted_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td>
                <td><div className="fchips">{x.flags.length ? x.flags.map((f, i) => <span key={i} className={`fc ${sev(f.severity)}`}>{f.title}</span>) : <span className="sub">—</span>}</div></td>
                <td>{x.max_match != null ? <b style={{ color: x.max_match >= 80 ? "var(--crit)" : undefined }}>{x.max_match}%</b> : <span className="sub">—</span>}</td>
                <td>{x.submitted_at && <a className="btn ghost" onClick={(e) => e.stopPropagation()} href={api.submissionUrl(x.seat_id)}>Files</a>}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="card sim"><h2>Similar submissions</h2>
            {r?.pairs.map((p, i) => (
              <div key={i} className="pair"><b>PC-{String(p.a).padStart(2, "0")}</b>↔
                {p.b != null ? <b>PC-{String(p.b).padStart(2, "0")}</b> : <span className="mono" style={{ fontSize: 12 }}>{p.b_path}</span>}
                <span className={`pct ${p.pct >= 80 ? "hi" : ""}`}>{p.pct}%</span></div>))}
            {!r?.pairs.length && <span className="sub">None above 40%.</span>}
          </div>
          <div className="card sim"><h2>Flags this exam</h2>
            {r && Object.entries(r.flag_counts).map(([k, n]) => <div key={k} className="pair">{k}<span className="pct">{n}</span></div>)}
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [x] **Step 2: Type-check, test, build**

Run: `cd console && npx tsc --noEmit && npm test && npm run build`
Expected: no type errors, 6 tests pass, `console/dist/index.html` exists.

- [x] **Step 3: See it against the real server**

Run: `tide-server --demo` (after the build it serves `console/dist`), open http://localhost:8765, PIN `2468`.
Expected: the Lobby shows 57/60 with seat 19 red and 45 amber, then 58–60 join within ~12 s. Press Start: Live shows the grid; scripted alerts appear at +20 s, +35 s…; clicking seat 14 opens the drawer with its timeline; **Simulate → Jev: AI site** on seat 7 adds a "Jev 0.96" alert. Compare each screen side by side with `design/mock-ui.html`.

- [x] **Step 4: Commit**

```bash
git add console
git commit -m "feat(console): seat drawer with evidence and results with similarity and CSV"
```

---

## Phase 5 — End-to-end rehearsal

### Task 25: Rehearse the demo and ship

**Files:**
- Modify: `README.md` (status line → "Demo build working"), `docs/DEMO.md` if any step changed during rehearsal

- [x] **Step 1: Single device (any OS, fake PC)** — follow `docs/DEVELOPMENT.md` §4. Run every command in the fake-PC list and confirm each console reaction. **Done** (commit `38de75c`): every scripted cheat was flagged correctly against the real in-repo server with live Jev.
- [ ] **Step 2: Two Windows PCs** — follow `docs/SETUP_TWO_PCS.md` start to finish on the real hardware, then run the `docs/DEMO.md` script twice. Time it: under 5 minutes. **Open** — needs the actual two-laptop hardware.
- [x] **Step 3: Acceptance checklist** — tick all 10 criteria in `docs/specs/2026-09-28-tide-design.md` §5. Note any failure as an issue, not a silent skip. **8/10 confirmed on the single device; #4 and #8 need real Windows hardware — see spec §5.**
- [x] **Step 4: Full test run**

Run: `pytest common/tests server/tests && (cd agent && pytest tests) && (cd console && npm test)`
Expected: all green.

- [x] **Step 5: Commit** — done as `38de75c`.

```bash
git add -A
git commit -m "chore: demo rehearsal fixes"
```
