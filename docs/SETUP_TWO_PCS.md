# Demo setup on two new Windows PCs

Follow this top to bottom on two fresh Windows 10/11 laptops. It takes about 30 minutes the
first time. After that, use the 2-minute **Before every demo** checklist at the end.

- **T** = teacher laptop (server + console, on the projector)
- **S** = student laptop (runs the Tide agent, plays the student)

What the demo does, step by step, is in [DEMO.md](DEMO.md).

---

## 1. What you need

| Item | Why |
|---|---|
| 2 Windows 10/11 laptops, admin rights on both | |
| 1 Ethernet cable (plus USB-C/USB-Ethernet adapters if the laptops have no port) | The "lab LAN" between T and S |
| A phone hotspot | T's internet for Jev, and S's "secret" hotspot in cheat #2 |
| Your OpenRouter API key | Jev (the only key Tide needs) |

## 2. Install software (both PCs)

1. **Python 3.12** from https://www.python.org/downloads/ . During install tick **"Add python.exe to PATH"**.
2. **Git** from https://git-scm.com/download/win (defaults are fine).
3. **T only:** **Node.js 20 LTS** from https://nodejs.org .
4. **S only:** **Google Chrome** and **VS Code**. Optionally install the *GitHub Copilot* extension in
   VS Code; pre-flight will flag it, which demos nicely.
5. The Edge **WebView2** runtime ships with Windows 10/11. If the agent window stays blank, install the
   *Evergreen Bootstrapper* from https://developer.microsoft.com/microsoft-edge/webview2/ .

Open **PowerShell** (not as admin) for the steps below.

## 3. Get the code (both PCs)

```powershell
cd $HOME
git clone <your Tide repo URL> Tide
cd Tide
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

**Firewall** (PowerShell **as Administrator**, once):
```powershell
New-NetFirewallRule -DisplayName "Tide server"    -Direction Inbound -Protocol TCP -LocalPort 8765  -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Tide discovery" -Direction Inbound -Protocol UDP -LocalPort 47800 -Action Allow -Profile Any
```

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

## 6. Wire the network

1. Connect T and S with the Ethernet cable.
2. Give both Ethernet adapters fixed addresses (PowerShell **as Administrator**; check the adapter
   name with `Get-NetAdapter`, it's usually "Ethernet"):
   ```powershell
   # on T
   New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 10.10.0.1 -PrefixLength 24
   # on S
   New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 10.10.0.7 -PrefixLength 24
   ```
   Don't set a gateway: the cable must not carry internet.
3. When Windows asks, mark the Ethernet network **Private** on both, or run
   `Set-NetConnectionProfile -InterfaceAlias "Ethernet" -NetworkCategory Private`.
4. **T:** join your phone hotspot over Wi-Fi (for Jev).
5. **S:** turn **Wi-Fi off**. Make sure S has joined the phone hotspot at least once before, so that in
   cheat #2 it reconnects in one click.
6. Check: on S, `ping 10.10.0.1` replies. On S, `curl.exe -I https://openrouter.ai` must **fail** (S is offline).

## 7. Start it

**T:**
```powershell
cd $HOME\Tide; .venv\Scripts\Activate.ps1
tide-server --demo
```
The banner prints the console URL, the PIN (`2468`), and `Classifier: Jev via OpenRouter`.
A browser opens: enter the PIN. You see the **Lobby**, with a join code and 57/60 seats.

**S:**
```powershell
cd $HOME\Tide; .venv\Scripts\Activate.ps1
tide-agent            # or double-click tide-agent.exe
```
The Join window says **Teacher found · 10.10.0.1**. Enter the join code, roll `22BCS107`, seat `7`.
Pre-flight ticks: Offline ✓, Apps ✓, Copilot ! (if installed), Files indexed ✓.
Seat 07 appears in T's lobby.

Now run the script in [DEMO.md](DEMO.md).

## 8. Before every demo (2 minutes)

- [ ] T: Wi-Fi on the phone hotspot, and the console header shows **Jev live**
- [ ] S: Wi-Fi **off**, Ethernet connected, `ping 10.10.0.1` works
- [ ] Fresh state on T: stop the server, delete `tide-data`, start `tide-server --demo`
- [ ] Fresh state on S: delete `C:\Exam`, close Chrome, then start the agent and join
- [ ] Projector shows T's browser at 100 % zoom, full screen (F11)

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| S says "Teacher not found" | Firewall rules on T (step 4); both networks Private; or skip discovery with `tide-agent --server 10.10.0.1` |
| Pre-flight on S says **Internet on** | S still has Wi-Fi or another adapter with internet. Turn it off; pre-flight re-checks every 5 s |
| Console header says **Offline heuristics** | T has no internet, or `.env.local` is missing or has a typo. Restart the server after fixing |
| Red "Internet detected" screen won't go away on S | Turn S's Wi-Fi off; it clears within ~5 s |
| Agent window is blank | Install the WebView2 runtime (section 2) |
| A step misfires live | Console → **Simulate** → pick the event for PC-07. It runs through the same pipeline |
| Need to quit the agent | It closes itself 10 s after Submit. Otherwise use Task Manager; T will show the seat grey, which is itself a talking point |
