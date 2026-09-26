# System Design Document
## Secure Lab Assessment Platform

---

## 1. High-level architecture

```mermaid
flowchart TB
    subgraph Lab LAN [College Lab — LAN, no internet required]
        subgraph Server [Server Machine — any lab PC]
            API[Backend API<br/>FastAPI / Node]
            DB[(SQLite)]
            Judge[Judge0<br/>Docker container]
            WS[WebSocket hub]
            API --> DB
            API --> Judge
            API --> WS
        end

        subgraph StudentPCs [Student PCs]
            K1[Electron Kiosk App<br/>+ Monaco Editor]
            K2[Electron Kiosk App<br/>+ Monaco Editor]
        end

        subgraph TeacherPCs [Teacher PCs — any LAN machine]
            D1[Browser Dashboard<br/>Teacher A]
            D2[Browser Dashboard<br/>Teacher B]
        end

        K1 <--> API
        K2 <--> API
        D1 <--> API
        D2 <--> API
        K1 -.flags.-> WS
        K2 -.flags.-> WS
        WS -.live push.-> D1
        WS -.live push.-> D2
    end
```

## 2. Component responsibilities

| Component | Responsibility |
|---|---|
| Electron Kiosk App | Fullscreen lockdown, DevTools/right-click disabled, Monaco editor, emits focus/blur/paste/fullscreen-exit events, debounced autosave |
| Backend API | Auth, assignment/session CRUD, access-code validation, start-time gate, routes submissions to Judge0/SQL pipeline, scopes all teacher queries by `teacher_id` |
| Judge0 (Docker) | Sandboxed execution for C++/Python/Java against visible + hidden test cases, resource/time limits |
| SQL Grading Pipeline | Separate service: loads schema+seed, runs student query, normalizes and compares result sets order-agnostically |
| WebSocket Hub | Routes flag events from a student session to only the teacher who owns that session |
| SQLite DB | Source of truth: teachers, assignments, sessions, students_in_session, submissions, flags |
| Browser Dashboard | Teacher-only, non-kiosk, login-gated, live flag feed + assignment/session management |

## 3. Key sequence flows

### 3.1 Assignment authoring → session creation → student join
```mermaid
sequenceDiagram
    participant T as Teacher
    participant API as Backend API
    participant DB as SQLite

    Note over T,DB: Days before the test
    T->>API: POST /assignments (problem, tests)
    API->>DB: INSERT assignment (teacher_id)

    Note over T,DB: Day of the test
    T->>API: POST /sessions (assignment_id, start_time)
    API->>DB: INSERT session (teacher_id, access_code)
    API-->>T: access_code

    participant S as Student (Kiosk App)
    S->>API: POST /sessions/join (access_code)
    API->>DB: lookup session by code
    API->>DB: INSERT students_in_session (session_id)
    API-->>S: student_session_id
```

### 3.2 Locked exam start + submission grading
```mermaid
sequenceDiagram
    participant S as Student (Kiosk App)
    participant API as Backend API
    participant J as Judge0

    loop until start_time reached
        S->>API: GET /exam/state
        API-->>S: locked (server clock check)
    end
    API-->>S: unlocked, problem + starter code

    S->>API: POST /exam/submit (code, language)
    API->>J: run against visible + hidden tests
    J-->>API: pass/fail per test (no hidden inputs returned)
    API-->>S: result (visible details only)
```

### 3.3 Live flag pipeline
```mermaid
sequenceDiagram
    participant S as Student (Kiosk App)
    participant WS as WebSocket Hub
    participant DB as SQLite
    participant D as Teacher Dashboard

    S->>WS: focus-lost (ts)
    WS->>DB: INSERT flag (student_session_id, type, ts, status=open)
    WS-->>D: live push (teacher_id match only)

    S->>WS: paste event (size, ts)
    WS->>DB: INSERT flag
    Note over WS,D: If paste follows focus-lost closely,<br/>dashboard renders as correlated / high-confidence

    D->>API: PATCH /dashboard/flags/:id (status=dismissed)
    API->>DB: UPDATE flag (status, reviewed_by, reviewed_at)
```

### 3.4 Disconnect → autosave → reconnect
```mermaid
sequenceDiagram
    participant S as Student (Kiosk App)
    participant API as Backend API
    participant DB as SQLite

    loop every few seconds
        S->>API: POST /exam/autosave (code)
        API->>DB: UPDATE submissions.code
    end

    Note over S,API: Connection drops (crash / kill / network blip)
    API->>DB: INSERT flag (type=connection-lost, ts, last_autosaved_code ref)

    Note over S,API: Student relaunches app, rejoins with same code
    S->>API: POST /sessions/join (access_code)
    API->>DB: INSERT flag (type=reconnected, ts, gap = ts - connection-lost.ts)
    API-->>S: resume with last autosaved code
```

## 4. Design decisions and rationale

| Decision | Rationale |
|---|---|
| LAN client-server, not fully offline single-device | A single-device app would ship hidden test cases to the student's own disk — decryptable locally, since grading must happen locally. LAN keeps hidden tests server-side, genuinely hidden. |
| Electron kiosk, not browser tab | Browser tabs can't reliably disable DevTools (any page-level JS block is itself disableable from DevTools) and can't block browser extensions (an AI-copilot extension can render inline with zero focus change, defeating tab-switch detection entirely). |
| Detection + audit trail, not prevention/auto-penalty | True prevention requires kernel-level drivers — undeployable in a real college, unbuildable in hackathon time. A human-reviewed flag feed is honest about this limit and is what a real institution would actually adopt. |
| Flags marked "dismissed," never deleted | Preserves an audit trail for disputes; costs nothing extra to implement (a status enum vs. a delete call). |
| Continuous per-student flag timeline (not reset on reconnect) | The sequence of events around a disconnect (preceded by a tab-switch? followed by a large paste on return?) is what lets a teacher infer cause — the system doesn't need to diagnose intent, just preserve the evidence. |
| Teacher-scoping derived from JWT, never from a client-supplied session ID | Prevents one teacher from viewing another's data by editing a request parameter — the isolation must be structural (server-side), not policy-based. |

## 5. Open items / explicit limitations
- `window-all-closed` guard logic not yet defined — decide whether reconnect is always allowed (recommended) or requires teacher unlock.
- Parameterized hidden test values per session — only needed if a single assignment is ever reused across multiple same-day shifts of the same batch (currently not the case; deprioritized to Tier 3).
- Native Win32 foreground-window polling (Ctrl+Alt+Del → Task Manager case) — not covered by Electron's own `blur` event; Tier 3 stretch.
