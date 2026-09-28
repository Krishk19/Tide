# Tide — Architecture

**Tide = Test Integrity in Developer Environments.** It keeps lab tests honest while students use real developer tools.

> Read this once and you should be able to run the demo, explain every box on the diagram,
> and answer a judge's "but what if the student…" question.

---

## 1. The problem, from first principles

Lab tests happen in a room of ~60 Windows PCs. Students legitimately use **real desktop tools**:
VS Code, CodeBlocks, a terminal, Windows Explorer, Wireshark, VMware.

Today's only control is "unplug the LAN cable". Students beat it by:

| # | How they cheat today | Why current practice fails |
|---|---|---|
| 1 | Open ChatGPT / Claude / Gemini / Copilot | Nobody can watch 60 screens |
| 2 | Secretly re-plug LAN, join Wi-Fi or a phone hotspot | Invisible from the front of the room |
| 3 | Download the test from Google Classroom, then get answers before unplugging | The questions leave the teacher's control too early |
| 4 | Open old saved code / solutions already on the PC or a USB | Files look like normal work |
| 5 | Mail code to themselves earlier, open it during the test | Needs internet — see #2 |
| 6 | Copy from a neighbour (same set) | Odd/even sets help, but nothing checks it |

**Conclusion:** we can't lock students inside our own editor (they need their real tools), and
we can't watch 60 screens by eye. So Tide **watches the real desktop** from a small agent on each
PC, **controls when questions exist**, and gives the invigilator **one screen that shows only
what matters**.

### Design principles

1. **Watch the real desktop, don't replace it.** Students keep VS Code, Wireshark, etc.
2. **Questions only exist inside Tide, and only after the PC is confirmed offline.**
3. **Act instantly on the obvious, ask AI about the ambiguous, let a human judge the rest.**
4. **Evidence over accusation.** Every flag carries what, when, confidence, and a screenshot.
5. **One glance.** Green / amber / red seat tiles. Minimal text.

---

## 2. System overview

```
 STUDENT PC  (Windows 10/11)                           TEACHER LAPTOP
 ┌───────────────────────────────┐                    ┌───────────────────────────────────┐
 │  Tide Agent  (tide-agent.exe) │                    │  Tide Server (FastAPI + SQLite)   │
 │                               │   WebSocket (LAN)  │                                   │
 │  Watchers ──► Local rules ──┐ │ ─── signals ─────► │  Seat registry & pairing          │
 │   window / browser URL      │ │ ─── flags+proof ─► │  Classifier pipeline              │
 │   processes / extensions    │ │                    │    rules ─► cache ─► Jev ─────────┼──► Jev API
 │   network / LAN peers       │ │ ◄── actions ────── │  Decision engine (act/flag/log)   │   (cloud,
 │   files / USB / clipboard   │ │ ◄── questions ──── │  Exam clock  (single source)      │    teacher's
 │                             ▼ │ ◄── timer/notice ─ │  Question release (odd/even sets) │    internet)
 │  Enforcer: kill app, close tab│ ─── snapshots ───► │  Snapshots, submissions,          │
 │  Evidence: screenshot         │ ─── submission ──► │  similarity, report export        │
 │  UI: join, timer pill, block  │                    │                                   │
 └───────────────────────────────┘                    └───────────────┬───────────────────┘
                                                                      │ WebSocket
                                                          ┌───────────▼───────────┐
                                                          │ Teacher Console (React)│
                                                          │ seat grid · flag feed  │
                                                          │ student timeline · report│
                                                          └────────────────────────┘
```

Three deliverables:

| Component | Tech | Runs on | Job |
|---|---|---|---|
| **Tide Agent** | Python 3.12, `pywin32`, `psutil`, `uiautomation`, `mss`, `pywebview`; shipped as one `.exe` via PyInstaller | Every student PC | See, act, collect evidence, deliver questions, collect answers |
| **Tide Server** | Python 3.12, FastAPI, WebSockets, SQLModel/SQLite | Teacher laptop | Pair seats, classify, decide, keep the clock, store everything |
| **Teacher Console** | React + Vite + TypeScript, served by the server | Teacher's browser | Create exam, watch the room, review evidence, export |

