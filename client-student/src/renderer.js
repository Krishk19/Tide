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
  isFrozen: false,
  suppressInternetProbeUntil: 0,
  questions: [],
  activeQuestionId: null,
  codes: {},
};

// Auto-detect server URL from current location or localStorage
if (window.location.protocol.startsWith('http')) {
  state.serverUrl = window.location.origin;
} else if (localStorage.getItem('tide_server_url')) {
  state.serverUrl = localStorage.getItem('tide_server_url');
}

// Background UDP LAN Auto-Discovery if running in Electron
if (window.electronAPI && window.electronAPI.discoverServer) {
  window.electronAPI.discoverServer().then((res) => {
    if (res && res.server_url) {
      console.log('LAN Auto-Discovery found server:', res);
      state.serverUrl = res.server_url;
      try { localStorage.setItem('tide_server_url', res.server_url); } catch (e) {}
      const hostInput = document.getElementById('serverHostInput');
      if (hostInput) hostInput.value = res.server_url;
      const pinStatusHint = document.getElementById('pinStatusHint');
      if (pinStatusHint) {
        pinStatusHint.innerHTML = `<span style="color: var(--status-emerald); font-weight: 600;">✓ Connected to Lab Server (${res.server_ip})</span>`;
      }
    }
  }).catch(() => {});
}

// Initialize theme immediately on script evaluation
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  if (document.body) {
    document.body.className = 'theme-' + theme;
  }
  try {
    localStorage.setItem('tide_theme', theme);
  } catch (e) {}

  const themeLightBtn = document.getElementById('themeLightBtn');
  const themeDarkBtn = document.getElementById('themeDarkBtn');
  if (themeLightBtn && themeDarkBtn) {
    if (theme === 'light') {
      themeLightBtn.classList.add('active');
      themeDarkBtn.classList.remove('active');
    } else {
      themeDarkBtn.classList.add('active');
      themeLightBtn.classList.remove('active');
    }
  }
}

function initUIControls() {
  const serverHostInput = document.getElementById('serverHostInput');
  if (serverHostInput) {
    serverHostInput.value = state.serverUrl;
  }

  const toggleSettingsBtn = document.getElementById('toggleServerSettingsBtn');
  const settingsContainer = document.getElementById('serverSettingsContainer');
  if (toggleSettingsBtn && settingsContainer) {
    toggleSettingsBtn.onclick = () => {
      const isHidden = settingsContainer.style.display === 'none';
      settingsContainer.style.display = isHidden ? 'block' : 'none';
    };
  }

  // Segmented Theme Toggle (Light / Dark mode)
  const themeLightBtn = document.getElementById('themeLightBtn');
  const themeDarkBtn = document.getElementById('themeDarkBtn');
  const legacyToggleBtn = document.getElementById('themeToggleBtn');
  const savedTheme = localStorage.getItem('tide_theme') || 'dark';
  applyTheme(savedTheme);

  if (themeLightBtn) {
    themeLightBtn.onclick = () => applyTheme('light');
  }
  if (themeDarkBtn) {
    themeDarkBtn.onclick = () => applyTheme('dark');
  }
  if (legacyToggleBtn) {
    legacyToggleBtn.onclick = () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    };
  }

  // Robust Access Code Formatting & Status Hint
  const accessCodeInput = document.getElementById('accessCodeInput');
  const pinStatusHint = document.getElementById('pinStatusHint');

  if (accessCodeInput) {
    accessCodeInput.addEventListener('input', () => {
      const val = accessCodeInput.value.toUpperCase().replace(/[^A-Z0-9-]/g, '');
      accessCodeInput.value = val;

      if (pinStatusHint) {
        if (val.length >= 6) {
          pinStatusHint.innerHTML = '<span style="color: var(--status-emerald); font-weight: 600;">✓ Access Key Ready</span>';
        } else {
          pinStatusHint.innerText = 'Enter the code displayed on the lab projector';
        }
      }
    });
  }
}

// Run UI initialization immediately or on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initUIControls);
} else {
  initUIControls();
}


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
    state.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === 'broadcast_announcement') {
          showBroadcastBanner(data);
        } else if (data.event === 'extend_time') {
          handleExtendTime(data);
        } else if (data.event === 'direct_warning') {
          showDirectWarning(data);
        } else if (data.event === 'force_submit') {
          showSubmittedScreen(data.result);
        } else if (data.event === 'freeze_exam') {
          handleExamFrozen(data.reason);
        } else if (data.event === 'unfreeze_exam') {
          handleExamUnfrozen(data.reason);
        }
      } catch (e) {
        console.error('Failed to parse incoming WebSocket message', e);
      }
    };
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

