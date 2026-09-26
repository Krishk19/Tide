# Technical Requirements Document (TRD)
## Secure Lab Assessment Platform

---

## 1. Architecture summary
**LAN-based client-server** — not a fully offline single-device app, and not internet-dependent. One machine on the lab's existing LAN (any lab PC, commonly the teacher's own laptop) runs the backend + self-hosted judge. All other machines communicate with it over the local network only. No traffic ever needs to leave the room.

```
[Student PC 1] ─┐
[Student PC 2] ─┼── LAN / Wi-Fi ──► [Backend Server] ── local ──► [Judge0 (Docker)]
[Student PC N] ─┘         ▲                │
                            │                └──► [SQLite DB]
[Teacher PC(s)] ───────────┘  (browser dashboard, any LAN machine)
```

## 2. Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| Student client | **Electron** (kiosk mode) + **Monaco Editor** | Native window control (fullscreen lock, DevTools disable, focus/blur events) unavailable to a plain browser tab; Monaco gives VS Code-grade editing for free |
| Teacher client | React (plain browser, not kiosk) | Needs full browser access — different route/bundle from the student app, served by the same backend |
| Backend API | FastAPI (Python) or Node/Express | Either is fine; pick based on team's stronger stack (Python/ML strength noted for this team → FastAPI is the natural fit) |
| Database | **SQLite** | Zero-config, file-based, no external DB server to install on lab machines, sufficient for session-scoped MVP load |
| Code execution / grading | **Self-hosted Judge0** (Docker) | Open-source sandboxed multi-language judge with time/memory limits already built — avoids writing a sandbox from scratch |
| Real-time flags | WebSocket (Socket.io or native FastAPI WebSocket) | Live push from student clients → server → teacher dashboard |
| Packaging (student app) | **electron-builder** | Produces a single Windows installer/portable `.exe`, no Node install needed on lab PCs |
| Auth | JWT or signed session cookie + `bcrypt` password hashing | Required once multi-teacher is confirmed — isolates data by `teacher_id` |

## 3. Language/runtime support (MVP)
C++, Python, Java — standard Judge0 language IDs, stdout-diff grading.
SQL — **separate pipeline**, not a Judge0 language ID reuse:
1. Load a per-question schema + seed data into a fresh SQLite instance.
2. Execute student query.
3. Dump result set, normalize (type coercion, NULL handling, column casing).
4. Compare **order-agnostically** unless the question explicitly requires `ORDER BY`.

This is budgeted as its own task — treating it as "one more Judge0 language" breaks silently on demo day.

## 4. Kiosk lockdown requirements
Implemented via Electron `BrowserWindow` config, not page-level JavaScript (page-level blocking is defeatable from DevTools itself):
- `kiosk: true`, `fullscreen: true`, `frame: false`, `autoHideMenuBar: true`
- `webPreferences.devTools: false` — the actual F12 block (Chromium-embed level)
- `before-input-event` listener — belt-and-suspenders block of F12 / Ctrl+Shift+I/J/C
- `context-menu` event — disable right-click
- `leave-full-screen` handler — re-force fullscreen + emit a `fullscreen-exit` flag (note: OS-level Esc-to-exit-fullscreen cannot be prevented by any app, per browser/Chromium spec — this is detection, not prevention)
- `blur` / `focus` window events → `focus-lost` / `focus-regained` flags, timestamped

**Known limitation, not solved in MVP:** `window-all-closed` has no guard logic yet. A student can currently kill the app via Task Manager with no server-side consequence beyond the disconnect flag. Decision needed: does reconnect just work (recommended default) or does it require teacher unlock?

## 5. API surface (indicative)

| Endpoint | Method | Purpose |
|---|---|---|
| `/auth/login` | POST | Teacher login, returns JWT |
| `/assignments` | POST/GET | Create / list a teacher's own assignments |
| `/sessions` | POST | Create session from an assignment (start time + access code) |
| `/sessions/join` | POST | Student submits access code, validated against active sessions |
| `/exam/state` | GET | Server-side check: is scheduled start time reached? |
| `/exam/submit` | POST | Submit code → routed to Judge0 or SQL pipeline → graded result |
| `/exam/autosave` | POST | Debounced code-state sync (every few seconds) |
| `/ws/flags` | WS | Student client → server: live flag events. Server → teacher dashboard: live feed |
| `/dashboard/flags` | GET | Teacher-scoped flag list (filtered server-side by JWT's `teacher_id`, never by a client-supplied session ID) |
| `/dashboard/flags/:id/status` | PATCH | Mark flag open / dismissed / escalated |

**Security-critical rule:** every teacher-facing query derives scope from the authenticated `teacher_id` in the JWT, never from a session ID the client passes. Passing a client-chosen session ID as the sole scoping mechanism is a real access-control hole — this must never be the design.

## 6. Non-functional requirements
- **No internet dependency.** Every component (Judge0, DB, backend) runs entirely on the local machine/LAN.
- **Concurrent multi-teacher sessions.** Two or more sessions must run simultaneously without any data crossover — verified via `teacher_id` scoping at the schema level (see Database doc).
- **Access-code collision handling.** Code generation checks for collisions only against currently-active sessions before issuing a new one.
- **Resilience to disconnects.** Debounced autosave (every few seconds) ensures no more than a few seconds of code is ever at risk of loss on crash/kill/network drop.
- **Hidden test case confidentiality.** Hidden inputs/expected outputs are never transmitted to or stored on the student client — only pass/fail per test is returned.

## 7. Deployment notes
- Student machines: install the packaged Electron `.exe` once (USB or LAN file share — no internet needed).
- Server machine: run backend + `docker run` Judge0 container once per exam day; point student `.exe` config at `SERVER_IP:PORT`.
- Teacher machines: no install — any browser, any LAN PC, navigate to `SERVER_IP:PORT/dashboard`.
