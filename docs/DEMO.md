# Tide — Demo Guide & Cross-Questions

The exact demo script, and answers to the questions judges ask.
**Setting up the two laptops:** [SETUP_TWO_PCS.md](SETUP_TWO_PCS.md). **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md).

**Status:** the script below has been rehearsed on one device with a simulated Windows PC talking to
the real server and live Jev (`docs/DEVELOPMENT.md` §4) — every step fired correctly. **Not yet
rehearsed** on two real Windows laptops; do that before presenting (`docs/SETUP_TWO_PCS.md`).

---

## 1. Hardware and network

| Laptop | Role | Network |
|---|---|---|
| **T** (teacher) | Tide Server + Console on a projector | **Ethernet** to S (the "lab LAN"); **Wi-Fi** on your phone hotspot for Jev |
| **S** (student) | `tide-agent.exe`, VS Code, Wireshark, Chrome | **Ethernet** to T only. Wi-Fi **off** at start |

- Use a direct Ethernet cable (USB-C adapters are fine) or a small switch. Give T a static IP
  `10.10.0.1/24` and S `10.10.0.7/24`, no gateway on the Ethernet adapter.
- On T, confirm the Ethernet adapter doesn't share internet (Windows ICS off).
- A **second phone hotspot** (or the same one) is what S "secretly" joins in cheat #2.
- Single-laptop fallback: run server and agent on T, and use T's Wi-Fi toggle for cheat #2.
  The console still shows 60 seats (1 real + 59 simulated).

## 2. Prep (5 minutes before)

1. On T: `tide-server --demo` → opens the console, creates the "CN Lab Test 3" exam with
   built-in Set A/B questions, and adds **59 simulated seats** (seat 19 red, 45 amber, 58–60 join late).
2. On S: put `D:\old\dsa_lab5.cpp` (or `Documents\old\dsa_lab5.cpp`) on disk, the "old saved code" prop. Install the Copilot
   extension in VS Code if you want the pre-flight flag.
3. On S: Chrome with ChatGPT bookmarked. Wi-Fi off.
4. Put `OPENROUTER_API_KEY` in `.env.local` on T. The console header shows **Jev live**. Without it
   the header shows "Offline heuristics" and everything except Jev auto-closing still works.

## 3. The script (~4 minutes)

