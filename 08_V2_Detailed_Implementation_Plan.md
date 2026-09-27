# Tide V2: Comprehensive Implementation Plan & Technical Blueprint

**Project:** Tide — Secure Lab Assessment Platform  
**Phase:** V2 (Advanced Anti-Cheat Intelligence, Remote Classroom Control, Code Playback & Plagiarism Engine)  
**Timeline:** Checkpoint 2 (Final Evaluation & Production Hardening)  
**Architecture:** LAN-Based Client-Server (Zero External Internet Required)  

---

## 🎯 Executive Summary & V2 Positioning

Where **V1** established the resilient operational core (kiosk lockdown, server-clock start-time lockdown, polyglot grading, debounced autosave, and raw telemetry streaming), **V2** elevates Tide into an intelligent, defensible classroom management and evaluation platform designed specifically for college computing labs.

### The Core Philosophy
> *"We do not make fragile claims of 'kernel-level unbreakable lockdown.' Instead, Tide combines multi-signal telemetry correlation, live remote classroom control, crash-proof forensic downtime auditing, video-like code playback, and AST-based cross-student structural plagiarism detection to give instructors total classroom control and indisputable, human-actionable evidence."*

---

## 🗺️ V2 Architecture Diagram & Data Flow

```mermaid
flowchart TD
    subgraph StudentPC["Student Kiosk (Electron / Web)"]
        UI["Monaco Editor UI"]
        KioskGuard["Kiosk Guard (Shortcuts / DevTools / ContextMenu)"]
        ClipboardTracker["Internal vs External Clipboard Buffer"]
        AutosaveSync["Debounced Code Autosave Engine"]
        WSClient["WebSocket Client & Heartbeat"]
        AnnouncementBanner["Broadcast Announcement & Warning Modal"]
    end

    subgraph TeacherPC["Tide Server (Teacher Laptop / Lab Host)"]
        FastAPI["FastAPI Master Controller"]
        DB[(SQLite Master DB)]
        
        subgraph V2Engines["V2 Subsystems & Engines"]
            Correlation["Multi-Signal Correlation Engine"]
            RiskScorer["Dynamic Risk Scoring (0 - 100)"]
            ASTNormalizer["AST Tree Normalizer & Plagiarism Matrix"]
            ReconnectAuditor["Forensic Delta-t Downtime Auditor"]
            CodePlaybackEngine["Autosave Snapshot History & Playback Engine"]
            RemoteCommander["Classroom Commander (Announce / +Time / Force Submit)"]
            ReportGen["University Marksheet & Dossier Exporter (CSV/JSON)"]
        end
    end

    subgraph TeacherDashboard["Teacher Command Center (/dashboard)"]
        LiveFeed["Live Correlated Flag Stream (High-Confidence Alerts)"]
        TriageGrid["Traffic Light Class Health Matrix (Green / Amber / Red)"]
        RemoteControls["Remote Class Broadcast & Student Action Toolbar"]
        CodePlaybackModal["'Code Playback' Scrubber & Growth Replay"]
        PlagView["Cross-Student Code Similarity Diff Studio"]
        TimelineModal["Student Forensic Chronological Audit"]
        ExportActions["One-Click Official Marksheet Export (CSV / JSON)"]
    end

    UI -->|Autosave (3s)| AutosaveSync --> FastAPI
    KioskGuard -->|Event| WSClient --> FastAPI
    ClipboardTracker -->|External Paste| WSClient
    FastAPI -->|Announcements & Remote Actions| AnnouncementBanner
    
    FastAPI --> Correlation
    FastAPI --> ReconnectAuditor
    FastAPI --> CodePlaybackEngine
    FastAPI --> RemoteCommander
    FastAPI --> DB
    
    Correlation --> RiskScorer
    RiskScorer --> DB
    
    DB --> ASTNormalizer
    ASTNormalizer --> PlagView
    
    FastAPI -->|Live WS Broadcast| LiveFeed
    DB --> TriageGrid
    DB --> CodePlaybackModal
    DB --> TimelineModal
    DB --> ReportGen --> ExportActions
    RemoteCommander --> RemoteControls
```

---

## 📦 V2 Feature Breakdown: 8 Strategic Milestones

---

### Milestone 1: Multi-Signal Correlation & Dynamic Risk Scoring (0–100)

#### 1. The Problem in V1
In V1, raw events (`focus-lost`, `paste`) are streamed independently. A student switching away to an IDE or browser for 8 seconds and immediately pasting 80 characters generates two separate, disconnected cards in the instructor feed. The instructor has to manually piece together timestamps.

