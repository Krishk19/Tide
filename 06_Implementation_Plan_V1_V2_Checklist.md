# Tide: Implementation Plan, Feature Matrix & Evaluation Checklist

**Project:** Tide — Secure Lab Assessment Platform  
**Target Architecture:** LAN-based Client-Server (Zero External Internet Required)  
**Timeline:**
- **Checkpoint 1 (V1 — Mid-Evaluation):** T + 10 Hours
- **Checkpoint 2 (V2 — Final Evaluation):** T + 24–30 Hours (Day 2)

---

## 🎯 Executive Overview & Core Framing

### The Pitch
> *"We don't claim to prevent cheating — we give teachers a live, evidence-backed flag timeline and cross-student similarity detection, with every action auditable, so a human makes the final call instead of an algorithm."*

### Why This Wins
1. **Realistic & Defensible:** Avoids untestable, fragile claims of "kernel-level unbreakable lockdown." Instead, it provides actionable evidence and human review.
2. **Built for Real College Labs:** Runs 100% on LAN without internet. Works with single-monitor lab setups and collection of mobile phones.
3. **True Multi-Teacher Scoping:** Real accounts, real isolation at the database query layer.
4. **Complete Exam Lifecycle:** Authoring days ahead $\rightarrow$ session scheduling $\rightarrow$ server-clock locked gate $\rightarrow$ Monaco editor $\rightarrow$ visible/hidden test execution $\rightarrow$ real-time telemetry $\rightarrow$ autosave resilience $\rightarrow$ AST plagiarism detection.

---

## 🗺️ V1 vs V2 Feature Matrix

| Feature Domain | Feature / Problem Solved | Phase | V1 (10-Hr Mid-Eval) | V2 (Final Pitch & Demo) |
|---|---|---|---|---|
| **Data & Architecture** | SQLite Relational Schema (Tier 0) | V1 | ✅ Full Schema & Models | ✅ Production Migrations & Indexes |
| **Authentication** | Multi-Teacher Auth (JWT + bcrypt) | V1 | ✅ Login, Token Scoping | ✅ Token Refresh & Session Expiry |
| **Assignment Lifecycle** | Reusable Problem Authoring (visible/hidden tests) | V1 | ✅ CRUD + Language Selection | ✅ Clone Assignment / Template Library |
| **Session Scheduling** | Day-of Session (6-char code + start time) | V1 | ✅ Active Code Generation | ✅ Code Collision Check & Status Auto-Transition |
| **Start Gate** | Server-Clock Start-Time Lockdown | V1 | ✅ Server timestamp lock + Countdown | ✅ Real-time countdown broadcast |
| **Student Client** | Electron Kiosk Shell (no chrome, no DevTools) | V1 | ✅ F12 Block, Right-Click Block | ✅ Windows Shortcut Hardening |
| **Student Client** | Monaco Code Editor Integration | V1 | ✅ Syntax highlighting, Run, Submit | ✅ Theme, Font Size, Layout polish |
| **Code Grading** | Polyglot Grading (Python, C++, Java) | V1 | ✅ Visible + Hidden Tests execution | ✅ Judge0 / Sandboxed Subprocess fallback |
| **SQL Grading** | Specialized SQL Pipeline (Schema + Seed) | V1 | ✅ In-memory SQLite execution | ✅ Order-agnostic comparator & Normalization |
| **Confidentiality** | Hidden Test Protection (Anti-leak) | V1 | ✅ Server-only hidden tests | ✅ Redacted result payload verification |
| **State Resilience** | Debounced Autosave (3–5s) | V1 | ✅ Autosave endpoint & DB persistence | ✅ Visual "Saved" pulse in Kiosk UI |
| **Live Telemetry** | Real-time WebSocket Flag Stream | V1 | ✅ Blur, Focus, Fullscreen-exit, Paste | ✅ Teacher dashboard live populating feed |
| **Correlated Proctoring**| Focus-lost $\rightarrow$ immediate paste correlation | V2 | 🟡 Raw events logged | ✅ **High-Confidence Warning Badge** |
| **Abrupt Disconnect** | Power cut / Task Manager kill handling | V2 | 🟡 WebSocket disconnect recognized | ✅ **`connection-lost` flag + autosave ref** |
| **Auto-Reconnect** | Student rejoins after crash/disconnect | V2 | 🟡 Manual re-enter | ✅ **$\Delta t$ gap tracking & restored state** |
| **Audit Workflow** | Non-Destructive Flag Review (`dismissed`) | V2 | 🟡 Simple flag listing | ✅ **`open / dismissed / escalated` audit log** |
| **Similarity Engine** | AST-based Cross-Student Plagiarism Detector | V2 | ⚪ Not required for mid-eval | ✅ **Python AST normalization & similarity score**|
| **Multi-Teacher Demo** | Two parallel teachers on LAN | V2 | 🟡 Single teacher verified | ✅ **Dual live sessions with 0 data bleed** |
| **Triage / Scoring** | Aggregate Risk Score per student | V2 (Stretch) | ⚪ Parked | 🟡 Flag aggregation heuristic |

