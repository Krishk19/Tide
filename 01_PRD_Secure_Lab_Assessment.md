# Product Requirements Document (PRD)
## Secure Lab Assessment Platform

**Version:** 1.0 (Hackathon MVP)
**Status:** Draft for submission

---

## 1. One-line pitch
A LAN-based, locked-down coding exam platform for college labs that lets multiple teachers run proctored, auto-graded coding tests — with a live behavioral flag feed instead of a false promise of "cheat-proof."

## 2. Problem statement
College coding labs run assessments with no reliable way to:
- Prevent students from looking up answers (AI tools, browser extensions, notes) mid-test.
- Grade code against test cases beyond the visible/sample ones (students hardcode outputs for known cases).
- Give teachers real-time visibility into suspicious behavior instead of discovering it after the fact.
- Let multiple teachers, running parallel sessions in the same building, manage their own batches without seeing each other's data.

Existing solutions either require internet-dependent cloud proctoring (not usable in labs with restricted/no internet) or full commercial lockdown software (not deployable by a student team, not affordable, not customizable to a specific course's test format).

## 3. Target users
- **Teacher / Instructor** — authors assignments, schedules sessions, monitors live flags, reviews evidence, grades.
- **Student** — joins via access code, solves in a locked environment, submits code for auto-grading.
- **Lab environment constraints (confirmed):** Windows PCs (~90%), single monitor per station, phones collected before the test, LAN-interconnected machines, internet not required or assumed.

## 4. Goals
- Deliver a working coding-test flow: assignment creation → scheduled session → student join → locked exam environment → auto-graded submission (C++, Python, Java, SQL).
- Give teachers a live, evidence-backed behavioral flag feed (not automated penalties).
- Support multiple teachers running independent, isolated sessions concurrently in the same building.
- Keep hidden test cases genuinely hidden (server-side only, never shipped to student disk).

## 5. Non-goals (explicitly out of scope for MVP)
- **OS kernel-level anti-cheat / true Alt-Tab prevention.** Not deployable in a real college (IT would never approve kernel-level surveillance software), not buildable in hackathon time, and not necessary given the lab's single-monitor + no-phone constraints already close the main gap this would address.
- **ML-based typing-cadence anomaly detection.** No training data available; rule-based thresholds deliver most of the value for a fraction of the effort.
- **Cross-session gradebook / historical analytics across multiple past exams.** Parked as future work — MVP is session-scoped.
- **Automated flag-based penalties** (auto-lock, auto-submit, auto-fail). The system flags; a human teacher decides.

## 6. Core user flows

### 6.1 Teacher: author an assignment (days ahead of the test)
Teacher logs in → creates assignment (problem statement, starter code, visible test cases, hidden test cases) → saves. Assignment is reusable across multiple future sessions.

### 6.2 Teacher: run a session (day of the test)
Teacher logs in from any LAN PC → picks a saved assignment → sets scheduled start time → generates a 6-character access code → shares code with the batch.

### 6.3 Student: take the exam
Student launches the locked-down kiosk app → enters access code → waits (exam is inaccessible until the scheduled start time, enforced server-side) → on start, gets the problem + Monaco code editor, fullscreen, no other app access → runs code against visible test cases → submits → server grades against visible + hidden test cases → result (pass/fail per test) returned, hidden inputs never revealed.

### 6.4 Teacher: live monitoring
Teacher's dashboard shows a real-time flag feed per student: focus-lost/regained, fullscreen-exit, paste events, disconnects/reconnects — correlated (e.g., focus-lost immediately followed by a large paste is weighted as high-confidence). Teacher can mark flags reviewed/dismissed/escalated; nothing is auto-deleted.

## 7. Feature list (priority order)

**Tier 1 — Core (nothing works without these)**
1. Teacher login (multi-teacher, isolated accounts)
2. Assignment authoring (reusable, days-ahead)
3. Session creation (assignment + schedule + access code)
4. Student join + server-enforced start-time lock
5. Locked-down kiosk exam environment (fullscreen, no chrome, DevTools disabled, right-click disabled)
6. Auto-grading: C++, Python, Java via self-hosted Judge0, hidden tests server-side only
7. SQL grading (separate result-set comparison pipeline)

**Tier 2 — Differentiators (what gets attention)**
8. Live teacher dashboard — real-time flag feed, continuous per-student timeline (including disconnect/reconnect with time-gap)
9. Correlated flag weighting (focus-lost + immediate large paste = high-confidence)
10. AST-based cross-student code similarity detection (catches copied logic post-renaming)
11. Strict multi-teacher data isolation (every query scoped server-side to the logged-in teacher)
12. Autosave (debounced) — code state preserved even on abrupt disconnect
13. Flag status tracking (open / dismissed / escalated, with reviewer + timestamp — audit trail, never hard-deleted)

**Tier 3 — Stretch (if ahead of schedule)**
14. Native Win32 foreground-window polling (catches Ctrl+Alt+Del → Task Manager switches)
15. Per-student end-of-exam aggregate risk score
16. Parameterized hidden test values per session (only relevant if one batch is ever split across same-day shifts on the same assignment — not the current usage pattern, so deprioritized)

## 8. Success criteria for the hackathon demo
- End-to-end flow works live: create assignment → schedule → student joins from a second machine → locked exam → submit → graded against hidden tests → flags appear live on teacher dashboard.
- At least one deliberate "cheat attempt" (alt-tab, paste from another window) is demonstrated and correctly flagged in real time.
- Two teacher accounts, two concurrent sessions, verified to see only their own data.

## 9. Explicit product framing (for judges/pitch)
"We don't claim to prevent cheating — we give teachers a live, evidence-backed flag timeline and cross-student similarity detection, with every action auditable, so a human makes the final call instead of an algorithm."