### Why not Electron?

The old version was an Electron kiosk with its own editor. It was the wrong shape:
- Students **must** use native tools, so a kiosk editor is useless in our labs.
- Anti-cheat needs **OS-level signals** (foreground window, process list, network adapters,
  browser address bar, clipboard, USB). Python + `pywin32`/`uiautomation` gets these in a few
  lines; Node needs fragile native add-ons.
- Electron is ~150 MB per install. The agent is ~25 MB.

The agent's small UI (join window, timer pill, block overlay) uses **pywebview**, which renders
HTML with the Edge WebView2 already built into Windows 10/11. So we get web-quality UI without
bundling Chromium.

---

## 3. Exam lifecycle

```
 SETUP ──► LOBBY / PRE-FLIGHT ──► LIVE ──► SUBMIT ──► REVIEW
 teacher    agents pair, check     questions  auto at     flags, proof,
 uploads    offline, extensions,   released,  time-up or  timeline,
 sets       file inventory         watching   by student  similarity, CSV
```

### 3.1 Setup (teacher console)
- Title, duration.
- **Question sets**: upload files for Set A (odd seats) and Set B (even seats). One set is fine.
- **App policy**: pick a preset ("Networking lab", "Programming lab"), toggle apps on/off.
  The policy is a list of allowed apps + a built-in deny list (AI apps, messengers, remote tools).
- Server generates a **6-character join code**.

### 3.2 Lobby and pre-flight (agent)
1. Student launches `tide-agent.exe`. It finds the server via **UDP broadcast** on the LAN
   (fallback: type the IP).
2. Student enters **join code + roll number**. Seat number comes from the PC hostname
   (`LAB3-PC07` → seat 7). In the demo, it is typed.
3. Server returns a **seat token** (random 256-bit). Every later message is authenticated with it.
4. Agent runs **pre-flight** and reports it:

