# Tide — Demo Guide & Cross-Questions

The exact demo script, and answers to the questions judges ask.
**Setting up the two laptops:** [SETUP_TWO_PCS.md](SETUP_TWO_PCS.md). **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md).

**Status:** the script below has been rehearsed on one device with a simulated Windows PC talking to
the real server and live Jev (`docs/DEVELOPMENT.md` §4) — every step fired correctly. **Not yet
rehearsed** on two real Windows laptops; do that before presenting (`docs/SETUP_TWO_PCS.md`).

**Demo mode = internet allowed, monitored.** Students stay online; Tide watches every site and app
and closes the forbidden ones live. (Tide also has a stricter *internet blocked* mode for real labs —
mention it in the pitch, don't demo it.)

---

## 1. Hardware and network

| Laptop | Role | Network |
|---|---|---|
| **T** (teacher) | Tide Server + Console on a projector | Same Wi-Fi / phone hotspot as S |
| **S** (student) | Tide agent, VS Code, Chrome | Same Wi-Fi / phone hotspot as T |

- No cable, no fixed IPs. Both laptops just join the same Wi-Fi.
- If S can't find T automatically (some hotspots block devices from seeing each other), start the
  agent with `tide-agent --server <T's IP>`. `tide-server` prints T's IP when it starts.
- **One laptop is enough** if needed: run the server and the agent on the same Windows PC
  (`tide-agent --server 127.0.0.1`). The console still shows 60 seats (1 real + 59 simulated).

## 2. Prep (5 minutes before)

1. On T: `tide-server --demo` → opens the console, creates the "CN Lab Test 3" exam (internet
   allowed) with built-in Set A/B questions, and adds **59 simulated seats** (seat 45 amber, 58–60 join late).
2. On S: copy `demo\props\dsa_lab5.cpp` to `Documents\old\` — the "old saved code" prop. Install the
   Copilot extension in VS Code if you want the pre-flight flag.
3. On S: Chrome with `chatgpt.com` and `poe.com` bookmarked. Optional: LM Studio or Ollama installed
   for the "local AI" step.
4. Put `OPENROUTER_API_KEY` in `.env.local` on T. The console header shows **Jev live**. Without it
   the header shows "Offline heuristics" and everything except Jev auto-closing still works.

## 3. The script (~4 minutes)

| # | Say | Do | Audience sees |
|---|---|---|---|
| 0 | "60 students, one invigilator. Nobody can watch 60 screens. Here's Tide." | Show console, **Lobby** | 57 seats already in, join code |
| 1 | "A student sits at PC-07 and opens Tide." | On S: launch agent, enter code + roll + seat 7 | Pre-flight: **Online ✓ (monitored), Copilot ! (flagged), files indexed ✓**. Seat 7 appears **amber** |
| 2 | "Questions don't exist anywhere until now. Not on Classroom, not in email." | Click **Start** | Timer bar on S; `C:\Exam\22BCS107\` gets **Set A** (odd seat). Even seats get Set B |
| 3 | "Real tools are fine — and so is the internet." | Open VS Code on S, browse to a normal site | Nothing flagged. Timeline shows "VS Code" in grey |
| 4 | "Now the classic." | Open `chatgpt.com` in Chrome — it **loads** | Tab closes in ~1 s, red screen on S; seat 7 **red**: "ChatGPT — closed", screenshot attached |
| 5 | "Something no block list knows." | Open `poe.com` | "poe.com — AI assistant · **Jev 0.97**" → auto-closed. Point at the Jev badge |
| 6 | "It's not just websites." | Open LM Studio / Ollama (a local AI, no internet needed) | "LM Studio — closed", app killed |
| 7 | "Old code saved from home." | Open `Documents\old\dsa_lab5.cpp` in VS Code, paste it into `main.c` | "Pre-exam file opened", then "Old code reused · 100 %" with the original path |
| 8 | "The teacher sees the story, not noise." | Click seat 7 | Timeline, screenshots, Jev confidence, code-growth chart |
| 9 | "Submit." | Click **Submit** on S | Seat shows ✓. **Results** tab: submissions, similarity pairs, CSV export |
| 10 | "For stricter labs, flip one switch: internet blocked…" | Show the Setup toggle / production slide | ARCHITECTURE §9 |

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

**Q: Why allow the internet at all?**
Unplugging the LAN is what fails today: students reconnect it, use a hotspot, or grab answers
before unplugging. And blocking breaks legitimate work (docs, package installs, Wireshark labs).
Tide makes the internet safe to leave on: every site is checked, forbidden ones close instantly,
and everything else is on the teacher's timeline.

**Q: Can a lab still go fully offline?**
Yes — one switch on the Setup page. In *internet blocked* mode, questions are only released to PCs
confirmed offline, and going online (LAN, Wi-Fi, hotspot) turns the screen red until it's off.
In production the Windows service can also push firewall rules.

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
We see the VMware window, not the guest's browser. For those labs use *internet blocked* mode with
host-only VM networking, so the VM has no way out; pre-flight can also read `.vmx` files to flag
NAT/bridged adapters. We say this limit openly.

**Q: Downloading the test early from Classroom?**
The test is never on Classroom. It's uploaded to Tide and released only at Start. And Classroom,
Gmail and Drive are on the block list during the exam.

**Q: Old code on the PC or a pen drive?**
Pre-flight fingerprints source files already on disk. Opening one, or code in the exam folder
that matches one, raises a flag with the original path. USB insertion is flagged too. Mailed code
means opening Gmail/Outlook, which is closed instantly.

**Q: Copying from a neighbour?**
Neighbours get different sets (odd/even). Established connections to other lab PCs are flagged.
After submission, similarity across all submissions shows matching pairs.

**Q: Local LLMs (Ollama, LM Studio)?**
They need no internet, so this is where app monitoring matters most. Known ones are on the deny
list (by process and PE metadata, so renaming doesn't help); unknown AI apps go to Jev by window title.

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

**Q: A site that isn't AI but has answers (Stack Overflow, GeeksforGeeks)?**
Jev labels it "web lookup" and it's flagged for the teacher (not auto-closed), so the teacher
decides. A lab that wants zero lookups can add those sites to the block list or use *internet blocked* mode.

**Q: What can't it catch?**
A phone under the desk, a friend whispering, anything inside a VM's windows, and an admin
student willing to break the agent (which leaves a grey seat). Tide shrinks the room to the three
seats worth walking to.
