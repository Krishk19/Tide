// Tide Student Kiosk Renderer Process
let state = {
  serverUrl: 'http://localhost:8000',
  studentSessionId: null,
  sessionId: null,
  studentName: '',
  studentIdentifier: '',
  accessCode: '',
  countdownInterval: null,
  autosaveTimer: null,
  ws: null,
  currentLanguage: 'python',
  isSubmitted: false,
};

// Auto-detect server URL from current location or localStorage
if (window.location.protocol.startsWith('http')) {
  state.serverUrl = window.location.origin;
} else if (localStorage.getItem('tide_server_url')) {
  state.serverUrl = localStorage.getItem('tide_server_url');
}

window.addEventListener('DOMContentLoaded', () => {
  const serverHostInput = document.getElementById('serverHostInput');
  if (serverHostInput) {
    serverHostInput.value = state.serverUrl;
  }

  const toggleSettingsBtn = document.getElementById('toggleServerSettingsBtn');
  const settingsContainer = document.getElementById('serverSettingsContainer');
  if (toggleSettingsBtn && settingsContainer) {
    toggleSettingsBtn.addEventListener('click', () => {
      const isHidden = settingsContainer.style.display === 'none';
      settingsContainer.style.display = isHidden ? 'block' : 'none';
    });
  }
});

// Internal Clipboard Tracker:
// Allows copying/pasting within the exam window without generating flags!
const internalClipboard = new Set();

document.addEventListener('copy', () => {
  const selectedText = window.getSelection().toString();
  if (selectedText && selectedText.trim()) {
    internalClipboard.add(selectedText.trim());
    console.log('[Internal Clipboard] Text copied inside exam window:', selectedText.substring(0, 30));
  }
});

document.addEventListener('cut', () => {
  const selectedText = window.getSelection().toString();
  if (selectedText && selectedText.trim()) {
    internalClipboard.add(selectedText.trim());
    console.log('[Internal Clipboard] Text cut inside exam window:', selectedText.substring(0, 30));
  }
});

// Fullscreen Detection & Enforcement Utilities
async function checkIsFullScreen() {
  if (window.electronAPI && window.electronAPI.isFullScreen) {
    return await window.electronAPI.isFullScreen();
  }
  const isDocFullscreen = document.fullscreenElement != null;
  const isWindowMaximized = (window.innerHeight >= screen.height - 25 && window.innerWidth >= screen.width - 25);
  return isDocFullscreen || isWindowMaximized;
}

async function enforceFullScreen() {
  if (window.electronAPI && window.electronAPI.setFullScreen) {
    await window.electronAPI.setFullScreen();
    return true;
  }
  if (document.documentElement.requestFullscreen) {
    try {
      await document.documentElement.requestFullscreen();
      return true;
    } catch (e) {
      console.warn('requestFullscreen request rejected:', e);
      return false;
    }
  }
  return false;
}

// DOM Elements
const views = {
  join: document.getElementById('joinView'),
  countdown: document.getElementById('countdownView'),
  exam: document.getElementById('examView'),
  submitted: document.getElementById('submittedView'),
};

const sessionBadge = document.getElementById('sessionBadge');
const studentInfoBadge = document.getElementById('studentInfoBadge');
const autosaveIndicator = document.getElementById('autosaveIndicator');
const autosaveText = document.getElementById('autosaveText');
const headerSubmitBtn = document.getElementById('headerSubmitBtn');

// Modals
const fullscreenGateModal = document.getElementById('fullscreenGateModal');
const enableFullscreenBtn = document.getElementById('enableFullscreenBtn');
const fullscreenLockoutOverlay = document.getElementById('fullscreenLockoutOverlay');
const resumeFullscreenBtn = document.getElementById('resumeFullscreenBtn');

// View Switching
function switchView(viewName) {
  Object.values(views).forEach((v) => v.classList.remove('active'));
  if (views[viewName]) {
    views[viewName].classList.add('active');
  }
}

