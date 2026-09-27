# Tide — Secure Lab Assessment Platform

> **"We don't claim to prevent cheating — we give teachers a live, evidence-backed flag timeline and cross-student similarity detection, with every action auditable, so a human makes the final call instead of an algorithm."**

Tide is a LAN-based, locked-down coding exam platform tailored for college computer labs. It allows multiple instructors to run isolated, proctored, auto-graded coding tests concurrently without relying on an external internet connection.

---

## 🏛️ System Architecture

```
[Student PC 1] ─┐
[Student PC 2] ─┼── LAN / Local Wi-Fi ──► [Backend Server (FastAPI)] ──► [Judge0 / SQL Engine]
[Student PC N] ─┘                                │
                                                 └──► [SQLite Database]
[Teacher PC(s)] ─────────────────────────────────┘ (Web Dashboard via LAN browser)
```

- **Student Client:** Locked-down Electron kiosk app featuring the Monaco Editor, fullscreen enforcement, DevTools & right-click blocks, shortcut intercepts, and real-time telemetry.
- **Teacher Dashboard:** Clean web interface for authoring assignments, scheduling sessions with 6-character access codes, and reviewing live behavioral flag streams.
- **Backend & Sandbox:** FastAPI server with SQLite DB, self-hosted Judge0 integration for C++, Python, and Java, plus a dedicated SQL execution and comparison pipeline.

---

## 📂 Repository Structure

```
Tide/
├── 01_PRD_Secure_Lab_Assessment.md            # Product Requirements Document
├── 02_TRD_Secure_Lab_Assessment.md            # Technical Requirements Document
├── 03_Design_Doc_Secure_Lab_Assessment.md     # System Architecture & Sequence Flows
├── 04_Database_Schema_Secure_Lab_Assessment.md# Relational Database Specifications
├── 05_Security_AntiCheat_Strategy.md          # Threat Model & Anti-Cheat Approach
├── 06_Implementation_Plan_V1_V2_Checklist.md # V1/V2 Feature Matrix & Evaluation Checklist
├── 07_V1_Detailed_Implementation_Plan.md     # 10-Hour V1 Blueprint & Technical Specs
├── server/                                    # FastAPI Backend & Grading Engine
│   ├── app/
│   │   ├── api/                               # REST & WebSocket endpoints
│   │   ├── core/                              # Config, security, DB session
│   │   ├── models/                            # SQLAlchemy models
│   │   ├── schemas/                           # Pydantic validation schemas
│   │   └── services/                          # Judge0, SQL grader, AST similarity
│   └── requirements.txt
├── client-student/                            # Electron Kiosk App
│   ├── src/                                   # Kiosk main process & Monaco UI
│   └── package.json
└── client-teacher/                            # Teacher Web Dashboard
```

---

## 🔑 Key Features

1. **Multi-Teacher Isolation:** Data access is strictly derived from the authenticated teacher's JWT context (`WHERE teacher_id = ?`) server-side.
2. **Confidential Test Grading:** Visible tests run client-visible; hidden test cases reside server-side only and are never exposed to student machines.
3. **Resilient Disconnect & Autosave:** Debounced editor autosave (every 3–5 seconds) preserves progress. Unscheduled disconnects trigger a timestamped `connection-lost` event without destroying session continuity.
4. **Behavioral Telemetry:** Live detection of window blur/focus loss, fullscreen exits, paste events, and correlated high-confidence flags (e.g. blur immediately followed by a large paste).
5. **Auditable Review Trail:** Flags are marked `open`, `dismissed`, or `escalated` with `reviewed_by` and `reviewed_at` timestamps — never deleted.
6. **AST-based Plagiarism Detection:** Syntactic tree comparison normalizes variable names to flag structural copying across submissions.

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.11+**
- **Node.js v18+ & npm**
- Optional: **Docker** (for Judge0 sandbox)

### 2. Backend Setup
```bash
cd server
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Student Kiosk Client
```bash
cd client-student
npm install
npm start
```

---

## 📄 License
MIT License.