#### 2. V2 Technical Specification
1. **Sliding Time-Window Correlator:**
   - Maintain an in-memory sliding buffer of student telemetry events per `student_session_id` ($T \le 10\text{s}$).
   - **Rule 1 (Window-Switch $\rightarrow$ Immediate Paste):** If a `paste` event of length $L \ge 20$ characters occurs within $T \le 6$ seconds after a `focus-lost` or `fullscreen-exit` event:
     - Generate a synthesized flag: `correlated-cheat-attempt`.
     - Severity: `high` or `critical`.
     - Flag Metadata:
       ```json
       {
         "blur_duration_seconds": 6.8,
         "paste_length": 84,
         "paste_preview": "def find_shortest_path(graph, src, dest):",
         "confidence": "high",
         "reason": "Window lost focus for 6.8s followed immediately by external paste of 84 chars"
       }
       ```
2. **Dynamic Risk Score Engine (0 to 100 Scale):**
   - Each student in session receives a live `risk_score` recalculation on every telemetry event:
     $$\text{RiskScore} = \min\left(100, \sum (w_i \times C_i) + B_{\text{correlated}} + P_{\text{external}}\right)$$
     Where:
     - $w_{\text{focus-lost}} = 5\text{ pts}$ (capped at 25)
     - $w_{\text{fullscreen-exit}} = 20\text{ pts}$
     - $w_{\text{connection-lost}} = 10\text{ pts}$
     - $B_{\text{correlated}} = 35\text{ pts per incident}$
     - $P_{\text{external}} = \min(30, \lfloor \text{Total Pasted Chars} / 25 \rfloor)$
   - Risk Classifications:
     - **0 – 19:** `Clean` (Green)
     - **20 – 49:** `Low Risk` (Blue)
     - **50 – 74:** `Suspicious` (Amber)
     - **75 – 100:** `High Risk / Disciplinary Review` (Red)
3. **Teacher Command Center Additions:**
   - Flag cards for `correlated-cheat-attempt` render with prominent red styling, an alert badge, and an explanation snippet.
   - Student roster table adds a **Risk Score Meter** sorting students by highest suspicious activity first.
   - Optional sound/audio notification on teacher dashboard when a `correlated-cheat-attempt` fires.

---

### Milestone 2: Crash, Kill & Reconnect Resilience with Forensic $\Delta t$ Downtime Audit

#### 1. The Problem in V1
If a student's computer abruptly powers off, or the student kills the kiosk process via Task Manager to claim a "technical malfunction", V1 logs `connection-lost`. When the student re-enters, they rejoin, but the instructor cannot easily distinguish between a legitimate reboot and an intentional offline consultation.

#### 2. V2 Technical Specification
1. **Intelligent Reconnection & State Restoration:**
   - In `POST /api/sessions/join`:
     - If `(access_code, student_identifier)` already exists in `students_in_session`:
       - Check `submission.submitted_at`: if already submitted, return `400: Assessment already finalized`.
       - If not submitted, calculate downtime gap:
         $$\Delta t = t_{\text{reconnect}} - t_{\text{disconnect}}$$
         (where $t_{\text{disconnect}}$ is the timestamp of socket drop or last autosave).
       - Automatically fetch the student's latest code and language from `submissions` table.
       - Log a structured `reconnected` flag:
         ```json
         {
           "downtime_seconds": 47,
           "restored_code_length": 412,
           "restored_line_count": 24,
           "last_saved_at": "2026-09-27T12:15:30Z"
         }
         ```
       - Resume session seamlessly on student kiosk without data loss.
2. **Teacher Feed Notification:**
   - Shows chronological correlation: *"Student disconnected (abrupt socket drop) $\rightarrow$ Offline for 47 seconds $\rightarrow$ Reconnected $\rightarrow$ Code state restored (24 lines)"*.
   - Gives proctor full context to judge whether the gap matches a quick PC restart or an extended absence.

---

### Milestone 3: AST-Based Cross-Student Code Similarity (Plagiarism Detection)

#### 1. The Problem in V1
Students in college labs often share code verbally or via paper notes, modifying variable names, function names, and whitespace (`x` $\rightarrow$ `counter`, `for i in range` $\rightarrow$ `for idx in range`) to bypass naive text diffs.