// Telemetry Sender
function sendTelemetry(type, metadata = {}) {
  // Suppress all flags if student has already submitted
  if (state.isSubmitted) return;

  const payload = {
    student_session_id: state.studentSessionId,
    type: type,
    metadata: metadata,
    ts: new Date().toISOString(),
  };

  // 1. Try WebSocket
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(payload));
  } else if (state.studentSessionId) {
    // 2. HTTP fallback
    fetch(`${state.serverUrl}/api/telemetry/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {});
  }
}

// Connect WebSocket
function connectTelemetryWebSocket() {
  if (!state.studentSessionId) return;
  const wsUrl = state.serverUrl.replace(/^http/, 'ws') + `/ws/student/${state.studentSessionId}`;
  try {
    state.ws = new WebSocket(wsUrl);
    state.ws.onopen = () => console.log('Telemetry WebSocket connected.');
    state.ws.onclose = () => console.log('Telemetry WebSocket closed.');
    state.ws.onerror = (e) => console.log('Telemetry WebSocket error:', e);
  } catch (err) {
    console.error('WebSocket connection failed:', err);
  }
}

// Handle Fullscreen Exit Lockout (Pause screen until resumed)
function handleFullscreenExit() {
  if (state.isSubmitted) return;
  const isExamActive = views.exam.classList.contains('active') || views.countdown.classList.contains('active');
  if (state.studentSessionId && isExamActive) {
    sendTelemetry('fullscreen-exit', { source: 'window-exit' });
    if (fullscreenLockoutOverlay) {
      fullscreenLockoutOverlay.style.display = 'flex';
    }
  }
}

// Electron Main Process IPC Telemetry Hook
if (window.electronAPI && window.electronAPI.onKioskEvent) {
  window.electronAPI.onKioskEvent((event) => {
    if (state.isSubmitted) return;
    console.log('Kiosk Security Event:', event);
    if (event.type === 'fullscreen-exit') {
      handleFullscreenExit();
    } else if (state.studentSessionId) {
      sendTelemetry(event.type, { source: 'electron-main' });
    }
  });
} else {
  // Web Browser / Kiosk Fallback listeners (works in Chrome, Edge, Firefox)
  window.addEventListener('blur', () => {
    if (state.isSubmitted) return;
    console.log('[Browser Telemetry] focus-lost');
    if (state.studentSessionId) sendTelemetry('focus-lost', { source: 'browser-blur' });
  });

  window.addEventListener('focus', () => {
    if (state.isSubmitted) return;
    console.log('[Browser Telemetry] focus-regained');
    if (state.studentSessionId) sendTelemetry('focus-regained', { source: 'browser-focus' });
  });

  document.addEventListener('visibilitychange', () => {
    if (state.isSubmitted) return;
    if (document.hidden) {
      console.log('[Browser Telemetry] tab-switched-out');
      if (state.studentSessionId) sendTelemetry('focus-lost', { source: 'tab-hidden' });
    } else {
      console.log('[Browser Telemetry] tab-switched-in');
      if (state.studentSessionId) sendTelemetry('focus-regained', { source: 'tab-visible' });
    }
  });

  document.addEventListener('fullscreenchange', () => {
    if (state.isSubmitted) return;
    if (!document.fullscreenElement) {
      console.log('[Browser Telemetry] fullscreen-exit');
      handleFullscreenExit();
    }
  });
}

// Resume Fullscreen Button Handler
if (resumeFullscreenBtn) {
  resumeFullscreenBtn.addEventListener('click', async () => {
    await enforceFullScreen();
    if (fullscreenLockoutOverlay) {
      fullscreenLockoutOverlay.style.display = 'none';
    }
    if (state.studentSessionId) {
      sendTelemetry('focus-regained', { source: 'fullscreen-restored' });
    }
  });
}

// Fullscreen Gate Modal Button Handler
if (enableFullscreenBtn) {
  enableFullscreenBtn.addEventListener('click', async () => {
    await enforceFullScreen();
    if (fullscreenGateModal) {
      fullscreenGateModal.style.display = 'none';
    }
    // Proceed to join
    executeJoinFlow();
  });
}

// Join Form Handler
const joinBtn = document.getElementById('joinBtn');
const joinError = document.getElementById('joinError');

joinBtn.addEventListener('click', async () => {
  // REQUIREMENT: KIOSK MUST NOT START THE EXAM IF SCREEN IS NOT FULLSCREEN!
  const isFs = await checkIsFullScreen();
  if (!isFs) {
    if (fullscreenGateModal) {
      fullscreenGateModal.style.display = 'flex';
    }
    return;
  }
  executeJoinFlow();
});

async function executeJoinFlow() {
  joinError.style.display = 'none';
  const customHost = document.getElementById('serverHostInput')?.value.trim().replace(/\/$/, '');
  if (customHost) {
    state.serverUrl = customHost;
    localStorage.setItem('tide_server_url', customHost);
  }
  state.accessCode = document.getElementById('accessCodeInput').value.trim().toUpperCase();
  state.studentName = document.getElementById('studentNameInput').value.trim();
  state.studentIdentifier = document.getElementById('studentIdInput').value.trim();

  if (!state.accessCode || !state.studentName || !state.studentIdentifier) {
    joinError.innerText = 'Please complete all required fields.';
    joinError.style.display = 'block';
    return;
  }

  joinBtn.disabled = true;
  joinBtn.innerText = 'Connecting...';

  try {
    const res = await fetch(`${state.serverUrl}/api/sessions/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        access_code: state.accessCode,
        student_name: state.studentName,
        student_identifier: state.studentIdentifier,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to join session');
    }

    const data = await res.json();
    state.studentSessionId = data.student_session_id;
    state.sessionId = data.session_id;

    // Update Header
    sessionBadge.innerText = `SESSION: ${state.accessCode}`;
    sessionBadge.style.background = '#0284c7';
    sessionBadge.style.color = '#e0f2fe';
    studentInfoBadge.innerText = `${state.studentName} (${state.studentIdentifier})`;
    studentInfoBadge.style.display = 'block';

    connectTelemetryWebSocket();
    checkExamState();
  } catch (err) {
    joinError.innerText = err.message;
    joinError.style.display = 'block';
  } finally {
    joinBtn.disabled = false;
    joinBtn.innerText = 'Enter Exam';
  }
}