| Check | Pass condition | If it fails |
|---|---|---|
| Internet | Connectivity probe fails (see §4.3) | Seat stays red: "Disconnect internet". **Cannot receive questions.** |
| AI extensions | No Copilot/Codeium/Cline/Continue/Tabnine/… in VS Code | Seat amber, flag raised. Allowed to continue (they can't work offline anyway). |
| Denied apps running | None of the deny list running | Agent closes them, notes it |
| File inventory | Always passes | Records fingerprints of source files already on disk (see §4.4) |

### 3.3 Start and question release
- Teacher presses **Start**. Server sends **only green seats** their set:
  seat number odd → Set A, even → Set B.
- Files land in `C:\Exam\<roll>\` along with a `README.txt` with instructions.
- **Why this closes cheat #3:** the questions never exist on Classroom or email. A leaked join
  code gets you nothing; questions go only to paired, offline, checked seats, at Start.

### 3.4 Clock
- The **server is the only clock.** At pairing the agent measures its offset
  (`server_now − local_now`, half round-trip corrected).
- Start sends a single absolute `ends_at`. The agent renders the countdown locally.
- Teacher can **extend time** for one seat or all; a new `ends_at` is pushed instantly.
- A restarted/reconnected agent receives the current `ends_at` in its `welcome` message.

### 3.5 During the exam
- Watchers run continuously (§4). Rules run locally; ambiguous signals go to the server.
- Every **30 s** the agent snapshots text files in `C:\Exam\<roll>\` (only changed files are sent).
  This powers the timeline and "code burst" detection.
- Heartbeat every **3 s**. Missing for **10 s** → seat turns grey "Agent offline" + flag.

### 3.6 Submit
- Student presses **Submit** in the timer pill, or time runs out → agent zips
  `C:\Exam\<roll>\` and uploads it. The seat is locked; watchers stop; agent exits.

### 3.7 Review
- Per student: timeline of everything, flags with screenshots, code growth chart.
- Room level: flag summary, **similarity pairs** across submissions, CSV/PDF export.
- Teacher marks each flag **dismissed** or **confirmed**. Flags are never deleted.

---

## 4. Detection — what we watch and how

Every watcher produces a **signal**: `{kind, data, ts}`. Signals go through the decision
pipeline (§5).

### 4.1 Foreground window + browser URL (every 500 ms)
- `GetForegroundWindow` → window title, owning PID → process name + exe path (`psutil`).
- If the process is a browser (`chrome`, `msedge`, `firefox`, `brave`, `opera`), read the
  **address bar** through Windows **UI Automation** (`uiautomation`), keeping just the host.
  Works in incognito, since the address bar is still an accessible control.
- Emits a signal only when (process, title, host) changes.
- **Catches:** ChatGPT, Claude, Gemini, Copilot web, Perplexity, Poe, DeepSeek, Stack Overflow,
  Gmail, WhatsApp Web, Drive, etc.

### 4.2 Processes and extensions (every 2 s)
- `psutil.process_iter` → new processes since last scan, with exe path, file description, and
  whether the binary is signed by a known vendor.
- **Deny list examples:** `ChatGPT.exe`, `Claude.exe`, `Copilot` app, `Cursor.exe`,
  `Windsurf.exe`, `ollama.exe`, `LM Studio.exe`, `WhatsApp.exe`, `Telegram.exe`, `Discord.exe`,
  `AnyDesk.exe`, `TeamViewer.exe`, `Outlook` (new/classic).
- **Renamed binaries:** rules match on file description and original filename from the PE
  version info, not only the exe name. Anything unknown goes to Jev.
- **VS Code extensions** (pre-flight + every 60 s): scan `%USERPROFILE%\.vscode\extensions`
  for `github.copilot*`, `codeium.*`, `continue.*`, `saoudrizwan.claude-dev` (Cline),
  `tabnine.*`, `supermaven.*`, `amazonwebservices.amazon-q-*`.

### 4.3 Network (every 2 s; probe every 5 s)
- **Adapter changes:** `psutil.net_if_stats/net_if_addrs`. A Wi-Fi adapter coming up, a new
  adapter (USB tethering, phone hotspot), or a new default gateway → signal.
- **Internet probe,** the same idea Windows uses for its "No internet" icon:
  HTTP GET `http://www.msftconnecttest.com/connecttest.txt` (expects `Microsoft Connect Test`)
  **and** a TCP connect to `1.1.1.1:443`. Either succeeding = internet reachable.
  Timeouts are 1.5 s, so an offline PC costs nothing.
- **LAN peers:** `psutil.net_connections` → established connections to LAN IPs other than the
  Tide server (other students' PCs, shared folders) → signal for review. (Wireshark captures are
  passive and aren't connections, so they don't trigger this.)
- **Offline-safe:** if the agent can't reach the server (because the student switched networks),
  it **still enforces locally** (§5.1), buffers events to disk, and flushes them on reconnect.
  The server separately flags the gap.

### 4.4 Files, USB, clipboard
- **File inventory (pre-flight):** walk user folders + non-system drives for source/doc files
  (`.c .cpp .h .py .java .js .ts .sql .txt .md .pdf .docx .ipynb`), capped by count and size.
  For code files, store a **normalized fingerprint** (whitespace/comments stripped, then
  winnowing hashes of token n-grams).
- **During the exam:**
  - A window title references an inventoried file (VS Code / CodeBlocks show the filename in
    the title) → **"Pre-exam file opened"**.
  - A file appears or changes in `C:\Exam\<roll>\` whose fingerprint overlaps an inventoried file
    above threshold → **"Old code reused"**, with the source path.
- **USB:** `psutil.disk_partitions` → new removable drive → flag (high).
- **Clipboard** (every 1 s): text ≥ 200 chars that didn't come from `C:\Exam` files → flag with
  a 120-char preview. If it matches an inventoried fingerprint → high.

### 4.5 Code bursts (server side)
- Between two 30 s snapshots, if the exam folder grows by **≥ 40 lines** → "Code burst" (medium).
  Typing 40 lines of working code in 30 s is not normal; pasting is.

### 4.6 Evidence
- On any flag of severity ≥ medium, the agent grabs a **screenshot** (`mss`, primary monitor,
  downscaled to 1280 px JPEG, ~120 KB) and attaches it to the flag.

---

## 5. Decision pipeline — act, flag, or log

```
 signal ──► (A) Local rules in agent ──match──► ACT now + flag (critical)
                 │ no match / not certain
                 ▼
            (B) Server rules ──match──► flag / act
                 │ no match
                 ▼
            (C) Cache (same process/title/host seen before?) ──hit──► reuse verdict
                 │ miss
                 ▼
            (D) Jev classifier ──► label + confidence ──► thresholds ──► act / flag / log
                 │ Jev unreachable
                 ▼
            (E) Offline heuristics (keywords) ──► flag for review (never auto-act)
```

### 5.1 Local rules (agent, instant, work offline)
The policy (allow list + deny list + domain deny list) is sent to the agent at pairing.
Certain matches are acted on immediately, with no round-trip:

| Match | Action |
|---|---|
| Browser host on the deny list (`chatgpt.com`, `claude.ai`, `gemini.google.com`, `copilot.microsoft.com`, `perplexity.ai`, `chat.deepseek.com`, Gmail, WhatsApp Web, Drive, Classroom, …). `poe.com` is left off on purpose, so the demo shows Jev catching an unlisted site | **Close tab** + block overlay + flag |
| Process on deny list | **Kill process** + block overlay + flag |
| Internet reachable | **Block overlay stays until offline** + flag (critical) |
| USB drive inserted | Flag (high), no action |

### 5.2 Jev — the AI classifier (server)
**What Jev is:** a decision model from TypeSafe AI (early access Sept 2026). You give it input
text and a fixed set of typed questions. It returns **a choice + probabilities + a confidence**,
with no generated text. We call it through **OpenRouter's Decisions API**
(`POST https://openrouter.ai/api/alpha/decisions`, model `~typesafe/jev-latest`, key in
`OPENROUTER_API_KEY`). Measured on our prompts: ~0.4 s per call, fractions of a cent, which is why
classifying every ambiguous event from 60 seats is affordable.

