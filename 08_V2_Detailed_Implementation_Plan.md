# Tide V2: Comprehensive Implementation Plan & Technical Blueprint

**Project:** Tide — Secure Lab Assessment Platform  
**Phase:** V2 (Advanced Anti-Cheat Intelligence, Forensic Auditing & Similarity Engine)  
**Timeline:** Checkpoint 2 (Final Evaluation & Production Hardening)  
**Architecture:** LAN-Based Client-Server (Zero External Internet Required)  

---

## 🎯 Executive Summary & V2 Positioning

Where **V1** established the resilient operational core (kiosk lockdown, server-clock start-time lockdown, polyglot grading, debounced autosave, and raw telemetry streaming), **V2** elevates Tide into an intelligent, defensible proctoring and evaluation platform designed specifically for college computing labs.

### The Core Philosophy
> *"We do not make fragile claims of 'kernel-level unbreakable lockdown.' Instead, Tide combines multi-signal telemetry correlation, crash-proof forensic downtime auditing, and AST-based cross-student structural plagiarism detection to provide instructors with indisputable, human-actionable evidence."*

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
    end

    subgraph TeacherPC["Tide Server (Teacher Laptop / Lab Host)"]
        FastAPI["FastAPI Master Controller"]
        DB[(SQLite Master DB)]
        
        subgraph V2Engines["V2 Intelligence Subsystems"]
            Correlation["Multi-Signal Correlation Engine"]
            RiskScorer["Dynamic Risk Scoring (0 - 100)"]
            ASTNormalizer["AST Tree Normalizer & Plagiarism Matrix"]
            ReconnectAuditor["Forensic Delta-t Downtime Auditor"]
            ReportGen["Disciplinary Dossier & CSV/JSON Exporter"]
        end
    end

    subgraph TeacherDashboard["Teacher Command Center (/dashboard)"]
        LiveFeed["Live Correlated Flag Stream"]
        RosterView["Student Roster & Risk Heatmap"]
        PlagView["Cross-Student Code Similarity Diff Viewer"]
        TimelineModal["Student Forensic Chronological Audit"]
        ExportActions["One-Click Export (CSV / JSON Dossier)"]
    end

    UI -->|Autosave (3s)| AutosaveSync --> FastAPI
    KioskGuard -->|Event| WSClient --> FastAPI
    ClipboardTracker -->|External Paste| WSClient
    
    FastAPI --> Correlation
    FastAPI --> ReconnectAuditor
    FastAPI --> DB
    
    Correlation --> RiskScorer
    RiskScorer --> DB
    
    DB --> ASTNormalizer
    ASTNormalizer --> PlagView
    
    FastAPI -->|Live WS Broadcast| LiveFeed
    DB --> RosterView
    DB --> TimelineModal
    DB --> ReportGen --> ExportActions
```

---

## 📦 V2 Feature Breakdown: 5 Strategic Milestones

---

### Milestone 1: Multi-Signal Correlation & Dynamic Risk Scoring

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
3. **C++ / Java Multi-Language Fallback:**
   - Token stream structural comparison (stripping identifier names and comments, comparing token operator/control flow sequences).
4. **Teacher Command Center UI: Similarity Studio:**
   - **Similarity Matrix View:** Ranked table of student pairs exceeding threshold (e.g. $\ge 70\%$).
   - **Side-by-Side Diff Modal:**
     - Left pane: Student A's code.
     - Right pane: Student B's code.
     - Synchronized line scrolling.
     - Highlighted structural similarity percentage and common logical blocks.

---

### Milestone 4: Forensic Audit Trail, Timeline Modal & Disciplinary Dossier Export

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
3. **Disciplinary Report Exporter:**
   - `GET /api/sessions/{session_id}/export?format=csv`:
     - Exports comprehensive lab marksheet: Roll No, Name, Visible Passed, Hidden Passed, Final Grade %, Flag Count, Risk Score, Plagiarism Matches.
   - `GET /api/sessions/{session_id}/export?format=json`:
     - Full forensic dump including student submissions, flag metadata, and review audit stamps for institutional records.
4. **Enhanced Flag Review:**
   - Add optional instructor notes: `PATCH /api/dashboard/flags/{flag_id}` with `{ status: "escalated", notes: "Student confirmed using unauthorized notes during viva" }`.

---

### Milestone 5: LAN Packaging, Discovery & Multi-Room Hardening

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
| **Step 1** | **Correlation Engine & Risk Scoring** | `server/app/services/heuristics.py`<br>`server/app/api/telemetry.py`<br>`client-teacher/app.js`<br>`client-teacher/styles.css` | 3 - 4 Hours |
| **Step 2** | **Crash & Reconnect Resilience** | `server/app/api/sessions.py`<br>`server/app/api/exam.py`<br>`client-student/src/renderer.js` | 2 - 3 Hours |
| **Step 3** | **AST Plagiarism & Similarity Engine** | `server/app/services/plagiarism.py`<br>`server/app/api/similarity.py`<br>`client-teacher/index.html`<br>`client-teacher/app.js` | 4 - 5 Hours |
| **Step 4** | **Forensic Timeline Modal & Exporter** | `server/app/api/reporting.py`<br>`client-teacher/index.html`<br>`client-teacher/app.js` | 3 - 4 Hours |
| **Step 5** | **LAN Auto-Discovery & Build Packaging** | `server/app/services/discovery.py`<br>`client-student/src/main.js`<br>`client-student/package.json` | 2 - 3 Hours |
| **Step 6** | **Full V2 Automated Test Suite & Rehearsal** | `server/tests/test_v2_intelligence.py`<br>`server/tests/test_v2_plagiarism.py`<br>`server/tests/test_v2_flow.py` | 2 - 3 Hours |

---

## 🧪 V2 Verification & Success Criteria

1. **Correlation Alert Verification:**
   - Student blurs window for 5s, returns, and pastes $\ge 20$ chars.
   - Server must generate a `correlated-cheat-attempt` flag within 100ms.
   - Teacher feed displays red alert card with exact blur duration and paste snippet.
2. **Reconnect Verification:**
   - Kill student kiosk process mid-exam.
   - Reopen kiosk, enter same roll number and code.
   - Kiosk restores full editor text; teacher feed logs `reconnected` with accurate $\Delta t$ seconds.
3. **AST Plagiarism Verification:**
   - Two code submissions with completely renamed variables and rearranged functions are submitted.
   - Similarity engine flags pair with $\ge 85\%$ structural match.
   - Teacher diff viewer displays matching tokens highlighted side-by-side.
4. **Audit Trail Verification:**
   - Timeline endpoint returns 100% of student actions in chronological order.
   - CSV export downloads clean, complete marksheet with zero null pointer errors.
5. **Multi-Teacher Isolation:**
   - 0% cross-talk between parallel teacher accounts verified by automated integration tests.
6. **Regression Safety:**
   - All 19 existing V1 tests must continue to pass (100% green).