| # | Say | Do | Audience sees |
|---|---|---|---|
| 0 | "60 students, one invigilator, and today's only rule is 'unplug the LAN'. Here's what happens instead." | Show console, **Lobby** | 59 seats already green, join code `K7Q2XM` |
| 1 | "A student sits at PC-07 and opens Tide." | On S: launch agent, enter code + roll | Pre-flight ticks: **Offline ✓, Copilot ✗ (flagged), 214 files indexed ✓**. Seat 7 appears **amber** |
| 2 | "Questions don't exist anywhere until now. Classroom never had them." | Click **Start** | Timer pill on S; `C:\Exam\22BCS107\` has **Set A** (odd seat). Seat 8 got Set B |
| 3 | "Real tools are fine." | Open VS Code + Wireshark on S | Nothing. Seat stays calm. Timeline shows "VS Code", "Wireshark" in grey |
| 4 | "Now the classic." | On S: open ChatGPT in Chrome | Tab closes in ~1 s, red overlay on S; seat 7 **red**: "ChatGPT — closed automatically", screenshot attached |
| 5 | "Something no keyword list knows." | Open `poe.com` or a new AI site | Console: **"ai_assistant · Jev 0.96"** → auto-closed. Point at the Jev badge |
| 6 | "The LAN-cable trick." | Turn on Wi-Fi on S, join a hotspot | Overlay on S: "Internet detected". Seat **red**: "Internet via Wi-Fi 'Redmi'" |
| 7 | "Old code from home." | Wi-Fi off. Open `D:\old\dsa_lab5.cpp`, paste it into the exam file | "Pre-exam file opened" + "Old code reused — 82 % match D:\old\dsa_lab5.cpp" |
| 8 | "The teacher sees the story, not noise." | Click seat 7 | Timeline, screenshots, code-growth chart with the paste spike |
| 9 | "Submit." | Click **Submit** on S | Seat shows ✓. **Results** tab: submissions, similarity pairs, export CSV |
| 10 | "In a real lab this is a Windows service students can't kill…" | Show the production slide | ARCHITECTURE §9 |

**Why the AI sites don't load:** S is offline, which is the point, so Chrome shows its "No internet"
page. Tide reads the address bar, so it catches the attempt anyway. Say: "even trying counts."

**Recovery:** if a step misfires, open the **Simulate** menu in the console and trigger that
event on seat 7. It goes through the same pipeline.

## 4. Cross-questions

**Q: Can't the student just close or kill the agent?**
In the demo build, yes, and the seat turns grey with an "Agent offline" flag within 10 s,
which is evidence in itself. In production the agent is a Windows **service running as SYSTEM**,
installed by IT. Students aren't admins, so they can't stop it.

**Q: What if they don't run it at all?**
Their seat is missing from the grid ("59/60 joined") and they never receive the questions. In
production it starts automatically at login.

**Q: Why not just block the internet with a firewall?**
We do in production: the service can push Windows Firewall rules. But a phone hotspot or USB
tethering creates a *new* adapter that the student controls, and students with admin rights
remove rules. Detection is still needed, and detection is what proves it happened.

**Q: Why is Jev needed? Isn't a block list enough?**
Block lists catch the famous sites. New AI sites appear weekly, and there are wrappers, renamed
apps, and tabs titled "Untitled". Jev classifies anything unknown into a fixed set of labels
with a confidence we can threshold. We auto-act only at ≥ 0.90, and only for AI, messaging or
remote-access labels. Below that it's a flag for a human.

**Q: Why Jev over GPT or Claude as a judge?**
We need a label and a trustworthy confidence number, not text. Jev is built for exactly that,
is faster (~0.1–0.7 s), and costs a fraction as much, so classifying every new window across 60
seats is affordable. Verdicts are cached, so each unique window is classified once per exam.

**Q: Doesn't sending data to Jev leak student data?**
Only window/app metadata for *ambiguous* events leaves, from the teacher laptop: process name,
window title, host. No code, no screenshots, no names.

**Q: False positives? A Windows notification steals focus…**
Allowed apps never flag. App switches are info-only. Auto-actions happen only on high-confidence
AI/messaging/remote matches. Everything else is amber for a human, and the teacher dismisses
with one click. Tide never punishes anyone. It shows evidence.

**Q: Students use VMware. Can't they run a browser inside the VM?**
The VM's internet goes through the host's adapters, so internet detection still fires. The lab
policy uses host-only VM networking, and pre-flight can read `.vmx` files to flag NAT/bridged
adapters. We can't see *inside* the guest's windows; we say that openly.

**Q: Downloading the test early from Classroom?**
The test is never on Classroom. It's uploaded to Tide and released at Start, and only to seats
that pre-flight confirmed are offline.

**Q: Old code on the PC or a pen drive?**
Pre-flight fingerprints source files already on disk. Opening one, or code in the exam folder
that matches one, raises a flag with the original path. USB insertion is flagged too. Mailed code
needs internet, which is detected.

**Q: Copying from a neighbour?**
Neighbours get different sets (odd/even). Established connections to other lab PCs are flagged.
After submission, similarity across all submissions shows matching pairs.

**Q: Local LLMs (Ollama, LM Studio)?**
On the deny list by process and PE metadata; unknown GUIs go to Jev by window title.

**Q: Incognito, a different browser, a renamed exe?**
We read the address bar through Windows UI Automation, which works in incognito and across
Chrome/Edge/Firefox/Brave/Opera. Processes match on PE metadata (original filename,
description), not just the exe name.

**Q: Timer cheating by changing the PC clock?**
The server clock is the only clock. Agents get an absolute end time and a measured offset.

**Q: Does it scale to 60 seats on one laptop?**
Yes. Each seat sends a few small JSON messages per second plus a screenshot per flag. The demo
itself runs 60 seats (59 simulated). SQLite handles this easily.

**Q: Privacy?**
Runs only during the exam, exits after submit. Collects metadata and screenshots only on flags.
Data stays on the teacher's machine.

**Q: What can't it catch?**
A phone under the desk, a friend whispering, anything inside a VM's windows, and an admin
student willing to break the agent (which leaves a grey seat). Tide shrinks the room to the three
seats worth walking to.