**Why Jev and not an LLM:** we need a decision from a fixed menu with a calibrated confidence
that we can threshold, not prose. LLM judges are slower, pricier, and their confidence isn't a
number you can safely automate on.

**What we send** (the only data that leaves the lab, and only from the teacher laptop):
```
Exam policy: allowed = VS Code, CodeBlocks, Terminal, Explorer, Wireshark, VMware.
Event: foreground window
  process: chrome.exe  (Google Chrome)
  title:   "Fast AI Chat - Poe"
  host:    poe.com
```
**Questions we ask:**
| Name | Type | Options |
|---|---|---|
| `activity` | choice | `allowed_tool`, `ai_assistant`, `communication`, `web_lookup`, `remote_or_file_share`, `other` |
| `violation` | yes/no probability | "Is this against the exam policy?" |

**Thresholds:**
| Condition | Result |
|---|---|
| `activity ∈ {ai_assistant, communication, remote_or_file_share}` and confidence ≥ **0.90** | **Auto-act** (close/kill) + critical flag |
| `violation` ≥ 0.60 | Flag for review (amber) |
| otherwise | Log only (visible in timeline) |

Tide's confidence is the **probability Jev gives the chosen label** (Jev's own `confidence` value is
kept alongside as evidence). Verdicts are **cached** per `(browser, host)` or `(process, title pattern)`,
so the same window is classified once per exam. Only Jev answers are cached, so a Jev outage heals itself.

Measured with the real API:

| Window | Jev label | p | Result |
|---|---|---|---|
| Chrome · `poe.com` "Fast AI Chat - Poe" | ai_assistant | 0.97 | auto-closed |
| `notegpt.exe` "NoteGPT - AI Notes" | ai_assistant | 0.99 | auto-killed |
| Edge · geeksforgeeks.org | web_lookup | 0.97 | high flag (review) |
| VS Code `main.c` | allowed_tool | 1.00 | nothing |
| Calculator | other | 0.99 | nothing |