*Legend: ✅ Must Have & Demonstrated | 🟡 Partial / Basic | ⚪ Stretch / V2 Exclusive*

---

## ⏱️ Phase 1: V1 Milestone (Target: 10 Hours — Mid-Evaluation)

### Goal for Mid-Evaluation
Demonstrate a complete, working, end-to-end coding exam on LAN:
1. Teacher logs in, creates a problem with visible and hidden test cases.
2. Teacher schedules a session and displays a 6-character access code.
3. Student opens the Electron Kiosk app, enters access code and name.
4. App shows a locked waiting state until scheduled start time.
5. On exam unlock, student writes code in Monaco Editor.
6. Student runs code against visible test cases (receives output).
7. Student tries to switch windows / paste external text $\rightarrow$ instant flag emitted.
8. Student submits code $\rightarrow$ evaluated against hidden test cases $\rightarrow$ pass/fail returned without exposing hidden inputs.
9. Teacher dashboard displays live telemetry flags.

---

### Detailed V1 Checklist

#### 1. Backend Core & Database (Tier 0 & Tier 1)
- [ ] **Database Setup:**
  - SQLite database initialized with tables: `teachers`, `assignments`, `sessions`, `students_in_session`, `submissions`, `flags`.
  - Proper foreign keys and indexes (`teacher_id`, `access_code`, `student_session_id`, `ts`).
- [ ] **Teacher Authentication API:**
  - `POST /api/auth/register` (Seed/register instructor accounts with bcrypt).
  - `POST /api/auth/login` (Verify password, return JWT token containing `teacher_id` and `username`).
  - `GET /api/auth/me` (Token verification).
- [ ] **Assignment Management API:**
  - `POST /api/assignments` (Create assignment: title, statement, starter code, visible tests JSON, hidden tests JSON, languages).
  - `GET /api/assignments` (List assignments strictly filtered by authenticated `teacher_id`).
  - `GET /api/assignments/{id}` (Get assignment details).
- [ ] **Session Scheduling API:**
  - `POST /api/sessions` (Create session linked to an assignment, specify `start_time`, generate unique 6-character alphanumeric code).
  - `GET /api/sessions` (List sessions for the logged-in teacher).
  - `GET /api/sessions/{id}` (Session details + student attendance list).
- [ ] **Student Join & State Gate API:**
  - `POST /api/sessions/join` (Validate 6-char code, register `student_name` + `student_identifier`, return `student_session_id`).
  - `GET /api/exam/state/{student_session_id}`:
    - Compare `current_server_time` with `session.start_time`.
    - If `now < start_time`: Return `status: "locked"`, `start_time`, `server_time`.
    - If `now >= start_time`: Return `status: "active"`, problem statement, starter code, visible tests. **NEVER return hidden tests.**
- [ ] **Code Execution & Grading API:**
  - Direct execution runner (subprocess/sandbox fallback for Python/C++/Java).
  - `POST /api/exam/run` (Execute code against visible test cases only, return stdout, stderr, execution time).
  - `POST /api/exam/submit` (Execute code against visible AND server-side hidden test cases; return summary of passed/failed counts; record submission in DB).
