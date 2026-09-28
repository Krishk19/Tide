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
| **T** (teacher) | Tide server + console on the projector | Same Wi-Fi / phone hotspot as S |
| **S** (student) | Tide agent, VS Code, Chrome | Same Wi-Fi / phone hotspot as T |

- No cable, no IP settings, no commands: both PCs use the double-click files (see
  [SETUP_TWO_PCS.md](SETUP_TWO_PCS.md), or `START HERE.txt` in the Tide folder).
- **One laptop is enough** if needed: start the teacher and the student on the same PC.

## 2. Prep (5 minutes before)

1. **T:** double-click `TEACHER - 2 Start.bat`. Log in (PIN 2468). The header should say **Jev live**.
2. **T:** on **Setup**, type a title, attach your question PDF (Set A; optionally a different Set B
   for even seats), keep **Internet: Allowed · monitored**, press **Create & open lobby**.
3. **S:** copy `demo\props\dsa_lab5.cpp` into `Documents\old\` (the "old saved code" prop), delete
   `C:\Exam` from any earlier run, have Chrome (with `chatgpt.com` and `poe.com` bookmarked), VS Code
   and optionally LM Studio ready.
4. **S:** double-click `STUDENT - 2 Start.bat` but **don't join yet** — you'll join live.

Want the room to look like a full lab? Start T with `TEACHER - 2 Start (mock 60-seat room).bat`
instead: 59 simulated students appear when you create the test, and a few of them raise scripted
alerts during the exam. Without it, the room shows only your real student(s).

## 3. The script (~4 minutes)

| # | Say | Do | Audience sees |
|---|---|---|---|
| 0 | "60 students, one invigilator. Nobody can watch 60 screens. Here's Tide." | Show the console **Lobby** | The join code, an empty room waiting for students |
| 1 | "A student sits at PC-07 and opens Tide." | On S: type the code, roll, seat 7, **Join** | Pre-flight on S: **Online ✓ (monitored), Copilot ! (flagged), files indexed ✓**. Seat 07 appears on T, **amber** |
| 2 | "The question paper doesn't exist anywhere until now. Not on Classroom, not in email." | T: **Start** | Timer bar on S; the PDF lands in `C:\Exam\22BCS107\` (Set A, odd seat). T switches to the live room and alert feed |
| 3 | "Real tools are fine — and so is the internet." | S: open VS Code, browse a normal site | Nothing flagged. Seat 07's timeline shows "VS Code" in grey |
| 4 | "Now the classic." | S: open `chatgpt.com` — it **loads** | Tab closes in ~1 s, red screen on S; T: seat 07 **red**, feed says "ChatGPT — closed · Auto-closed", screenshot attached |
| 5 | "Something no block list knows." | S: open `poe.com` | Feed: "poe.com — AI assistant · **Jev 0.97** · Auto-closed". Point at the Jev badge |
| 6 | "It's not just websites." | S: open LM Studio / Ollama (local AI, no internet needed) | "LM Studio — closed", app killed |
| 7 | "Old code saved from home." | S: open `Documents\old\dsa_lab5.cpp` in VS Code, copy it into a new `main.c` in `C:\Exam\22BCS107\` | "Pre-exam file opened", then "Old code reused · 100 %" with the original path (within 30 s) |
| 8 | "The teacher sees the story, not noise." | T: click seat 07 | Timeline, screenshots, Jev confidence, code-growth chart |
| 9 | "Submit." | S: **Submit** in the timer bar | Seat shows ✓. **Results** tab: submission, flags, CSV export |
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
can run a full 60-seat room (the mock-room option adds 59 simulated seats). SQLite handles this easily.

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