#### 2. V2 Technical Specification
1. **Python Abstract Syntax Tree (AST) Normalizer:**
   - Built using Python's native `ast` standard library module.
   - **Canonical Identifier Alpha-Renaming:**
     - Replace all variable names (`ast.Name`) with canonical ordered tokens (`v0`, `v1`, `v2`...).
     - Replace all function names (`ast.FunctionDef`) with canonical tokens (`fn0`, `fn1`...).
     - Replace function arguments (`ast.arg`) with canonical tokens (`arg0`, `arg1`...).
   - **Syntax Stripping:**
     - Remove comments, docstrings, type annotations, and pass statements.
     - Normalize syntax structures (e.g. constant expressions).
   - **AST Token Serialization:**
     - Walk normalized AST to generate a canonical token stream.
     - Example:
       ```python
       # Original Student A:
       def calculate_factorial(n):
           result = 1
           for i in range(1, n + 1):
               result = result * i
           return result
       
       # Original Student B:
       def fact(num):
           ans = 1
           for x in range(1, num + 1):
               ans = ans * x
           return ans
       ```
       Both compile to the exact identical normalized AST token stream:
       `[FunctionDef, fn0, [arg0], Assign, [v0], For, [v1], Call, [Name, range], Assign, [v0], Mult, Return, [v0]]`
2. **Pairwise Similarity Engine:**
   - For all submissions in a completed or ongoing session:
     - Compute structural similarity using tokenized $k$-gram Jaccard Index combined with Tree Edit Distance ratio:
       $$\text{Similarity}(S_A, S_B) = \frac{|K_A \cap K_B|}{|K_A \cup K_B|} \times 100\%$$
     - Pairwise matrix generated in $< 1.5$ seconds for up to 150 students.
3. **Multi-Signal Correlation Filter to Prevent False Positives on Canonical Questions:**
   - On short questions where solutions naturally converge:
     - **Keystroke Velocity Filter:** Flag high AST similarity *only* if at least one student exhibited "0-to-full" instant code appearance.
     - **Starter Code Subtraction:** Mask boilerplate starter code so only novel logic is compared.
     - **Idiosyncrasy Fingerprinting:** Check for matching non-standard quirks (e.g., identical `-99999` constant, unused variable `temp_cnt`, identical edge-case logic error).
4. **C++ / Java Multi-Language Fallback:**
   - Token stream structural comparison (stripping identifier names and comments, comparing token operator/control flow sequences).
5. **Teacher Command Center UI: Similarity Studio:**
   - **Similarity Matrix View:** Ranked table of student pairs exceeding threshold (e.g. $\ge 70\%$).
   - **Side-by-Side Diff Modal:**
     - Left pane: Student A's code.
     - Right pane: Student B's code.
     - Synchronized line scrolling.
     - Highlighted structural similarity percentage and common logical blocks.

---

### Milestone 4: Live Remote Classroom Control & Broadcast Announcements

#### 1. The Problem in V1
In real college labs, teachers shout across the room to clarify questions, have no way to grant extra time to a student whose machine rebooted, and cannot remotely intervene if a student refuses to submit.

#### 2. V2 Technical Specification
1. **Class-Wide Broadcast Announcements:**
   - Endpoint: `POST /api/sessions/{session_id}/broadcast`
     - Payload: `{ "message": "Notice: In Question 2, assume inputs are positive integers only!", "type": "info|warning" }`
   - Real-Time Delivery: Pushed over WebSocket to all student kiosks connected to the session.
   - Student Kiosk UI: Displays a high-visibility, dismissible floating announcement banner at the top of the exam screen without interrupting Monaco editor focus.
2. **Per-Student Remote Interventions:**
   - **Grant Extra Time (`+Time`):**
     - Endpoint: `POST /api/sessions/{session_id}/students/{student_id}/extend-time`
     - Allows teacher to grant $+5$, $+10$, or $+15$ minutes of compensatory time to a specific student whose PC rebooted or froze.
     - Kiosk updates remaining countdown display dynamically.
   - **Send Direct Warning Popup:**
     - Endpoint: `POST /api/sessions/{session_id}/students/{student_id}/warn`
     - Displays an amber warning modal on the student's screen: *"Warning from Instructor: Keep your eyes on your monitor. Suspicious activity has been logged."*
   - **Remote Screen Freeze & Force Submit:**
     - Endpoint: `POST /api/sessions/{session_id}/students/{student_id}/force-submit`
     - Instantly triggers grading of the student's latest autosaved code, transitions state to `submitted`, locks the Monaco editor, and displays the submitted screen.

---

### Milestone 5: "Code Playback" Forensic Scrubber (Keystroke & Growth Replay)

#### 1. The Problem in V1
When a student is caught with an external paste and claims *"I typed every character myself"*, the teacher has no visual proof of how the code actually grew over the session duration.