The Jev client lives in one file (`server/tide_server/classify/jev.py`). With no
`OPENROUTER_API_KEY`, the server uses **offline heuristics** (keywords, confidence capped at 0.70,
so they never auto-act) and says so in the console header. The demo never breaks.

### 5.3 Severity → seat colour
| Severity | Examples | Seat tile |
|---|---|---|
| critical | Internet reachable, AI site/app (auto-acted), agent killed | **Red** |
| high | USB, old code reused, clipboard match, Jev violation ≥ 0.8 | **Red** |
| medium | Code burst, LAN peer connection, AI extension installed, Jev 0.6–0.8 | **Amber** |
| info | App switches, allowed tools, snapshots | Green (timeline only) |
| — | No heartbeat for 10 s | **Grey** "offline" |

A seat's colour = its worst **open** flag. When the teacher dismisses the flag, the colour drops.

### 5.4 Enforcement mechanics
- **Close tab:** bring the browser window to the foreground, send `Ctrl+W` via `SendInput`,
  re-read the address bar after 300 ms; if the AI host is still there, **kill the browser**.
- **Kill app:** `psutil` terminate → kill after 1 s.
- **Block overlay:** full-screen topmost window, red, one line ("ChatGPT blocked — reported"),
  auto-dismisses after 4 s. For internet, it stays until the probe fails again.
- Every action is recorded on its flag (`action` + `result`), so the teacher sees
  "Auto-closed" with the time.

---

## 6. Protocol

One WebSocket per seat: `ws://<server>:8765/ws/agent`. JSON messages `{"t": type, ...}`.
First message must be `hello` with the seat token; otherwise the socket is closed.

**Agent → Server**
| `t` | Payload |
|---|---|
| `hello` | `token, agent_version, local_time` |
| `heartbeat` | `fg` (foreground process) |
| `preflight` | `internet, extensions[], denied_closed[], inventory_count` |
| `event` | `kind, data, ts` (allowed activity, timeline only) |
| `signal` | `kind, data, ts` (unknown, for the server pipeline) |
| `flag` | `ref, kind, severity, title, data, ts, action, result` (from local rules) |
| `evidence` | `ref` or `flag_id`, `jpeg_b64` |
| `snapshot` | `ts, files: [{path, text, sha}]` (changed files only; unchanged starter files never sent) |

**Server → Agent**
| `t` | Payload |
|---|---|
| `welcome` | `seat_no, roll, set, policy, server_time, exam_state, ends_at` |
| `start` | `set, files: [{name, b64}], ends_at` |
| `act` | `action: close_tab/kill/overlay, target, reason, flag_id` |
| `time` | `ends_at` |
| `notice` | `text` |
| `end` | `reason` (time / teacher): collect and submit now |

A bad token closes the socket with code `4401`.

**HTTP:** `POST /api/pair` (join code + roll + seat → token), `POST /api/submit` (zip,
token-authenticated), plus the teacher REST API under `/api/teacher/*`. The console gets live
updates on `ws://<server>:8765/ws/console`.

---

## 7. Data model (SQLite)

```
exam(id, title, duration_s, join_code, state[lobby|live|ended], started_at, ends_at, policy_json)
exam_file(id, exam_id, set_name['A'|'B'], name, data)
seat(id, exam_id, seat_no, roll, hostname, token_hash, set_name,
     state[lobby|ready|blocked|live|offline|submitted], resume_state, preflight_json,
     last_seen, ends_at_override, fg_app, simulated)
event(id, seat_id, ts, kind, data_json)                -- the timeline
flag(id, seat_id, ts, kind, severity, title, source[rule|jev|heuristic|server],
     label, confidence, data_json, action, screenshot, status[open|dismissed|confirmed],
     reviewed_at, ref)
snapshot(id, seat_id, ts, path, sha, text, line_count)
submission(id, seat_id, ts, file_name, auto)
```
The Jev verdict cache is in memory (one exam per server run).

---

## 8. Security model