// Check State and Start-Gate
async function checkExamState() {
  try {
    const res = await fetch(`${state.serverUrl}/api/exam/state/${state.studentSessionId}`);
    if (!res.ok) throw new Error('Failed to retrieve exam state');
    const examData = await res.json();

    if (examData.status === 'locked') {
      // Show Countdown Lock Screen
      switchView('countdown');
      document.getElementById('countdownStudentName').innerText = state.studentName;
      startCountdownTimer(examData.remaining_seconds);
    } else if (examData.status === 'submitted') {
      showSubmittedScreen();
    } else {
      // Exam is Active
      if (state.countdownInterval) clearInterval(state.countdownInterval);
      loadExamEnvironment(examData);
    }
  } catch (err) {
    console.error('State check error:', err);
  }
}

// Countdown Clock
function startCountdownTimer(remainingSeconds) {
  let seconds = remainingSeconds;
  const digitsEl = document.getElementById('countdownDigits');

  function updateDisplay() {
    const hrs = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const mins = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const secs = String(seconds % 60).padStart(2, '0');
    digitsEl.innerText = `${hrs}:${mins}:${secs}`;
  }

  updateDisplay();
  if (state.countdownInterval) clearInterval(state.countdownInterval);

  state.countdownInterval = setInterval(() => {
    seconds -= 1;
    if (seconds <= 0) {
      clearInterval(state.countdownInterval);
      digitsEl.innerText = '00:00:00';
      // Polling unlock
      checkExamState();
    } else {
      updateDisplay();
    }
  }, 1000);
}

