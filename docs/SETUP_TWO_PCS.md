# Running Tide on two Windows PCs

- **Teacher PC** runs the server and the console (put it on the projector).
- **Student PC** runs the Tide agent and plays the student.

Both just join **the same Wi-Fi** (or the same phone hotspot). No cable, no IP settings, no
commands: everything is a double-click file in the Tide folder. Only one laptop? Do both the
teacher and student steps on it — it works the same.

> The double-click files were written for Windows but haven't been run on a real Windows PC yet.
> If one fails, the manual commands are in [DEVELOPMENT.md](DEVELOPMENT.md).

---

## 1. Once per PC (about 10 minutes)

1. **Install Python 3.12** from https://www.python.org/downloads/ . In the installer, tick
   **"Add python.exe to PATH"**. (Use 3.12 or 3.13; newer versions aren't supported by the
   Windows UI library yet.)
2. **Get the Tide folder.** Either download it from
   https://github.com/akshit2434/Tide/tree/rebuild (**Code → Download ZIP**, then unzip), or
   `git clone -b rebuild https://github.com/akshit2434/Tide.git`.
3. **Run the setup file** in the Tide folder:

   | PC | Double-click | It will |
   |---|---|---|
   | Teacher | `TEACHER - 1 Setup (once).bat` | Install Tide, then ask for your OpenRouter key (paste it, or press Enter to skip — then Tide uses keyword checks instead of Jev) |
   | Student | `STUDENT - 1 Setup (once).bat` | Install Tide |

   Setup needs internet. If Python isn't found, it opens the download page for you.

**Student PC extras for the demo** (optional but makes it better):
- Chrome, with `chatgpt.com` and `poe.com` bookmarked.
- VS Code, ideally with the GitHub Copilot extension (pre-flight flags it).
- LM Studio (https://lmstudio.ai) or Ollama, for the "local AI" step.
- The "old code" prop: copy `demo\props\dsa_lab5.cpp` into `Documents\old\`.

## 2. Every time you run it

**Teacher PC**
1. Double-click **`TEACHER - 2 Start.bat`**. The very first time, click **Yes** when Windows asks
   for permission (it opens the firewall so students can connect; it won't ask again).
2. A black window opens and stays open. It shows the **Teacher IP**. Keep it open; closing it stops Tide.
3. The console opens in the browser. PIN: **2468**.
4. On **Setup**: type a title, pick the allowed apps, attach your question PDF (Set A, and
   optionally a different Set B for even seats), press **Create & open lobby**.
5. The **Lobby** shows the **join code**. Tell the students.

**Student PC**
1. Double-click **`STUDENT - 2 Start.bat`**. (No admin needed.)
2. Type the join code, roll number and seat number, press **Join**.
   If it says **Teacher not found**, type the Teacher IP from the teacher's black window into
   **Teacher address** and press Join again.
3. Pre-flight ticks through; the seat appears in the teacher's Lobby.

**Teacher PC**: press **Start**. The PDF lands in `C:\Exam\<roll>\` on each student PC, the
student gets a timer bar, and the teacher sees the live room.

### Mock room (for a fuller-looking presentation)

Use **`TEACHER - 2 Start (mock 60-seat room).bat`** instead. When you create the test, Tide adds
59 simulated students around the real ones, with a few scripted alerts during the exam. Real
students join exactly the same way.

## 3. Before every demo (1 minute)

- [ ] Both PCs on the same Wi-Fi
- [ ] Teacher console header shows **Jev live** (if it says *Offline heuristics*, the key is missing
      or the teacher PC has no internet)
- [ ] On the student PC, delete `C:\Exam` from the last run and close Chrome / LM Studio
- [ ] Projector shows the teacher's browser full screen (F11)

Every teacher start is a **clean slate** (old tests and flags are wiped). Export results first
(**Results → Export CSV**) if you want to keep them.

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| Setup says Python isn't installed | Install Python 3.12 with "Add python.exe to PATH" ticked, then run setup again |
| Student says **Teacher not found** | Type the Teacher IP (from the teacher's black window) into **Teacher address**. If it still fails, the Wi-Fi blocks devices from seeing each other (common on public/college Wi-Fi) — use a phone hotspot or run both on one laptop |
| Console header says **Offline heuristics** | No key, or the teacher PC has no internet. Put the key in `.env.local` in the Tide folder (`OPENROUTER_API_KEY=...`) and start again |
| ChatGPT isn't closed on the student PC | Check the seat is in the console and the test is **Live** |
| Student window is blank | Install Microsoft's WebView2 runtime: https://developer.microsoft.com/microsoft-edge/webview2/ |
| A step misfires during the demo | Console → **Simulate** → pick the event for that seat. It goes through the same pipeline |
| The student agent needs to quit | It closes itself 10 s after Submit. Otherwise close its black window; the teacher sees the seat go grey, which is itself a talking point |

## 5. Optional: one .exe for students

Instead of setting up Python on every student PC, you can build `tide-agent.exe` once on any
Windows PC with Tide set up, then copy it around:
```
.venv\Scripts\python.exe -m pip install pyinstaller
cd agent
..\.venv\Scripts\pyinstaller tide-agent.spec      ->  agent\dist\tide-agent.exe
```
If SmartScreen warns on first launch: **More info → Run anyway**.