| Threat | Demo | Production |
|---|---|---|
| Fake agent / forged flags for a classmate | Per-seat random token from pairing; required on every WS message and upload | + TLS with pinned server cert; agent binary signed |
| Student kills the agent | Heartbeat stops → seat grey + critical flag in 10 s | Agent runs as a **Windows service (SYSTEM)**; students aren't admins so they can't stop it. A per-session helper (needed to read windows, because services run in Session 0) is restarted by the service within 1 s |
| Student never starts the agent | Seat missing from grid; teacher sees 59/60 | Agent starts at login via service; hostname roster shows who is missing |
| Tampering with local rules | Rules are sent from the server; agent code is compiled into a PyInstaller exe | + integrity check of the binary hash in `hello` |
| Changing the PC clock | Server clock is authoritative | same |
| Teacher console access | Teacher PIN, console served only on the teacher laptop | Real accounts, per-lab isolation |
| Privacy | Agent runs only during an exam, exits after submit. Collects window titles, process names, hosts, exam folder, screenshots **only on flags**. Data stays on the teacher laptop; only window/app metadata of ambiguous events goes to Jev | Retention policy, consent notice at join |

---

## 9. Demo vs production

| Area | Demo (built) | Production (pitched) |
|---|---|---|
| Seats | 1 real laptop + **59 simulated seats** so the grid looks like a real lab | 60 real PCs |
| Agent install | Run `tide-agent.exe` | MSI via Group Policy / lab image, Windows service + session helper |
| Seat number | Typed | From hostname |
| Network | Ethernet cable between laptops (LAN); student Wi-Fi used for the "hotspot" cheat | Lab VLAN where the firewall allows only the Tide server; optional Windows Firewall lockdown pushed by the service |
| Teacher auth | PIN | Accounts, multiple labs and teachers at once |
| Jev | Live if key present, else offline heuristics | Live, with an on-prem fallback |
| Storage | SQLite on the teacher laptop | Same (60 seats is small), or Postgres for a department |
| Grading | Not included; teacher reviews files | Optional test-case runner in a sandbox |

---

## 10. Honest limitations (say these before a judge does)

- **User-mode software can't stop everything.** An admin student could stop the agent in the
  demo build. In production the service runs as SYSTEM and students aren't admins; if the agent
  goes silent, the seat turns grey within 10 s anyway, which is itself evidence.
- **Phones and second devices** are for physical invigilation (phones are collected). Tide makes
  the invigilator's job smaller by telling them *which* seat to walk to.
- **Inside a VM** (VMware), we see the VMware window, not the guest's browser. Mitigations: host
  internet detection still fires (NAT/bridged use the host adapters); the lab policy sets VMs to
  host-only networking; pre-flight can read `.vmx` files for NAT/bridged adapters.
- **A friend typing the answer for you** in the same room isn't a software problem.
- Tide **flags and stops obvious violations; it never grades or punishes.** A human confirms
  every penalty.

---

## 11. Repository layout (target)

```
Tide/
├── common/           tide_common: protocol, policy (allow/deny lists), rules, fingerprints
├── agent/            Tide Agent (Python → tide-agent.exe)
│   └── tide_agent/   watchers.py, engine.py, enforcer.py, link.py, preflight.py, inventory.py,
│                     win/ (real Windows calls), fake.py (simulated PC for dev), ui/ (pywebview)
├── server/           Tide Server (FastAPI)
│   └── tide_server/  api/, classify/ (describe, heuristics, jev, pipeline), decide.py, ingest.py,
│                     monitor.py, similarity.py, simulate.py (59 fake seats), discovery.py
├── console/          Teacher Console (React + Vite)
├── design/
│   └── mock-ui.html  The UI reference: every screen, clickable
└── docs/
    ├── ARCHITECTURE.md   (this file)
    ├── DEMO.md           the demo script and cross-question answers
    ├── SETUP_TWO_PCS.md  demo setup on two new Windows PCs
    ├── DEVELOPMENT.md    build and test everything on one machine
    ├── specs/            design spec: scope and decisions
    └── plans/            implementation plan
```