#### 2. V2 Technical Specification
1. **Autosave Snapshot Keyframes:**
   - The debounced autosave endpoint stores periodic delta keyframes in SQLite (`code_snapshots` table or snapshot JSON):
     - `student_session_id`, `code`, `timestamp`, `lines_count`, `chars_count`, `is_paste_event`.
2. **Teacher Code Playback Scrubber UI:**
   - Accessible via the teacher dashboard by clicking **"⏪ Code Playback"** on any student row.
   - **Interactive Scrubber Bar:**
     - Timeline slider from $00:00$ (joined) to $45:00$ (submitted).
     - **Red marker dots** on the slider indicate exact timestamps where external paste spikes occurred.
     - **Yellow marker dots** indicate where test runs were executed.
   - **Playback Controls:**
     - Play / Pause button with speed options ($1\times, 2\times, 5\times, 10\times$).
     - Dragging the slider shows the exact code in the editor at that historical second.
   - **The Defense:** If a student claims they typed it, dragging the slider reveals that between 10:14:02 and 10:14:05 (3 seconds), 42 lines appeared out of nowhere. Indisputable forensic evidence.

---

### Milestone 6: "Traffic Light" Class Health Triage Grid (Zero Alert Fatigue)

#### 1. The Problem in V1
A teacher with 60 students cannot read 400 sequential alert badges streaming down a single vertical feed. Alert fatigue causes them to miss critical infractions.

#### 2. V2 Technical Specification
1. **3-Zone Classroom Triage Dashboard:**
   - Replaces the noisy raw feed with a clean, high-level **Traffic Light Grid**:
     - 🟢 **Zone 1: On Track (Healthy):**
       - Students typing with normal incremental velocity, running visible tests, 0 or minor transient blurs.
     - 🟡 **Zone 2: Struggling / Inactive (Needs Pedagogical Help):**
       - Students who have written 0 lines for 15+ minutes, or have 6+ consecutive failing test runs with compilation errors. The teacher can walk over and assist.
     - 🔴 **Zone 3: High Suspicion (Proctoring Intervention):**
       - Students with `correlated-cheat-attempt`, risk score $\ge 60$, extensive window blur ($> 1\text{ min}$), or sudden 0-to-full code paste.
2. **Live Counter Pills:**
   - Top banner displays: `🟢 48 On Track | 🟡 8 Struggling | 🔴 4 Under Review`.
   - Clicking any pill filters the classroom roster instantly.

---

### Milestone 7: Forensic Audit Trail, Timeline Modal & University Marksheet Export

#### 1. The Problem in V1
When a student contests an academic dishonesty accusation before a university disciplinary committee, instructors need comprehensive, chronological proof with exact timestamps, rather than fleeting dashboard alerts.

#### 2. V2 Technical Specification
1. **Per-Student Forensic Timeline API:**
   - `GET /api/sessions/{session_id}/students/{student_session_id}/timeline`:
   - Returns a merged, chronologically sorted array of all session actions:
     - `joined` (time + IP)
     - `autosaved` (timestamps, delta lines added/deleted)
     - `telemetry_flag` (`focus-lost`, `fullscreen-exit`, `paste`, `connection-lost`)
     - `test_run` (visible test results, execution time, errors)
     - `submission` (final grading score, hidden test breakdown)
     - `review_action` (flags reviewed or dismissed by instructor)
2. **Teacher Timeline Modal:**
   - Interactive visual vertical timeline displaying the student's entire exam session journey from start to finish.
3. **Official University Marksheet Exporter (1-Click):**
   - `GET /api/sessions/{session_id}/export?format=csv`:
     - Clean, official marksheet ready for university portal / ERP upload:
       `Roll No, Student Name, IP Address, Joined At, Submitted At, Visible Passed, Hidden Passed, Total Tests, Final Score %, Flag Count, Risk Score, Plagiarism Match %`.
   - `GET /api/sessions/{session_id}/export?format=json`:
     - Full forensic evidence dossier with complete student code, test logs, timestamps, and instructor review signatures.
4. **Enhanced Flag Review:**
   - Add optional instructor notes: `PATCH /api/dashboard/flags/{flag_id}` with `{ status: "escalated", notes: "Student confirmed using unauthorized notes during viva" }`.

---

### Milestone 8: LAN Packaging, Discovery & Multi-Room Hardening

#### 1. The Problem in V1
In V1, connecting lab PCs requires typing or configuring host URLs manually. In a real lab exam with 60–120 machines, zero-config launch is essential.

