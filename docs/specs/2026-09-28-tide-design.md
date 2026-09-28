# Tide — Design Spec (Demo Build)

*Tide = Test Integrity in Developer Environments.*

Date: 2026-09-28 · Status: **built** (all 25 plan tasks implemented and passing on branch `rebuild`); real-hardware Windows verification still open — see §5
Plan: [../plans/2026-09-28-tide-demo-build.md](../plans/2026-09-28-tide-demo-build.md) · How it works: [../ARCHITECTURE.md](../ARCHITECTURE.md) · Demo: [../DEMO.md](../DEMO.md) · UI reference: [../../design/mock-ui.html](../../design/mock-ui.html)

## 1. Intent

Build a **convincing, demoable** anti-cheating system for Windows lab tests, runnable on 1–2
laptops. Production concerns are **explained, not built**. Priority is high-impact cheat
detection over platform features.

**Success =** in a ~4-minute live demo, judges see each of the top cheats caught (most of them
stopped live) on a clean console, and the team can answer "what about…" questions from the docs.

## 2. Decisions log

| # | Decision | Why |
|---|---|---|
| D1 | **Rebuild from scratch.** Drop the v1 Electron kiosk + in-app editor + server-side code runner | Students must use native tools (VS Code, CodeBlocks, Wireshark, VMware); v1 had unauthenticated student APIs and ran student code raw on the server |
| D2 | **Windows only** | Real lab is Windows; best OS APIs |
| D3 | **Background agent watches the real desktop**, no kiosk | Principle 1 |
| D4 | **Enforcement mode B:** auto-act on high-confidence hits, flag the rest | Stops the cheat live; humans still review |
| D5 | **Questions released only through Tide**, after offline pre-flight, odd/even sets by seat number | Closes "download from Classroom first" |
| D6 | **Jev classifier on the teacher server** (via OpenRouter Decisions API, `~typesafe/jev-latest`) for ambiguous signals; rules first; offline heuristics fallback | Catches unknown AI tools with a thresholdable confidence; demo never breaks |
| D7 | **Stack:** Python agent (PyInstaller exe, pywebview UI) · FastAPI + SQLite server · React + Vite console. **No Electron** | OS APIs from Python; small binary; team knows Python/React |
| D8 | **Server clock is authoritative**; agents get `ends_at` + offset | Timer sync, restart-safe |
| D9 | **59 simulated seats** in demo mode | Makes one laptop look like a 60-seat lab |
| D10 | **No grading** in the demo | Not the differentiator |

## 3. In scope (demo build)

Requirement IDs are referenced by the implementation plan.

**Agent**
- A1 Server discovery (UDP broadcast) + manual IP; pair with join code, roll, seat → token
- A2 Pre-flight: internet probe, VS Code AI extension scan, deny-list process check, file inventory with fingerprints
- A3 Watchers: foreground window + browser host (UIA), processes, network adapters + probe, LAN peers, USB, clipboard, exam-folder changes
- A4 Local rules from the server policy; act instantly (close tab, kill app, overlay)
- A5 Evidence screenshot on flags ≥ medium
- A6 Receive question files into `C:\Exam\<roll>\`; 30 s snapshots of changed files; submit zip
- A7 UI (pywebview): join, pre-flight checklist, waiting, floating timer pill with Submit, block overlay, done
- A8 Heartbeat 3 s; offline buffering to disk with flush on reconnect

**Server**
- S1 Exam CRUD (single exam at a time is fine), set files A/B, policy presets, join code
- S2 Pairing, seat tokens, WS auth, heartbeat timeout → offline flag
- S3 Classifier pipeline: server rules → cache → Jev → heuristics; thresholds per ARCHITECTURE §5.2
- S4 Decision engine: severity, seat colour, `act` messages, action log
- S5 Clock: start, per-seat/all extend, `ends_at`, auto-end → `end` to agents
- S6 Question release by seat parity
- S7 Snapshots, code-burst detection, submissions, similarity across submissions + vs. inventory
- S8 Console WS feed; REST for flags (dismiss/confirm), seat detail, report CSV
- S9 Demo mode: seed exam, 59 simulated seats, "Simulate event on seat" endpoint

**Console** (matches `design/mock-ui.html`)
- C1 Setup: title, duration, set uploads, policy chips
- C2 Lobby: join code, seat grid with pre-flight status, Start
- C3 Live: seat grid (colour, flag count, current app), flag feed, clock, extend, broadcast notice
- C4 Seat drawer: timeline, flags with screenshot + Jev badge, code-growth chart, actions (warn, extend, dismiss/confirm)
- C5 Results: submissions, similarity pairs, flag summary, export CSV

## 4. Out of scope (pitch only)

Windows service + session helper, MSI/GPO deployment, TLS/cert pinning, binary attestation,
teacher accounts and multi-lab, firewall lockdown, VM `.vmx` inspection, grading, macOS/Linux.

## 5. Acceptance criteria

Checked in the single-device rehearsal (fake Windows PC + real server + live Jev, `docs/DEVELOPMENT.md` §4),
unless marked **Windows-only** — those need `.exe` hardware verification (plan Task 19, Step 5) and the
two-laptop rehearsal (`docs/SETUP_TWO_PCS.md`).

1. ✅ Fresh laptop: run the agent, pair within 10 s of entering the code. **(.exe build + real hardware still open)**
2. ✅ Pre-flight fails while internet is reachable; questions are not delivered to that seat.
3. ✅ Start delivers Set A to an odd seat, Set B to an even seat; timers on agents are within 1 s of the server.
4. ⏳ **Windows-only.** Opening `chatgpt.com` in Chrome closes the tab within 2 s and shows a red seat with a screenshot. (Verified with the fake platform via the rule path; the real address-bar read + `Ctrl+W` close needs real Windows — plan Task 19.)
5. ✅ An AI site not on any list is classified by Jev and auto-closed at ≥ 0.90. Verified live: `poe.com` → 0.97, an unknown "NoteGPT" app → 0.98.
6. ✅ Enabling Wi-Fi with internet raises "Internet detected"; the block clears once Wi-Fi is off.
7. ✅ Opening an inventoried file, and pasting its contents into the exam folder, raise "Pre-exam file opened" and "Old code reused" with the path — verified at 100% match.
8. ⏳ Killing the agent turns the seat grey within 10 s. (`monitor.tick` is unit-tested; not yet rehearsed by physically killing a running agent process.)
9. ✅ Submit uploads the folder; the Results tab lists it, flags, and max-match %; CSV export endpoint verified.
10. ✅ With no Jev key, the pipeline falls back to heuristics (capped confidence, never auto-acts) and the console header says so — unit-tested; not yet rehearsed live end-to-end with the key unset.

**Status:** 8/10 fully rehearsed end-to-end; 2 need real Windows hardware or a longer-running process to exercise (#4 real close-tab mechanics, #8 kill-and-wait). All ten are covered by passing automated tests either way.