// Load Active Exam Environment
function loadExamEnvironment(data) {
  switchView('exam');
  autosaveIndicator.style.display = 'flex';
  headerSubmitBtn.style.display = 'block';

  const assignment = data.assignment;
  document.getElementById('problemTitle').innerText = assignment.title;
  document.getElementById('problemStatement').innerText = assignment.problem_statement;

  // Render Visible Test Cases
  const container = document.getElementById('visibleTestCasesContainer');
  container.innerHTML = '';
  (assignment.visible_test_cases || []).forEach((tc, idx) => {
    const card = document.createElement('div');
    card.className = 'test-case-card';
    card.innerHTML = `
      <div style="font-weight: 600; font-size: 13px; margin-bottom: 6px; color: #60a5fa;">Test Case ${idx + 1}</div>
      <div class="tc-label">Input:</div>
      <div class="tc-value">${escapeHtml(tc.input || '')}</div>
      <div class="tc-label">Expected Output:</div>
      <div class="tc-value">${escapeHtml(tc.expected_output || '')}</div>
    `;
    container.appendChild(card);
  });

  // Editor setup
  const textarea = document.getElementById('codeEditorTextarea');
  textarea.value = data.saved_code || assignment.starter_code || '';
  if (data.saved_language) {
    document.getElementById('languageSelect').value = data.saved_language;
    state.currentLanguage = data.saved_language;
  }

  // Setup Autosave & Paste Listeners on Textarea
  textarea.addEventListener('input', triggerAutosave);
  textarea.addEventListener('paste', handleEditorPaste);
}

function escapeHtml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// REQUIREMENT: Paste from outside is flagged; internal copy-paste is ALLOWED!
function handleEditorPaste(e) {
  const clipboardData = e.clipboardData || window.clipboardData;
  if (!clipboardData) return;
  const pastedData = clipboardData.getData('text');
  if (!pastedData) return;

  const trimmed = pastedData.trim();

  // Check if content was copied from within the exam window
  if (internalClipboard.has(trimmed)) {
    console.log(`[Paste Allowed] Internal copy-paste from exam window (${pastedData.length} chars) - No flag generated.`);
    return; // Allowed without penalty!
  }

  // If not copied internally, it came from an external window/source -> FLAG IT!
  const pasteLength = pastedData.length;
  console.log(`[Paste Flagged] External paste detected: ${pasteLength} characters`);
  sendTelemetry('paste', {
    length: pasteLength,
    sample: pastedData.substring(0, 50),
    source: 'external-source',
  });
}

// Debounced Autosave (3 seconds)
function triggerAutosave() {
  autosaveText.innerText = 'Typing...';
  if (state.autosaveTimer) clearTimeout(state.autosaveTimer);

  state.autosaveTimer = setTimeout(async () => {
    const code = document.getElementById('codeEditorTextarea').value;
    const lang = document.getElementById('languageSelect').value;
    try {
      const res = await fetch(`${state.serverUrl}/api/exam/autosave`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_session_id: state.studentSessionId,
          code: code,
          language: lang,
        }),
      });
      if (res.ok) {
        const d = new Date();
        const timeStr = d.toTimeString().split(' ')[0];
        autosaveText.innerText = `Autosaved (${timeStr})`;
      }
    } catch (err) {
      autosaveText.innerText = 'Autosave failed (retrying)';
    }
  }, 3000);
}

// Run Visible Tests Button
const runTestsBtn = document.getElementById('runTestsBtn');
const consoleBody = document.getElementById('consoleBody');
const consoleTimeBadge = document.getElementById('consoleTimeBadge');