#### 2. V2 Technical Specification
1. **UDP Broadcast / LAN Auto-Discovery:**
   - Server runs a background UDP discovery responder on port 8001.
   - When the student client launches, it broadcasts a UDP discovery ping `TIDE_DISCOVER_SERVER`.
   - The teacher server responds with its IP, port, and active session codes.
   - The student kiosk automatically connects to the server with zero typing.
2. **Production Packaging:**
   - `npm run package:win`: Generates portable `Tide-Exam.exe` with bundled Chromium, locked kiosk flags, and default config.
   - Can be placed on a shared network drive (`\\lab-server\tide\Tide-Exam.exe`) or distributed via USB.
3. **Multi-Teacher Isolation Test Suite:**
   - Automated tests verifying that two concurrent instructors on the same LAN switch have complete data isolation with 0 data bleed.

---

## 📅 Step-by-Step Implementation Roadmap

| Step | Subsystem | Key Files to Create / Modify | Estimated Effort |
|---|---|---|---|
| **Step 1** | **Correlation Engine & Risk Scoring** | `server/app/services/heuristics.py`<br>`server/app/api/telemetry.py`<br>`client-teacher/app.js`<br>`client-teacher/styles.css` | 3 Hours |
| **Step 2** | **Crash & Reconnect Resilience** | `server/app/api/sessions.py`<br>`server/app/api/exam.py`<br>`client-student/src/renderer.js` | 2 Hours |
| **Step 3** | **Remote Classroom Control & Announcements** | `server/app/api/classroom.py`<br>`client-student/src/renderer.js`<br>`client-student/src/index.html`<br>`client-teacher/app.js` | 3 Hours |
| **Step 4** | **"Code Playback" Scrubber & Keyframe History** | `server/app/services/playback.py`<br>`server/app/api/exam.py`<br>`client-teacher/app.js`<br>`client-teacher/index.html` | 3 Hours |
| **Step 5** | **Traffic Light Class Health Triage Grid** | `server/app/api/dashboard.py`<br>`client-teacher/app.js`<br>`client-teacher/index.html` | 2 Hours |
| **Step 6** | **AST Plagiarism & Similarity Engine** | `server/app/services/plagiarism.py`<br>`server/app/api/similarity.py`<br>`client-teacher/index.html`<br>`client-teacher/app.js` | 4 Hours |
| **Step 7** | **Forensic Timeline & University Marksheet Export** | `server/app/api/reporting.py`<br>`client-teacher/index.html`<br>`client-teacher/app.js` | 3 Hours |
| **Step 8** | **LAN Auto-Discovery & Full V2 Automated Test Suite** | `server/app/services/discovery.py`<br>`server/tests/test_v2_classroom.py`<br>`server/tests/test_v2_plagiarism.py` | 2 Hours |

---

## 🧪 V2 Verification & Success Criteria

1. **Correlation Alert Verification:**
   - Student blurs window for 5s, returns, and pastes $\ge 20$ chars.
   - Server generates a `correlated-cheat-attempt` flag within 100ms.
   - Teacher feed displays red alert card with exact blur duration and paste snippet.
2. **Reconnect Verification:**
   - Kill student kiosk process mid-exam via Task Manager.
   - Reopen kiosk, enter same roll number and code.
   - Kiosk restores full editor text; teacher feed logs `reconnected` with accurate $\Delta t$ seconds.
3. **Classroom Remote Control Verification:**
   - Teacher sends broadcast announcement $\rightarrow$ instantly renders banner on student kiosk.
   - Teacher clicks `+5 mins` $\rightarrow$ student kiosk countdown extends by 300 seconds.
   - Teacher clicks "Force Submit" $\rightarrow$ student kiosk locks and displays final graded score.
4. **Code Playback Verification:**
   - Dragging the playback scrubber plays back the student's code growth over time with red markers highlighting sudden paste spikes.
5. **Traffic Light Triage Verification:**
   - Dashboard automatically classifies students into Green (On Track), Amber (Struggling/Idle), and Red (High Suspicion).
6. **AST Plagiarism Verification:**
   - Two code submissions with completely renamed variables and rearranged functions are submitted.
   - Similarity engine flags pair with $\ge 85\%$ structural match.
   - Teacher diff viewer displays matching tokens highlighted side-by-side.
7. **University Marksheet Export Verification:**
   - CSV export downloads clean, complete marksheet with zero missing values.
8. **Regression Safety:**
   - All 19 existing V1 tests must continue to pass (100% green).
