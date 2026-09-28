# Development: build and test everything on one machine

For contributors. Two laptops for the real demo: [SETUP_TWO_PCS.md](SETUP_TWO_PCS.md).
How it works: [ARCHITECTURE.md](ARCHITECTURE.md). Build order and code: [plans/2026-09-28-tide-demo-build.md](plans/2026-09-28-tide-demo-build.md).

## 1. Prerequisites

- Python 3.12+, Node 20+, Git
- macOS, Linux or Windows. The **real** agent needs Windows; everywhere else you use the **fake PC**
  (`--fake`), which runs the same engine, rules and UI against a simulated desktop.

## 2. Setup

```bash
git clone <repo> Tide && cd Tide
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e common -e "server[dev]" -e "agent[dev]"
(cd console && npm install)
cp .env.example .env.local                              # add OPENROUTER_API_KEY for Jev (optional)
```

## 3. Tests

```bash
pytest common/tests server/tests         # rules, fingerprints, server API/WS, Jev client (mocked)
(cd agent && pytest tests)               # watchers, engine, link, plus a full fake-student end-to-end run
(cd console && npm test)                 # room state reducer
```
None of these call the real Jev API; tests pass `_env_file=None` so your key is never used.
Windows-only smoke tests (`agent/tests/test_win_smoke.py`) are skipped on other OSes.

## 4. End to end on one device (any OS, fake PC)

Three terminals from the repo root, venv active:

```bash
# 1  server + 59 simulated seats (serves console/dist if built)
tide-server --demo

# 2  console with hot reload (or run `npm run build` once and use http://localhost:8765)
cd console && npm run dev                # http://localhost:5173, PIN 2468

# 3  a fake student PC that you drive by typing
tide-agent --fake --server 127.0.0.1
```

In the agent window, join with the code shown in the Lobby, roll `22BCS107`, seat `7`. Press **Start**
in the console. Then type these into terminal 3, one per line:

| Command | Fake student does | Console should show on PC-07 |
|---|---|---|
| `ai` | opens chatgpt.com in Chrome | **ChatGPT — closed** (Rule, Auto-closed) + screenshot |
| `code` | back to VS Code | timeline: VS Code |
| `poe` | opens poe.com (not on any list) | **poe.com — AI assistant** (Jev 0.9x, Auto-closed); with no key, an amber heuristic flag instead |
| `app` | opens an unknown "NoteGPT" app | **notegpt — AI assistant** (Jev, killed) |
| `wifi` / `wifi off` | goes online / offline | Timeline event only (the demo exam allows internet). In an exam created with **Internet: Blocked**: **Internet via Wi-Fi "Redmi Note"** and a red screen until `wifi off` |
| `old` | opens `old/dsa_lab5.cpp` in VS Code | **Pre-exam file opened** |
| `paste` | pastes the old file into `main.c` | **Old code reused · 100%** within 30 s |
| `usb` | plugs in a pen drive | **USB drive inserted** |
| `clip` | copies a big chunk of old code | **Paste matches old file** |

No window server (CI, SSH)? Use a terminal-only agent:
`tide-agent --fake --headless --server 127.0.0.1 --code <CODE> --roll 22BCS107 --seat 7`.
It prints every UI event (`[block] ChatGPT — closed`, …) instead of showing windows.

## 5. End to end on one Windows PC (real agent)

```powershell
tide-server --demo
tide-agent --server 127.0.0.1
```
Then really do the cheats: open chatgpt.com in Chrome (it loads, then closes), open `poe.com`,
open `demo\props\dsa_lab5.cpp` in VS Code and paste it into `main.c`, and so on. The demo exam allows
internet, so one online PC runs the whole demo with Jev live. (Only an exam set to **Internet: Blocked**
needs the student PC offline — test that mode with two machines.)

## 6. Where things live

| Want to change… | File |
|---|---|
| Allowed apps, presets, blocked apps/sites, AI extensions, internet mode | `common/tide_common/policy.py` |
| What counts as a violation (rules) | `common/tide_common/rules.py` |
| Jev prompt and labels | `server/tide_server/classify/jev.py` |
| Auto-act threshold, PIN, ports | `server/tide_server/config.py` (env `TIDE_*`) |
| Demo room: fake seats and scripted events | `server/tide_server/simulate.py` |
| Agent screens | `agent/tide_agent/ui/web/*.html` |
| Console screens | `console/src/pages`, `console/src/components` |
| Visual reference | `design/mock-ui.html` |

## 7. Debugging

- Server data is in `tide-data/`: `tide.db` (SQLite), `shots/`, `submissions/`. Delete the folder to reset.
- `sqlite3 tide-data/tide.db "select seat_id,title,source,confidence from flag order by id desc limit 10"`
- The agent keeps unsent messages in `%LOCALAPPDATA%\Tide\outbox-<roll>.jsonl` (or `~/Tide/…`).
- `python agent/scripts/win_smoke.py` (Windows) prints what the agent sees every second.