// Focus event debouncing state to prevent duplicate Alt-Tab signals
let lastFocusEventType = null;
let lastFocusEventTime = 0;

function handleFocusChange(type, source) {
  const now = Date.now();
  if (type === lastFocusEventType && (now - lastFocusEventTime) < 2500) {
    return; // Suppress duplicate focus transition within 2.5 seconds
  }
  lastFocusEventType = type;
  lastFocusEventTime = now;
  console.log(`[Focus Telemetry] ${type} from ${source}`);
  if (state.studentSessionId) {
    sendTelemetry(type, { source: source });
  }
}

// Electron Main Process IPC Telemetry Hook
if (window.electronAPI && window.electronAPI.onKioskEvent) {
  window.electronAPI.onKioskEvent((event) => {
    if (state.isSubmitted) return;
    console.log('Kiosk Security Event:', event);
    if (event.type === 'fullscreen-exit') {
      handleFullscreenExit();
    } else if (event.type === 'focus-lost' || event.type === 'focus-regained') {
      handleFocusChange(event.type, 'electron-main');
    } else if (event.type === 'internet-detected') {
      triggerInternetDetected('electron-main');
    } else if (state.studentSessionId) {
      sendTelemetry(event.type, { source: 'electron-main' });
    }
  });
} else {
  // Web Browser / Kiosk Fallback listeners (works in Chrome, Edge, Firefox)
  window.addEventListener('blur', () => {
    if (state.isSubmitted) return;
    handleFocusChange('focus-lost', 'browser-blur');
  });

  window.addEventListener('focus', () => {
    if (state.isSubmitted) return;
    handleFocusChange('focus-regained', 'browser-focus');
  });

  document.addEventListener('visibilitychange', () => {
    if (state.isSubmitted) return;
    if (document.hidden) {
      handleFocusChange('focus-lost', 'tab-hidden');
    } else {
      handleFocusChange('focus-regained', 'tab-visible');
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

// Exam Freeze & Lockout Lifecycle
function handleExamFrozen(reason) {
  if (state.isSubmitted) return;
  state.isFrozen = true;
  const overlay = document.getElementById('internetLockoutOverlay');
  if (overlay) {
    overlay.style.display = 'flex';
  }
  const textarea = document.getElementById('codeEditorTextarea');
  if (textarea) {
    textarea.readOnly = true;
  }
  if (window.editorInstance) {
    window.editorInstance.updateOptions({ readOnly: true });
  }
  const runBtn = document.getElementById('runTestsBtn');
  const subBtn = document.getElementById('headerSubmitBtn');
  if (runBtn) runBtn.disabled = true;
  if (subBtn) subBtn.disabled = true;
  console.warn('[EXAM FROZEN]', reason);
}

function handleExamUnfrozen(reason) {
  state.isFrozen = false;
  // Grace period so developer or local tests don't immediately re-freeze
  state.suppressInternetProbeUntil = Date.now() + 25000;
  const overlay = document.getElementById('internetLockoutOverlay');
  if (overlay) {
    overlay.style.display = 'none';
  }
  const textarea = document.getElementById('codeEditorTextarea');
  if (textarea) {
    textarea.readOnly = false;
  }
  if (window.editorInstance) {
    window.editorInstance.updateOptions({ readOnly: false });
  }
  const runBtn = document.getElementById('runTestsBtn');
  const subBtn = document.getElementById('headerSubmitBtn');
  if (runBtn) runBtn.disabled = false;
  if (subBtn) subBtn.disabled = false;
  showFloatingNotification('Exam Unlocked', 'Evaluator has restored your examination session.', '🔓');
  console.log('[EXAM UNFROZEN]', reason);
}

function triggerInternetDetected(source = 'canary-probe') {
  if (state.isSubmitted || state.isFrozen) return;
  if (state.suppressInternetProbeUntil && Date.now() < state.suppressInternetProbeUntil) return;

  console.warn(`[SECURITY CRITICAL] External internet detected via ${source}! Freezing exam.`);
  handleExamFrozen('Unauthorized external internet detected');
  if (state.studentSessionId) {
    sendTelemetry('internet-detected', {
      source: source,
      reason: 'Active WAN / external internet gateway detected on terminal.'
    });
  }
}

// Active Canary Probe for External Internet Connectivity
// NOTE: Disabled by default for local dev/testing so home/office Wi-Fi doesn't freeze the exam.
// Can be toggled on via window.enableInternetDetection(true) or manually triggered via Ctrl+Alt+Shift+I.
let enableAutoInternetDetection = false;

window.enableInternetDetection = function(enabled = true) {
  enableAutoInternetDetection = enabled;
  console.log(`[Tide Security] Automatic internet detection is now: ${enabled ? 'ENABLED' : 'DISABLED'}`);
  if (enabled) {
    checkInternetConnection();
  }
};

async function checkInternetConnection() {
  if (!enableAutoInternetDetection) return false;
  if (!state.studentSessionId || state.isSubmitted || state.isFrozen) return false;
  if (state.suppressInternetProbeUntil && Date.now() < state.suppressInternetProbeUntil) return false;

  const isExamActive = views.exam.classList.contains('active') || views.countdown.classList.contains('active');
  if (!isExamActive) return false;

  try {
    if (window.electronAPI && window.electronAPI.checkInternet) {
      const isOnline = await window.electronAPI.checkInternet();
      if (isOnline) {
        triggerInternetDetected('electron-net-socket');
        return true;
      }
    } else {
      // Browser canary fetch probe
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1200);
      try {
        await fetch('https://connectivitycheck.gstatic.com/generate_204', {
          mode: 'no-cors',
          cache: 'no-store',
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        triggerInternetDetected('browser-http-canary');
        return true;
      } catch (err) {
        clearTimeout(timeoutId);
      }
    }
  } catch (err) {
    // Offline (expected state in secure exam lab)
  }
  return false;
}

// Periodic Canary Probe Interval (only runs if enableAutoInternetDetection is turned on)
setInterval(() => {
  if (enableAutoInternetDetection) {
    checkInternetConnection();
  }
}, 4000);

// Network online event listener (only triggers if enableAutoInternetDetection is turned on)
window.addEventListener('online', () => {
  if (enableAutoInternetDetection && state.studentSessionId && !state.isSubmitted && !state.isFrozen) {
    triggerInternetDetected('browser-online-event');
  }
});

// Proctor / Evaluator demo test trigger (available anytime for manual testing)
window.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.altKey && e.shiftKey && (e.key === 'I' || e.key === 'i')) {
    e.preventDefault();
    console.log('[PROCTOR SHORTCUT] Manual internet detection triggered for testing');
    triggerInternetDetected('proctor-manual-trigger');
  }
});
window.simulateInternetDetection = () => triggerInternetDetected('evaluator-demo-trigger');

// On-Desk Evaluator Unlock Handlers
const openUnlockBtn = document.getElementById('openEvaluatorUnlockBtn');
const unlockPanel = document.getElementById('evaluatorUnlockPanel');
const submitUnlockBtn = document.getElementById('submitEvaluatorUnlockBtn');
const unlockPasswordInput = document.getElementById('evaluatorPasswordInput');
const unlockError = document.getElementById('evaluatorUnlockError');

if (openUnlockBtn && unlockPanel) {
  openUnlockBtn.addEventListener('click', () => {
    const isHidden = unlockPanel.style.display === 'none';
    unlockPanel.style.display = isHidden ? 'block' : 'none';
    if (isHidden && unlockPasswordInput) {
      unlockPasswordInput.focus();
    }
  });
}

if (submitUnlockBtn && unlockPasswordInput) {
  async function performOnDeskUnlock() {
    const password = unlockPasswordInput.value.trim();
    if (!password) {
      if (unlockError) {
        unlockError.innerText = 'Please enter proctor password.';
        unlockError.style.display = 'block';
      }
      return;
    }
    if (!state.studentSessionId) return;

    submitUnlockBtn.disabled = true;
    submitUnlockBtn.innerText = 'Unlocking...';
    if (unlockError) unlockError.style.display = 'none';

    try {
      const res = await fetch(`${state.serverUrl}/api/sessions/on-desk-unfreeze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_session_id: state.studentSessionId,
          password: password,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        handleExamUnfrozen('On-desk evaluator authentication');
        unlockPasswordInput.value = '';
        if (unlockPanel) unlockPanel.style.display = 'none';
      } else {
        if (unlockError) {
          unlockError.innerText = data.detail || 'Invalid proctor password.';
          unlockError.style.display = 'block';
        }
      }
    } catch (err) {
      if (unlockError) {
        unlockError.innerText = 'Failed to connect to server.';
        unlockError.style.display = 'block';
      }
    } finally {
      submitUnlockBtn.disabled = false;
      submitUnlockBtn.innerText = 'Unlock';
    }
  }

  submitUnlockBtn.addEventListener('click', performOnDeskUnlock);
  unlockPasswordInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      performOnDeskUnlock();
    }
  });
}

function showFloatingNotification(title, desc, icon = 'ℹ️') {
  let toast = document.getElementById('reconnectToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'reconnectToast';
    toast.className = 'reconnect-toast';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `
    <div class="reconnect-toast-icon">${icon}</div>
    <div class="reconnect-toast-content">
      <div class="reconnect-toast-title">${title}</div>
      <div class="reconnect-toast-desc">${desc}</div>
    </div>
  `;
  toast.classList.add('visible');
  setTimeout(() => toast.classList.remove('visible'), 5000);
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

    if (data.is_reconnect) {
      showReconnectNotification(data.downtime_seconds);
    }
    if (data.is_frozen) {
      handleExamFrozen('Session is currently frozen by evaluator.');
    }

    // Update Header
    sessionBadge.innerText = `SESSION: ${state.accessCode}`;
    sessionBadge.style.background = 'var(--bg-subtle)';
    sessionBadge.style.color = 'var(--text-primary)';
    sessionBadge.style.borderColor = 'var(--border-subtle)';
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

// Reconnect Floating Toast Notification
function showReconnectNotification(downtimeSeconds) {
  let toast = document.getElementById('reconnectToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'reconnectToast';
    toast.className = 'reconnect-toast';
    document.body.appendChild(toast);
  }
  const formattedDowntime = downtimeSeconds ? `${downtimeSeconds}s` : 'brief';
  toast.innerHTML = `
    <div class="reconnect-toast-icon">✓</div>
    <div class="reconnect-toast-content">
      <div class="reconnect-toast-title">Session Resumed</div>
      <div class="reconnect-toast-desc">Restored code from autosave (${formattedDowntime} offline gap). Assessment active.</div>
    </div>
  `;
  toast.classList.add('visible');
  setTimeout(() => {
    toast.classList.remove('visible');
  }, 6000);
}

// Classroom Remote Broadcast Banner
function showBroadcastBanner(data) {
  const container = document.getElementById('broadcastBannerContainer');
  if (!container) return;

  const banner = document.createElement('div');
  const type = data.type || 'info';
  banner.className = `broadcast-banner ${type}`;

  const icon = type === 'urgent' ? '🚨' : type === 'warning' ? '⚠️' : '📢';
  const label = type === 'urgent' ? 'URGENT NOTICE' : type === 'warning' ? 'IMPORTANT' : 'ANNOUNCEMENT';

  banner.innerHTML = `
    <div class="broadcast-banner-left">
      <span class="broadcast-banner-badge">${icon} ${label}</span>
      <span class="broadcast-banner-text">${escapeHtml(data.message)}</span>
    </div>
    <button class="broadcast-banner-close" title="Dismiss">✕</button>
  `;

  const closeBtn = banner.querySelector('.broadcast-banner-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      banner.style.opacity = '0';
      banner.style.transform = 'translateY(-20px)';
      setTimeout(() => banner.remove(), 250);
    });
  }

  container.appendChild(banner);

  // Auto-dismiss after 15 seconds
  setTimeout(() => {
    if (banner.parentNode) {
      banner.style.opacity = '0';
      banner.style.transform = 'translateY(-20px)';
      setTimeout(() => banner.remove(), 250);
    }
  }, 15000);
}

// Classroom Remote Extra Time Handler
function handleExtendTime(data) {
  const timerBadge = document.getElementById('examTimerBadge');
  if (timerBadge) {
    timerBadge.classList.add('time-pulse');
    setTimeout(() => timerBadge.classList.remove('time-pulse'), 5000);
  }

  let toast = document.getElementById('reconnectToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'reconnectToast';
    toast.className = 'reconnect-toast';
    document.body.appendChild(toast);
  }
  toast.innerHTML = `
    <div class="reconnect-toast-icon">⏰</div>
    <div class="reconnect-toast-content">
      <div class="reconnect-toast-title">+${data.added_minutes} Minutes Added</div>
      <div class="reconnect-toast-desc">${escapeHtml(data.reason || 'Compensatory time granted by instructor.')}</div>
    </div>
  `;
  toast.classList.add('visible');
  setTimeout(() => toast.classList.remove('visible'), 7000);
}

// Classroom Direct Warning Modal
function showDirectWarning(data) {
  const modal = document.getElementById('directWarningModal');
  const msgEl = document.getElementById('directWarningMessageText');
  const ackBtn = document.getElementById('ackWarningBtn');
  if (!modal || !msgEl) return;

  msgEl.innerText = data.message || 'Please maintain exam integrity and stay focused on your terminal.';
  modal.style.display = 'flex';

  if (ackBtn) {
    ackBtn.onclick = () => {
      modal.style.display = 'none';
    };
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
  state.questions = assignment.questions && assignment.questions.length > 0 ? assignment.questions : [{
    id: 'q1',
    title: assignment.title,
    problem_statement: assignment.problem_statement,
    starter_code: assignment.starter_code || '',
    visible_test_cases: assignment.visible_test_cases || []
  }];

  state.codes = data.saved_codes || {};
  if (Object.keys(state.codes).length === 0) {
    state.questions.forEach((q, idx) => {
      state.codes[q.id] = idx === 0 ? (data.saved_code || q.starter_code || '') : (q.starter_code || '');
    });
  }

  // Setup question tabs
  renderQuestionTabs();

  if (data.saved_language) {
    document.getElementById('languageSelect').value = data.saved_language;
    state.currentLanguage = data.saved_language;
  }

  // Switch to first question
  switchQuestion(state.questions[0].id, false);

  // Setup Autosave, Tab key indentation, and Paste Listeners on Textarea
  const textarea = document.getElementById('codeEditorTextarea');
  if (!textarea._hasListeners) {
    textarea._hasListeners = true;
    textarea.addEventListener('input', triggerAutosave);
    textarea.addEventListener('paste', handleEditorPaste);
    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        textarea.value = textarea.value.substring(0, start) + '    ' + textarea.value.substring(end);
        textarea.selectionStart = textarea.selectionEnd = start + 4;
        triggerAutosave();
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        const runBtn = document.getElementById('runTestsBtn');
        if (runBtn && !runBtn.disabled) runBtn.click();
      }
    });
  }

  if (state.isFrozen) {
    handleExamFrozen('Session is currently frozen by evaluator.');
  }
}

function renderQuestionTabs() {
  const tabsBar = document.getElementById('questionTabsBar');
  if (!tabsBar) return;
  tabsBar.innerHTML = '';

  state.questions.forEach((q, idx) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `panel-tab question-tab-btn ${q.id === state.activeQuestionId ? 'active' : ''}`;
    btn.dataset.qid = q.id;
    btn.style.cursor = 'pointer';
    btn.style.background = 'transparent';
    btn.style.border = 'none';
    btn.innerText = `Q${idx + 1}: ${q.title || `Problem ${idx + 1}`}`;
    btn.addEventListener('click', () => switchQuestion(q.id, true));
    tabsBar.appendChild(btn);
  });
}

function switchQuestion(qid, saveCurrent = true) {
  const textarea = document.getElementById('codeEditorTextarea');
  if (saveCurrent && state.activeQuestionId && textarea) {
    state.codes[state.activeQuestionId] = textarea.value;
    triggerAutosave();
  }

  state.activeQuestionId = qid;
  const q = state.questions.find(x => x.id === qid) || state.questions[0];

  // Update tabs active state
  document.querySelectorAll('.question-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.qid === qid);
  });

  document.getElementById('problemTitle').innerText = q.title;
  document.getElementById('problemStatement').innerText = q.problem_statement;

  // Render Visible Test Cases
  const container = document.getElementById('visibleTestCasesContainer');
  container.innerHTML = '';
  (q.visible_test_cases || []).forEach((tc, idx) => {
    const card = document.createElement('div');
    card.className = 'test-case-card';
    card.innerHTML = `
      <div style="font-weight: 600; font-size: 11px; margin-bottom: 8px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em;">Test Case ${idx + 1}</div>
      <div class="tc-label">Input</div>
      <div class="tc-value">${escapeHtml(tc.input || '')}</div>
      <div class="tc-label">Expected Output</div>
      <div class="tc-value">${escapeHtml(tc.expected_output || '')}</div>
    `;
    container.appendChild(card);
  });

  if (textarea) {
    textarea.value = state.codes[qid] !== undefined ? state.codes[qid] : (q.starter_code || '');
  }

  if (consoleBody) {
    consoleTimeBadge.innerText = 'Ready';
    consoleBody.innerHTML = `<span style="color: var(--text-secondary);">Switched to <strong>${escapeHtml(q.title)}</strong>. Press "Run Tests" to execute against visible test cases.</span>`;
  }
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

// Debounced Autosave (2 seconds)
function triggerAutosave() {
  autosaveText.innerText = 'Typing...';
  if (state.autosaveTimer) clearTimeout(state.autosaveTimer);

  state.autosaveTimer = setTimeout(async () => {
    const textarea = document.getElementById('codeEditorTextarea');
    const code = textarea ? textarea.value : '';
    const lang = document.getElementById('languageSelect').value;
    if (state.activeQuestionId) {
      state.codes[state.activeQuestionId] = code;
    }
    try {
      const res = await fetch(`${state.serverUrl}/api/exam/autosave`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_session_id: state.studentSessionId,
          code: code,
          question_id: state.activeQuestionId,
          codes: state.codes,
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
  }, 2000);
}

// Run Visible Tests Button
const runTestsBtn = document.getElementById('runTestsBtn');
const consoleBody = document.getElementById('consoleBody');
const consoleTimeBadge = document.getElementById('consoleTimeBadge');

runTestsBtn.addEventListener('click', async () => {
  runTestsBtn.disabled = true;
  runTestsBtn.innerText = 'Running...';
  consoleBody.innerHTML = '<span style="color: var(--text-secondary);">Executing test suites against sandbox...</span>';
  consoleTimeBadge.innerText = 'Executing';

  const code = document.getElementById('codeEditorTextarea').value;
  const lang = document.getElementById('languageSelect').value;
  if (state.activeQuestionId) {
    state.codes[state.activeQuestionId] = code;
  }

  try {
    const res = await fetch(`${state.serverUrl}/api/exam/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_session_id: state.studentSessionId,
        code: code,
        language: lang,
        question_id: state.activeQuestionId,
      }),
    });

    const data = await res.json();
    consoleTimeBadge.innerText = `${data.execution_time_ms.toFixed(1)} ms`;

    let html = '';
    if (data.results && data.results.length > 0) {
      data.results.forEach((r, idx) => {
        const statusBadge = r.passed
          ? '<span style="background: rgba(16, 185, 129, 0.12); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.25); padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 10px; font-family: var(--font-mono);">PASSED</span>'
          : '<span style="background: rgba(244, 63, 94, 0.12); color: #fda4af; border: 1px solid rgba(244, 63, 94, 0.25); padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 10px; font-family: var(--font-mono);">FAILED</span>';

        html += `
          <div style="margin-bottom: 10px; padding: 10px 12px; background: var(--bg-well); border: 1px solid var(--border-hairline); border-radius: 6px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <strong style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-primary);">Test Case ${idx + 1}</strong>
              ${statusBadge}
            </div>
            ${r.error ? `<div style="color: var(--status-rose); font-size: 11px; margin-top: 4px;">Error: ${escapeHtml(r.error)}</div>` : ''}
            <div style="color: var(--text-tertiary); font-size: 11px; margin-top: 4px;">Output:</div>
            <pre style="background: rgba(0,0,0,0.4); border: 1px solid var(--border-hairline); padding: 6px 8px; border-radius: 4px; margin-top: 4px; font-family: var(--font-mono); font-size: 11px; color: var(--text-primary);">${escapeHtml(r.actual_output || '')}</pre>
          </div>
        `;
      });
    } else {
      html = '<span style="color: var(--status-emerald);">Execution completed with no visible tests.</span>';
    }

    consoleBody.innerHTML = html;
  } catch (err) {
    consoleBody.innerHTML = `<span style="color: var(--status-rose);">Run failed: ${escapeHtml(err.message)}</span>`;
  } finally {
    runTestsBtn.disabled = false;
    runTestsBtn.innerText = 'Run Tests';
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
  if (state.activeQuestionId) {
    state.codes[state.activeQuestionId] = code;
  }

  try {
    const res = await fetch(`${state.serverUrl}/api/exam/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_session_id: state.studentSessionId,
        code: code,
        language: lang,
        codes: state.codes,
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
    // In browser: attempt close, or cleanly reset session and redirect to terminal join
    try {
      window.close();
    } catch (e) {}
    sessionStorage.clear();
    localStorage.removeItem('tide_student_session');
    setTimeout(() => {
      window.location.href = '/student';
    }, 200);
  }
});