- [ ] **SQL Grading Subsystem:**
  - Dynamic in-memory SQLite runner.
  - Execute question schema definition & seed data.
  - Execute student query, extract tabular results, normalize types and casing.
  - Compare student result set with expected query result set order-agnostically.
- [ ] **Autosave Endpoint:**
  - `POST /api/exam/autosave` (Debounced update of `submissions.code` and `submissions.last_autosaved_at`).
- [ ] **WebSocket Telemetry Hub:**
  - `/ws/student/{student_session_id}`: Receive raw client events (`focus-lost`, `focus-regained`, `fullscreen-exit`, `paste`).
  - `/ws/teacher`: Push live flag events filtered by teacher's active sessions.

#### 2. Student Kiosk Client (Electron + Monaco)
- [ ] **Kiosk Shell Lockdown:**
  - Fullscreen enforcement (`fullscreen: true`, `kiosk: true`, `frame: false`).
  - Block DevTools (`webPreferences: { devTools: false }`).
  - Intercept shortcut keys (`F12`, `Ctrl+Shift+I/J/C`, `Ctrl+R`, `F5`).
  - Disable right-click context menu.
  - Handle `leave-full-screen` $\rightarrow$ auto re-maximize window.
- [ ] **Telemetry Listeners in Electron:**
  - Window `blur` $\rightarrow$ send `focus-lost` with timestamp.
  - Window `focus` $\rightarrow$ send `focus-regained` with timestamp.
  - Window `leave-full-screen` $\rightarrow$ send `fullscreen-exit`.
- [ ] **Student Exam UI:**
  - Join view: input 6-char code, name, roll number.
  - Waiting view: live countdown timer synchronizing with server start time.
  - Exam view: split layout (Left: Problem statement & visible test cases; Right: Monaco Editor).
  - Monaco editor setup: syntax highlighting, language selector, tab handling.
  - "Run Visible Tests" button + console output drawer.
  - "Submit Exam" button with confirmation modal.
  - Client-side debounced autosave (triggers API call every 3–5 seconds upon typing).
  - Paste event interceptor in Monaco editor: captures paste character count and emits telemetry event.

#### 3. Teacher Browser Dashboard (Web)
- [ ] **Login Screen:** Clean username/password form connecting to `/api/auth/login`.
- [ ] **Assignment Manager:** Form to create problems with visible and hidden test case tables.
- [ ] **Session Launcher:** Modal to select assignment, pick start time, and display prominent 6-char access code for lab board projection.
- [ ] **Live Monitoring View:**
  - Active students table (Roll No, Name, Status, Last Autosave time).
  - Real-time flag feed powered by WebSocket: shows timestamped cards (`focus-lost`, `paste`, `fullscreen-exit`).

---

## 🚀 Phase 2: V2 Milestone (Final Evaluation — Day 2)

### Goal for Final Evaluation
Turn the working prototype into an airtight, technically sophisticated platform with advanced anti-cheat intelligence, forensic auditing, and cross-student similarity detection.

---

### Detailed V2 Checklist

#### 1. Correlated Flag Weighting & Detection Intelligence
- [ ] **Correlation Rule Engine:**
  - Detect `focus-lost` followed within $T \le 5$ seconds by a `paste` event of length $L \ge 20$ characters.
  - Automatically tag as `correlated-cheat-attempt` with high severity.
  - Store metadata: `{ blur_duration_seconds, paste_length, correlation_confidence: "high" }`.
- [ ] **Dashboard Visualization:**
  - Display correlated flags in high-contrast red badge with an exclamation icon.
  - Show explanation: *"Switched away for 8s, immediately pasted 142 characters"*.

#### 2. Robust Disconnect, Crash & Reconnect Lifecycle
- [ ] **WebSocket Heartbeat & Abrupt Disconnect Detection:**
  - Server detects TCP drop or socket closure without an explicit submit.
  - Auto-generate a `connection-lost` flag with last autosaved timestamp and code line-count.