runTestsBtn.addEventListener('click', async () => {
  runTestsBtn.disabled = true;
  runTestsBtn.innerText = 'Running...';
  consoleBody.innerHTML = '<span style="color: #60a5fa;">Compiling and executing test cases...</span>';
  consoleTimeBadge.innerText = 'Executing';

  const code = document.getElementById('codeEditorTextarea').value;
  const lang = document.getElementById('languageSelect').value;

  try {
    const res = await fetch(`${state.serverUrl}/api/exam/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_session_id: state.studentSessionId,
        code: code,
        language: lang,
      }),
    });

    const data = await res.json();
    consoleTimeBadge.innerText = `${data.execution_time_ms.toFixed(1)} ms`;

    let html = '';
    if (data.results && data.results.length > 0) {
      data.results.forEach((r, idx) => {
        const statusBadge = r.passed
          ? '<span style="background: #047857; color: white; padding: 2px 6px; border-radius: 4px; font-weight: 700;">PASSED</span>'
          : '<span style="background: #b91c1c; color: white; padding: 2px 6px; border-radius: 4px; font-weight: 700;">FAILED</span>';

        html += `
          <div style="margin-bottom: 12px; padding: 8px; background: #111827; border-radius: 6px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
              <strong>Test Case ${idx + 1}</strong>
              ${statusBadge}
            </div>
            ${r.error ? `<div style="color: #ef4444; margin-top: 4px;">Error: ${escapeHtml(r.error)}</div>` : ''}
            <div style="color: #94a3b8; font-size: 12px; margin-top: 4px;">Output:</div>
            <pre style="background: #000; padding: 6px; border-radius: 4px; margin-top: 2px;">${escapeHtml(r.actual_output || '')}</pre>
          </div>
        `;
      });
    } else {
      html = '<span style="color: #10b981;">Execution completed with no visible tests.</span>';
    }

    consoleBody.innerHTML = html;
  } catch (err) {
    consoleBody.innerHTML = `<span style="color: #ef4444;">Run failed: ${escapeHtml(err.message)}</span>`;
  } finally {
    runTestsBtn.disabled = false;
    runTestsBtn.innerText = '▶ Run Tests';
  }
});

// Submit Exam Modal Flow
const submitModal = document.getElementById('submitModal');
const cancelSubmitBtn = document.getElementById('cancelSubmitBtn');
const confirmSubmitBtn = document.getElementById('confirmSubmitBtn');

headerSubmitBtn.addEventListener('click', () => {
  submitModal.style.display = 'flex';
});

cancelSubmitBtn.addEventListener('click', () => {
  submitModal.style.display = 'none';
});

confirmSubmitBtn.addEventListener('click', async () => {
  confirmSubmitBtn.disabled = true;
  confirmSubmitBtn.innerText = 'Submitting...';

  const code = document.getElementById('codeEditorTextarea').value;
  const lang = document.getElementById('languageSelect').value;

  try {
    const res = await fetch(`${state.serverUrl}/api/exam/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_session_id: state.studentSessionId,
        code: code,
        language: lang,
      }),
    });

    if (!res.ok) throw new Error('Submission failed');
    const result = await res.json();

    submitModal.style.display = 'none';
    showSubmittedScreen(result);
  } catch (err) {
    alert(`Submission error: ${err.message}`);
    confirmSubmitBtn.disabled = false;
    confirmSubmitBtn.innerText = 'Yes, Submit';
  }
});

function showSubmittedScreen(result) {
  state.isSubmitted = true;
  if (state.autosaveTimer) clearTimeout(state.autosaveTimer);
  if (state.countdownInterval) clearInterval(state.countdownInterval);

  if (state.ws) {
    try {
      state.ws.close(1000, 'Exam submitted');
    } catch (e) {}
    state.ws = null;
  }

  // Dismiss lockout overlay if active
  if (fullscreenLockoutOverlay) {
    fullscreenLockoutOverlay.style.display = 'none';
  }

  switchView('submitted');
  autosaveIndicator.style.display = 'none';
  headerSubmitBtn.style.display = 'none';

  if (result) {
    document.getElementById('finalScoreText').innerText = `${result.score_percentage}%`;
    document.getElementById('finalScoreDetails').innerText = `Passed ${result.passed_tests} of ${result.total_tests} total tests`;
  }
}

// Exit Kiosk Button
document.getElementById('exitKioskBtn').addEventListener('click', () => {
  if (window.electronAPI && window.electronAPI.exitApp) {
    window.electronAPI.exitApp();
  } else {
    window.close();
  }
});
