# Security & Anti-Cheat Strategy
## Secure Lab Assessment Platform

---

## 1. Threat model — what we defend against, and what we explicitly don't

| Threat | In scope? | Mitigation |
|---|---|---|
| Tab-switch / alt-tab to another app | Yes | Electron `blur`/`focus` window events → `focus-lost`/`focus-regained` flags |
| Exiting fullscreen | Yes | `leave-full-screen` handler re-forces fullscreen + flags the event (note: cannot be *prevented*, only detected — OS/Chromium spec reserves Esc-to-exit-fullscreen for the user) |
| Pasting external code/answers | Yes | Paste event captured (size, timing) — a single large paste is a stronger cheating signal than a window-switch alone |
| Correlated cheating (switch away, then paste on return) | Yes | Dashboard weights a paste immediately following a focus-lost event as high-confidence, distinct from either signal alone |
| Copy-pasting between students / plagiarized submissions | Yes | AST-based cross-student similarity detection (survives variable renaming) |
| Second monitor / second device for lookup | **Out of scope by environment, not by design** | Lab environment confirmed single-monitor, phones collected before test — this vector is closed by physical lab policy, not by software |
| Browser extension rendering an AI assistant inline (no focus change) | Yes | Root cause of moving from browser-tab to **Electron kiosk app** — no extension surface exists in a non-Chrome shell |
| Opening DevTools to inspect/disable telemetry JS | Yes | `devTools: false` at the Chromium-embed level (not page-level JS, which is itself disableable from DevTools) + input-event blocking of F12/Ctrl+Shift+I/J/C + disabled right-click |
| Killing the app via Task Manager to work elsewhere, relaunching later | Partially | Disconnect is flagged (`connection-lost`), autosave preserves code state, reconnect is flagged with time-gap — teacher sees the full timeline and infers likely cause; **system does not attempt automated intent classification** |
| Ctrl+Alt+Del → Task Manager switch | **Known gap, Tier 3** | Not caught by Electron's own `blur` (OS-reserved combo); native Win32 foreground-window polling would close this, deferred as stretch |
| Local/offline AI tool used via a full app switch | Yes | Caught the same way as any other focus-lost event — using it still requires switching away from the kiosk window |
| OS-level surveillance (full process list, kernel monitoring) | **Explicitly not attempted** | Undeployable in a real college (IT would never approve), not buildable in hackathon time, and not necessary given the above mitigations already close the practical gaps for this lab environment |

## 2. Why detection-and-audit, not prevention-and-punishment
No software running in user-mode (i.e., without a signed kernel driver and admin-level install) can *actually prevent* a determined student from switching away, and claiming otherwise doesn't survive a technical question from a judge or an IT reviewer. Two consequences follow:

1. **The product promise is: visibility + evidence, not immunity.** "Flag it and let a human teacher decide" is both more honest and more useful — an automated false positive (a Windows Defender toast stealing focus for 2 seconds) would be far worse if it triggered an auto-fail than if it just added one line to a review queue.
2. **Every flag is retained, timestamped, and status-tracked — never silently deleted.** If a student later disputes a grading decision, the full behavioral timeline is available as evidence of what was actually observed and what a teacher decided to do about it.

## 3. Hidden test case confidentiality
- Hidden test cases are stored server-side only (`assignments.hidden_test_cases`) and are never transmitted to, or cached on, the student's machine.
- Grading happens via a request to the local Judge0 instance / SQL pipeline on the server; the student client only ever receives a pass/fail result per test, never the hidden input/expected-output pair itself.
- **Known residual limitation:** if the same assignment were ever reused across two same-day shifts of the same batch, students from the earlier shift could describe (not literally leak the file, but relay) the hidden tests to the later shift. Confirmed not to be the current usage pattern (each batch gets a distinct assignment) — flagged here so the assumption is documented, not silently relied upon.

## 4. Multi-teacher isolation as a security property
Teacher data isolation is enforced structurally: every dashboard query filters by the `teacher_id` embedded in the authenticated session token, never by a session ID supplied in the client request. This means a teacher cannot access another teacher's data even by directly manipulating request parameters — the access control lives in how the query is constructed server-side, not in a UI-level restriction that a modified request could bypass.

## 5. Flag lifecycle and audit trail
- Flags are created with `status = open`.
- A teacher can mark a flag `dismissed` (reviewed, no action) or `escalated` (reviewed, action taken) — both set `reviewed_by` and `reviewed_at`.
- Flags are **never hard-deleted.** This costs nothing extra to build (a status enum instead of a delete call) and preserves a defensible record if a grading decision is ever questioned.

## 6. What we tell judges directly, unprompted
- We do not claim to be cheat-proof.
- We do not claim OS-level prevention.
- Our defensible claim: a live, timestamped, correlated behavioral flag feed with full audit trail, scoped correctly across multiple concurrent teachers, backed by genuinely server-side-hidden grading.