- [ ] **Seamless Student Reconnect Flow:**
  - If kiosk crashes or task is killed, student opens kiosk, enters the same 6-character code and roll number.
  - Server recognizes existing `student_session_id`, restores exact autosaved code from DB.
  - Server logs a `reconnected` flag with calculated downtime $\Delta t = t_{\text{reconnect}} - t_{\text{disconnect}}$.
  - Teacher timeline reflects: *"Disconnected for 48s $\rightarrow$ Reconnected $\rightarrow$ Code restored"*.

#### 3. Non-Destructive Flag Review & Audit Trail
- [ ] **Review Workflow:**
  - Add flag actions on teacher dashboard: **Dismiss** (false positive, e.g., Windows Defender popup) or **Escalate** (suspicious).
  - `PATCH /api/dashboard/flags/{id}` updates status to `dismissed` or `escalated`.
  - Record `reviewed_by = teacher_id` and `reviewed_at = utc_now()`.
  - Flags are **never deleted from the database**.
- [ ] **Audit Trail Modal:**
  - Teacher can view student's complete chronological audit timeline even after the exam is over.

#### 4. AST-Based Cross-Student Code Similarity (Plagiarism Detection)
- [ ] **Syntax Tree Normalization Engine:**
  - Python submissions: Parse using Python's built-in `ast` module.
  - Replace all user variable names, function names, and argument names with normalized tokens (`var_1`, `var_2`, `func_1`).
  - Strip comments, docstrings, and non-semantic formatting.
  - For C++/Java: Token-stream / structural comparison.
- [ ] **Similarity Matrix:**
  - Compute pairwise Jaccard / Levenshtein / subtree similarity score (0% to 100%) between all students in the session.
  - Flag any student pair exceeding threshold (e.g. $\ge 85\%$ structural match).
  - Teacher dashboard displays "Code Similarity Matrix" ranking suspicious pairs with side-by-side diff view.

#### 5. Strict Multi-Teacher Isolation Surfacing
- [ ] **Parallel Session Demonstration:**
  - Setup Teacher 1 (Session Code `ABC123`) and Teacher 2 (Session Code `XYZ789`).
  - Verify Teacher 1's dashboard never receives WebSocket events or query records belonging to Teacher 2's session.
  - Security test: verify changing session ID in URL parameters returns `403 Forbidden` or empty results due to structural JWT query filtering.

#### 6. Polish, Reliability & Demo Rehearsal (Tier 3 Stretch)
- [ ] **Local Sandbox Fallback:**
  - Graceful fallback for code execution if Docker is unavailable on the host PC (direct isolated subprocess execution for Python/C++/Java/SQLite).
- [ ] **UI Polish:**
  - Dark mode teacher dashboard matching student kiosk aesthetics.
  - Sound chime or subtle notification animation when a high-priority flag triggers.
  - Export session report to JSON / CSV with student grades and flag counts.
- [ ] **Demo Battle-Testing:**
  - Prepare pre-seeded demo accounts and sample questions (1 Python algorithmic, 1 SQL query).
  - Rehearse 3-minute pitch and live cheat demonstration.

---

## 🛡️ Threat Model, Edge Cases & Specific Mitigations

