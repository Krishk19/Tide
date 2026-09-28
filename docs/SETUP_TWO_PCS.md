# Demo setup on two new Windows PCs

Follow this top to bottom on two fresh Windows 10/11 laptops. It takes about 20 minutes the
first time. After that, use the 2-minute **Before every demo** checklist at the end.

- **T** = teacher laptop (server + console, on the projector)
- **S** = student laptop (runs the Tide agent, plays the student)

Both laptops simply join **the same Wi-Fi** (or the same phone hotspot). No cable, no fixed IPs:
the demo exam allows internet and Tide monitors it. What the demo does, step by step, is in
[DEMO.md](DEMO.md).

Only have one laptop? Do sections 2–4 on it, then run the agent on the same PC with
`tide-agent --server 127.0.0.1`. Everything works the same.

---

## 1. What you need

| Item | Why |
|---|---|
| 2 Windows 10/11 laptops, admin rights on both | |
| One Wi-Fi network or phone hotspot for both | Jev (on T) and normal browsing (on S) |
| Your OpenRouter API key | Jev (the only key Tide needs) |

## 2. Install software (both PCs)

1. **Python 3.12** from https://www.python.org/downloads/ . During install tick **"Add python.exe to PATH"**.
2. **Git** from https://git-scm.com/download/win (defaults are fine).
3. **T only:** **Node.js 20 LTS** from https://nodejs.org .
4. **S only:** **Google Chrome** and **VS Code**. Optionally:
   - the *GitHub Copilot* extension in VS Code — pre-flight flags it, which demos nicely;
   - **LM Studio** (https://lmstudio.ai) or **Ollama** — for the "local AI" step.
5. The Edge **WebView2** runtime ships with Windows 10/11. If the agent window stays blank, install the
   *Evergreen Bootstrapper* from https://developer.microsoft.com/microsoft-edge/webview2/ .

Open **PowerShell** (not as admin) for the steps below.

## 3. Get the code (both PCs)

```powershell
cd $HOME
git clone https://github.com/akshit2434/Tide.git Tide
cd Tide
git checkout rebuild
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```
If PowerShell blocks the activate script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

## 4. Teacher laptop (T)

```powershell
pip install -e common -e server
cd console; npm install; npm run build; cd ..
copy .env.example .env.local
notepad .env.local        # paste your key after OPENROUTER_API_KEY=  and save
```

**Firewall** (PowerShell **as Administrator**, once) so S can reach T:
```powershell
New-NetFirewallRule -DisplayName "Tide server"    -Direction Inbound -Protocol TCP -LocalPort 8765  -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Tide discovery" -Direction Inbound -Protocol UDP -LocalPort 47800 -Action Allow -Profile Any
```
When Windows asks whether the Wi-Fi network is public or private, choose **Private**.

## 5. Student laptop (S)

Option A (simplest): **run from source**
```powershell
pip install -e common -e agent
```

Option B: **use the .exe** (build once on any Windows PC with the repo, then copy it to S)
```powershell
pip install -e common -e "agent[dev]"
cd agent; pyinstaller tide-agent.spec     # -> agent\dist\tide-agent.exe
```
If SmartScreen warns on first launch: **More info → Run anyway**.

**Demo props on S:**
```powershell
mkdir $HOME\Documents\old
copy demo\props\dsa_lab5.cpp $HOME\Documents\old\
```
In Chrome, bookmark `chatgpt.com` and `poe.com`.

## 6. Start it

**T:**
```powershell
cd $HOME\Tide; .venv\Scripts\Activate.ps1
tide-server --demo
```
The banner prints the console URL (with T's IP), the PIN (`2468`), and `Classifier: Jev via OpenRouter`.
A browser opens: enter the PIN. You see the **Lobby**, with a join code and 57/60 seats.

**S:**
```powershell
cd $HOME\Tide; .venv\Scripts\Activate.ps1
tide-agent            # or double-click tide-agent.exe
```
The Join window says **Teacher found · <T's IP>**. Enter the join code, roll `22BCS107`, seat `7`.
Pre-flight ticks: Online ✓ (monitored), Apps ✓, Copilot ! (if installed), Files indexed ✓.
Seat 07 appears in T's lobby.

If it says **Teacher not found**, start it as `tide-agent --server <T's IP>` instead (see troubleshooting).

Now run the script in [DEMO.md](DEMO.md).

## 7. Before every demo (2 minutes)

- [ ] T and S on the same Wi-Fi; the console header on T shows **Jev live**
- [ ] Fresh state on T: stop the server, delete `tide-data`, start `tide-server --demo`
- [ ] Fresh state on S: delete `C:\Exam`, close Chrome and LM Studio, then start the agent and join
- [ ] Projector shows T's browser at 100 % zoom, full screen (F11)

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| S says "Teacher not found" | Firewall rules on T (section 4); Wi-Fi set to Private; or skip discovery with `tide-agent --server <T's IP>`. Some phone hotspots stop devices seeing each other — then use a normal router, or run both on one laptop |
| Console header says **Offline heuristics** | T has no internet, or `.env.local` is missing or has a typo. Restart the server after fixing |
| ChatGPT isn't closed | Check the console shows seat 7 joined and the exam is **Live**; the agent watches from pairing onwards |
| Agent window is blank | Install the WebView2 runtime (section 2) |
| A step misfires live | Console → **Simulate** → pick the event for PC-07. It runs through the same pipeline |
| Need to quit the agent | It closes itself 10 s after Submit. Otherwise use Task Manager; T will show the seat grey, which is itself a talking point |