| Attack Vector / Edge Case | What Actually Happens | How Tide Handles It |
|---|---|---|
| **Student presses `Alt+Tab` or `Win+Tab`** | Focus shifts away from Electron window | Electron `blur` event triggers; server logs `focus-lost` flag immediately. |
| **Student exits Fullscreen via `Esc`** | Chromium reserves `Esc` key by spec | `leave-full-screen` fires $\rightarrow$ emits `fullscreen-exit` flag $\rightarrow$ auto re-maximizes window within 100ms. |
| **Student pastes code from notes/AI** | External content inserted into editor | Monaco `onDidPaste` fires $\rightarrow$ captures character count $\rightarrow$ server logs `paste` flag. |
| **Switch out $\rightarrow$ copy AI code $\rightarrow$ switch in $\rightarrow$ paste** | Classic cheating sequence | Correlated detection: `focus-lost` + rapid large `paste` flagged as **High-Confidence Correlated Flag**. |
| **Student opens Developer Tools (`F12`)** | Might inspect memory or network | Blocked at Chromium embed level (`devTools: false`) + `before-input-event` catches F12 and Ctrl+Shift+I/J/C. |
| **Student right-clicks to inspect element** | Context menu popup | `context-menu` event intercepted with `e.preventDefault()`. |
| **Student edits client clock to bypass start time** | Attempts early exam access | Start gate validated against server SQLite clock on every `/exam/state` call; client clock is ignored. |
| **Student inspects network payloads for hidden tests** | Network sniffing | Hidden tests are stored only on the server; the API never transmits hidden inputs or outputs to client. |
| **App killed via Task Manager or Power Outage** | Abrupt process termination | Continuous debounced autosave protects code state $\rightarrow$ server detects socket drop $\rightarrow$ student relaunches, resumes seamlessly $\rightarrow$ timeline logs disconnect duration. |
| **Two students submit identical logic with renamed variables** | Trivial renaming evasion | AST normalization strips variable names and compares abstract syntax trees, flagging structural similarity. |
| **Teacher clicks "clear flag"** | Risk of losing disciplinary evidence | Flags are never deleted; status transitions to `dismissed` with reviewer ID and timestamp for audit protection. |
| **Teacher B attempts to view Teacher A's session** | Direct URL or API manipulation | All queries strictly filter by JWT `teacher_id` (`WHERE sessions.teacher_id = :auth_teacher_id`); Teacher B gets 0 rows. |

---

## 🎪 Step-by-Step Demo Script for Judges

### Mid-Evaluation Demo (V1 — 10 Hours)
1. **Teacher Setup (1 min):**
   - Log in as Professor Sharma.
   - Show assignment with 2 visible tests and 3 hidden tests.
   - Create a session set to start in 30 seconds; project the 6-character code (`TIDE01`).
2. **Student Join (1 min):**
   - Launch Electron Kiosk on student PC.
   - Enter `TIDE01`, Roll No: `CS2026_042`, Name: `Rahul Kumar`.
   - Show the locked countdown screen waiting for the server clock.
   - Screen automatically unlocks at $T=0$.
3. **Cheat Detection Demo (1 min):**
   - Student presses `Alt+Tab` to switch to notepad $\rightarrow$ Teacher dashboard immediately flashes `focus-lost`.
   - Student copies a block of code and pastes it into Monaco $\rightarrow$ Teacher dashboard flashes `paste (84 chars)`.
4. **Grading Demo (1 min):**
   - Student runs code against visible test cases $\rightarrow$ passes.
   - Student submits $\rightarrow$ server grades against hidden tests $\rightarrow$ student receives "4/5 Tests Passed" (hidden inputs are never revealed).

### Final Evaluation Demo (V2 — Day 2)
1. **Correlated Cheat Intelligence:** Demonstrate the red High-Confidence badge when window switch is immediately followed by a large paste.
2. **Disconnect Resilience:** Kill the student kiosk process via Task Manager mid-exam. Show teacher dashboard flag `connection-lost`. Relaunch kiosk, enter code, and watch the exact code restore instantly with `reconnected (gap: 18s)`.
3. **Audit Trail:** Teacher clicks "Dismiss" on a false alarm flag $\rightarrow$ show that flag is marked `dismissed` with teacher's username and audit timestamp.
4. **AST Plagiarism:** Submit two solutions with completely different variable and function names. Run the similarity analyzer $\rightarrow$ reveal a 94% structural match with highlighted syntax diff.
5. **Multi-Teacher Isolation:** Open two incognito browser windows with different teacher accounts to prove complete data segregation.

---

## 📋 Immediate Action Items (Next 2 Hours)

1. **Backend Auth & Session Endpoints:** Implement FastAPI JWT login, assignment creation, and session generation endpoints.
2. **Student State API & Kiosk Connection:** Wire Monaco editor in Electron to the backend `/exam/state`, `/exam/run`, and `/exam/submit` endpoints.
3. **Autosave & WebSocket Hub:** Set up WebSocket channels for real-time telemetry streaming and connect debounced Monaco typing events.
