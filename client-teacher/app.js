// Tide Teacher Command Center Dashboard
const state = {
  token: localStorage.getItem('tide_token') || null,
  teacher: null,
  assignments: [],
  sessions: [],
  selectedSessionId: null,
  ws: null,
  activeFlags: [],
  audioAlertEnabled: true,
};

// Audio Alert Toggle
const audioToggleBtn = document.getElementById('audioAlertToggleBtn');
if (audioToggleBtn) {
  audioToggleBtn.addEventListener('click', () => {
    state.audioAlertEnabled = !state.audioAlertEnabled;
    audioToggleBtn.innerText = state.audioAlertEnabled ? '🔔 Audio Alert: ON' : '🔕 Audio Alert: OFF';
    audioToggleBtn.style.color = state.audioAlertEnabled ? '#10b981' : '#94a3b8';
  });
}

// Theme Toggle (Light / Dark mode)
const themeToggleBtn = document.getElementById('themeToggleBtn');
const themeToggleText = document.getElementById('themeToggleText');
const savedTheme = localStorage.getItem('tide_theme') || 'dark';
applyTheme(savedTheme);

if (themeToggleBtn) {
  themeToggleBtn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('tide_theme', theme);
  if (themeToggleText) {
    themeToggleText.innerText = theme === 'dark' ? '☀ Light' : '☾ Dark';
  }
}

// DOM Elements
const authSection = document.getElementById('authSection');
const liveMonitorSection = document.getElementById('liveMonitorSection');
const sessionsSection = document.getElementById('sessionsSection');
const assignmentsSection = document.getElementById('assignmentsSection');

const mainNav = document.getElementById('mainNav');
const teacherProfile = document.getElementById('teacherProfile');
const teacherNameDisplay = document.getElementById('teacherNameDisplay');
const logoutBtn = document.getElementById('logoutBtn');
const authError = document.getElementById('authError');

// Navigation
document.querySelectorAll('.nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const targetId = btn.dataset.view;

    [liveMonitorSection, sessionsSection, assignmentsSection].forEach((sec) =>
      sec.classList.remove('active')
    );
    const targetSec = document.getElementById(targetId);
    if (targetSec) targetSec.classList.add('active');

    if (targetId === 'sessionsSection') loadSessions();
    if (targetId === 'assignmentsSection') loadAssignments();
    if (targetId === 'liveMonitorSection') refreshMonitorView();
  });
});

// App Initialization
async function initApp() {
  if (state.token) {
    try {
      const res = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${state.token}` },
      });
      if (res.ok) {
        state.teacher = await res.json();
        showAuthenticatedUI();
        return;
      }
    } catch (e) {
      console.error('Session verify failed:', e);
    }
  }
  showUnauthenticatedUI();
}

function showAuthenticatedUI() {
  authSection.classList.remove('active');
  mainNav.style.display = 'flex';
  teacherProfile.style.display = 'block';
  logoutBtn.style.display = 'block';
  teacherNameDisplay.innerText = state.teacher.name || state.teacher.username;

  liveMonitorSection.classList.add('active');
  connectTeacherWebSocket();
  loadAssignments();
  loadSessions();
  refreshMonitorView();
}

function showUnauthenticatedUI() {
  authSection.classList.add('active');
  mainNav.style.display = 'none';
  teacherProfile.style.display = 'none';
  logoutBtn.style.display = 'none';
  if (state.ws) state.ws.close();
}

// Authentication Handlers
document.getElementById('loginBtn').addEventListener('click', async () => {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value.trim();
  authError.style.display = 'none';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error('Invalid credentials');
    const data = await res.json();
    state.token = data.access_token;
    state.teacher = data.teacher;
    localStorage.setItem('tide_token', state.token);
    showAuthenticatedUI();
  } catch (err) {
    authError.innerText = err.message;
    authError.style.display = 'block';
  }
});

// Quick Register Demo Button
document.getElementById('demoRegisterBtn').addEventListener('click', async () => {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value.trim();
  authError.style.display = 'none';

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username,
        password: password,
        name: 'Prof. R. K. Sharma',
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Registration failed');
    }
    // Auto-login
    document.getElementById('loginBtn').click();
  } catch (err) {
    authError.innerText = err.message;
    authError.style.display = 'block';
  }
});

logoutBtn.addEventListener('click', () => {
  localStorage.removeItem('tide_token');
  state.token = null;
  state.teacher = null;
  showUnauthenticatedUI();
});

// Web Audio API Chime for Critical Alerts
function playAlertChime() {
  if (!state.audioAlertEnabled) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.1);
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.35);
  } catch (e) {}
}

// WebSocket Live Telemetry Feed
function connectTeacherWebSocket() {
  if (!state.token) return;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/teacher?token=${state.token}`;

  try {
    state.ws = new WebSocket(wsUrl);
    state.ws.onopen = () => {
      document.getElementById('feedStatusText').innerText = 'Connected (Live Stream)';
      document.getElementById('feedStatusText').style.color = '#10b981';
    };
    state.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.event === 'new_flag') {
        prependFlagCard(data.flag);
        // Refresh active student roster if needed
        if (state.selectedSessionId) loadActiveSessionRoster(state.selectedSessionId);
      } else if (data.event === 'student_submitted' || data.event === 'risk_score_update') {
        // Refresh active student roster immediately to show SUBMITTED badge or new Risk Score
        if (state.selectedSessionId) loadActiveSessionRoster(state.selectedSessionId);
      }
    };
    state.ws.onclose = () => {
      document.getElementById('feedStatusText').innerText = 'Reconnecting...';
      document.getElementById('feedStatusText').style.color = '#f59e0b';
      setTimeout(connectTeacherWebSocket, 3000);
    };
  } catch (err) {
    console.error('WebSocket error:', err);
  }
}

// Assignments
async function loadAssignments() {
  if (!state.token) return;
  try {
    const res = await fetch('/api/assignments', {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    state.assignments = await res.json();

    // Render Grid
    const grid = document.getElementById('assignmentsGrid');
    grid.innerHTML = '';
    state.assignments.forEach((a) => {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <div style="font-weight: 600; font-size: 15px; margin-bottom: 8px; color: var(--text);">${escapeHtml(a.title)}</div>
        <p style="font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 14px;">${escapeHtml(a.problem_statement.substring(0, 110))}...</p>
        <div style="display: flex; gap: 6px; font-size: 11px; margin-bottom: 6px;">
          <span class="badge">${a.language_set}</span>
          <span class="badge">${(a.visible_test_cases || []).length} Visible</span>
          <span class="badge">${(a.hidden_test_cases || []).length} Hidden</span>
        </div>
      `;
      grid.appendChild(card);
    });

    // Populate Modal Dropdown
    const select = document.getElementById('modalSessionAssignmentSelect');
    select.innerHTML = '<option value="">Select an Assignment</option>';
    state.assignments.forEach((a) => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.innerText = a.title;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Failed to load assignments:', err);
  }
}

// Sessions
async function loadSessions() {
  if (!state.token) return;
  try {
    const res = await fetch('/api/sessions', {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    state.sessions = await res.json();

    const tbody = document.getElementById('sessionsTableBody');
    tbody.innerHTML = '';
    const activeSelect = document.getElementById('activeSessionSelect');
    activeSelect.innerHTML = '<option value="">Select a Session to Monitor</option>';

    state.sessions.forEach((s) => {
      const tr = document.createElement('tr');
      const startD = new Date(s.start_time);
      tr.innerHTML = `
        <td><strong style="color: #60a5fa; letter-spacing: 2px;">${s.access_code}</strong></td>
        <td>${escapeHtml(s.assignment_title || 'Untitled')}</td>
        <td>${startD.toLocaleTimeString()}</td>
        <td><span class="badge badge-${s.status}">${s.status}</span></td>
        <td>${s.student_count}</td>
        <td>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 12px;" onclick="openProjector('${s.access_code}', '${escapeHtml(s.assignment_title)}')">📽️ Project</button>
          <button class="btn btn-primary" style="padding: 4px 8px; font-size: 12px;" onclick="selectSessionForMonitor(${s.id})">👁️ Monitor</button>
        </td>
      `;
      tbody.appendChild(tr);

      const opt = document.createElement('option');
      opt.value = s.id;
      opt.innerText = `${s.access_code} — ${s.assignment_title || 'Session'}`;
      if (s.id === state.selectedSessionId) opt.selected = true;
      activeSelect.appendChild(opt);
    });

    // Default select first session if none selected
    if (!state.selectedSessionId && state.sessions.length > 0) {
      selectSessionForMonitor(state.sessions[0].id);
    }
  } catch (err) {
    console.error('Failed to load sessions:', err);
  }
}

// Monitor Session Switch
document.getElementById('activeSessionSelect').addEventListener('change', (e) => {
  const sessId = parseInt(e.target.value);
  if (sessId) selectSessionForMonitor(sessId);
});

function selectSessionForMonitor(sessionId) {
  state.selectedSessionId = sessionId;
  document.getElementById('activeSessionSelect').value = sessionId;
  refreshMonitorView();
}

async function refreshMonitorView() {
  if (!state.selectedSessionId) return;
  loadActiveSessionRoster(state.selectedSessionId);
  loadRecentFlags();
}

async function loadActiveSessionRoster(sessionId) {
  if (!state.token) return;
  try {
    const res = await fetch(`/api/sessions/${sessionId}`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!res.ok) return;
    const session = await res.json();

    document.getElementById('studentCountBadge').innerText = `${session.student_count} CONNECTED`;

    // Update Executive Metrics Bar
    const metricTotal = document.getElementById('metricTotalStudents');
    const metricSubmitted = document.getElementById('metricSubmittedCount');
    const metricActive = document.getElementById('metricActiveStreams');
    const metricFlags = document.getElementById('metricSecurityFlags');
    if (metricTotal) metricTotal.innerText = session.students?.length || 0;
    if (metricSubmitted) metricSubmitted.innerText = session.students?.filter(s => s.submitted_at).length || 0;
    if (metricActive) metricActive.innerText = session.student_count || 0;
    if (metricFlags) metricFlags.innerText = session.students?.reduce((acc, s) => acc + (s.flag_count || 0), 0) || 0;

    const tbody = document.getElementById('studentRosterTbody');
    tbody.innerHTML = '';

    if (!session.students || session.students.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 24px;">No students have joined this session yet. Project code on board!</td></tr>';
      return;
    }

    session.students.forEach((st) => {
      const tr = document.createElement('tr');
      const autosaveTime = st.last_autosaved_at ? new Date(st.last_autosaved_at).toLocaleTimeString() : 'Never';
      const statusBadge = st.submitted_at
        ? '<span class="badge" style="background: rgba(16, 185, 129, 0.1); color: #34d399; border-color: rgba(16, 185, 129, 0.25);">SUBMITTED</span>'
        : '<span class="badge" style="background: rgba(255, 255, 255, 0.08); color: var(--text);">TAKING EXAM</span>';

      const flagBadge = st.flag_count > 0
        ? `<span class="badge" style="background: rgba(244, 63, 94, 0.12); color: #fda4af; border-color: rgba(244, 63, 94, 0.25);">${st.flag_count} Flags</span>`
        : '<span class="badge" style="background: rgba(16, 185, 129, 0.08); color: #34d399; border-color: rgba(16, 185, 129, 0.2);">Clean</span>';

      const risk = st.risk_score || 0;
      let riskClass = 'risk-clean';
      let riskLabel = '0 Clean';
      if (risk >= 75) {
        riskClass = 'risk-high';
        riskLabel = `⚠️ ${risk} High Risk`;
      } else if (risk >= 50) {
        riskClass = 'risk-suspicious';
        riskLabel = `⚡ ${risk} Suspicious`;
      } else if (risk >= 20) {
        riskClass = 'risk-low';
        riskLabel = `${risk} Low Risk`;
      }
      const riskBadge = `<span class="risk-badge ${riskClass}">${riskLabel}</span>`;

      tr.innerHTML = `
        <td><strong>${escapeHtml(st.student_name)}</strong></td>
        <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">${escapeHtml(st.student_identifier)}</td>
        <td>${riskBadge}</td>
        <td style="font-size: 12px; font-family: var(--font-mono); color: var(--text-muted);">${autosaveTime}</td>
        <td>${statusBadge}</td>
        <td>${flagBadge}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Failed to load roster:', err);
  }
}

// Flags Management
async function loadRecentFlags() {
  if (!state.token) return;
  try {
    const url = state.selectedSessionId
      ? `/api/dashboard/flags?session_id=${state.selectedSessionId}`
      : '/api/dashboard/flags';
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    const flags = await res.json();

    const feed = document.getElementById('liveFlagFeed');
    feed.innerHTML = '';
    if (flags.length === 0) {
      feed.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; text-align: center; padding: 30px;">Awaiting telemetry signals from student kiosk sessions...</div>';
      return;
    }
    flags.forEach((f) => prependFlagCard(f, false));
  } catch (err) {
    console.error('Failed to load flags:', err);
  }
}

function prependFlagCard(flag, isNew = true) {
  const feed = document.getElementById('liveFlagFeed');
  // Remove placeholder if present
  if (feed.innerText.includes('Awaiting telemetry')) feed.innerHTML = '';

  const card = document.createElement('div');
  const isCritical = flag.type === 'correlated-cheat-attempt' || flag.severity === 'critical';
  const isDanger = ['fullscreen-exit', 'connection-lost', 'paste'].includes(flag.type) || isCritical;
  card.className = `flag-card ${isCritical ? 'critical' : isDanger ? 'danger' : 'info'}`;
  card.id = `flag-card-${flag.id}`;

  const timeStr = new Date(flag.ts).toLocaleTimeString();
  let descText = `Event type: ${flag.type}`;
  if (flag.type === 'focus-lost') descText = 'Window lost focus (Alt-Tab or window switch)';
  if (flag.type === 'focus-regained') descText = 'Window regained focus';
  if (flag.type === 'fullscreen-exit') descText = 'Attempted to exit fullscreen kiosk';
  if (flag.type === 'paste') {
    descText = `Pasted ${flag.metadata?.length || 0} characters into code editor`;
    if (flag.metadata?.sample) {
      descText += `<div style="font-family: var(--font-mono); font-size: 11px; background: rgba(0,0,0,0.4); border: 1px solid var(--border); padding: 4px 8px; border-radius: 4px; margin-top: 5px; color: var(--text-muted);">Sample: "${escapeHtml(flag.metadata.sample)}"</div>`;
    }
  }
  if (flag.type === 'connection-lost') descText = 'Abrupt WebSocket disconnect detected';
  if (flag.type === 'reconnected') {
    const downtime = flag.metadata?.downtime_seconds != null ? `${flag.metadata.downtime_seconds}s` : null;
    const lines = flag.metadata?.restored_line_count != null ? `${flag.metadata.restored_line_count} lines` : null;
    if (downtime && lines) {
      descText = `Student reconnected after ${downtime} offline gap. Restored ${lines} of code from autosave.`;
    } else if (flag.metadata?.reason) {
      descText = escapeHtml(flag.metadata.reason);
    } else {
      descText = 'Student reconnected to exam session';
    }
  }
  if (flag.type === 'correlated-cheat-attempt') {
    descText = `⚠️ <strong>HIGH-CONFIDENCE CORRELATION ALERT:</strong> ${escapeHtml(flag.metadata?.reason || 'Window lost focus followed immediately by external paste.')}`;
    if (flag.metadata?.paste_sample) {
      descText += `<div style="font-family: var(--font-mono); font-size: 11px; background: rgba(244, 63, 94, 0.08); border: 1px solid rgba(244, 63, 94, 0.2); padding: 4px 8px; border-radius: 4px; margin-top: 5px; color: #fda4af;">Sample: "${escapeHtml(flag.metadata.paste_sample)}"</div>`;
    }
    if (isNew) playAlertChime();
  }

  const isReviewed = flag.status !== 'open';
  const notesText = flag.notes ? `<div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;"><em>Note: ${escapeHtml(flag.notes)}</em></div>` : '';

  card.innerHTML = `
    <div class="flag-header">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span class="badge badge-${flag.type}">${flag.type}</span>
        <strong style="font-size: 13px;">${escapeHtml(flag.student_name || 'Student')}</strong>
        <span style="font-size: 11px; font-family: var(--font-mono); color: var(--text-tertiary);">(${escapeHtml(flag.student_identifier || '')})</span>
      </div>
      <span style="font-size: 11px; font-family: var(--font-mono); color: var(--text-tertiary);">${timeStr}</span>
    </div>
    <div class="flag-desc">${descText}${notesText}</div>
    <div style="display: flex; justify-content: flex-end; gap: 6px;">
      ${
        isReviewed
          ? `<span style="font-size: 11px; color: ${flag.status === 'escalated' ? 'var(--danger)' : 'var(--success)'}; font-weight: 600;">✓ Reviewed (${flag.status})</span>`
          : `
            <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px;" onclick="dismissFlag(${flag.id})">Dismiss</button>
            <button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px; background: rgba(244, 63, 94, 0.12); color: #fda4af; border-color: rgba(244, 63, 94, 0.25);" onclick="escalateFlag(${flag.id})">Escalate</button>
          `
      }
    </div>
  `;

  if (isNew) {
    feed.insertBefore(card, feed.firstChild);
  } else {
    feed.appendChild(card);
  }
}

// Non-Destructive Flag Dismiss
window.dismissFlag = async function (flagId) {
  const notes = prompt('Optional dismissal note (or press OK):', 'False alarm / verified');
  if (notes === null) return;
  try {
    const res = await fetch(`/api/dashboard/flags/${flagId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ status: 'dismissed', notes: notes }),
    });
    if (res.ok) {
      const card = document.getElementById(`flag-card-${flagId}`);
      if (card) {
        card.querySelector('div:last-child').innerHTML =
          '<span style="font-size: 11px; color: #10b981; font-weight: 600;">✓ Dismissed by Instructor</span>';
      }
      if (state.selectedSessionId) loadActiveSessionRoster(state.selectedSessionId);
    }
  } catch (err) {
    console.error('Dismiss flag error:', err);
  }
};

// Disciplinary Flag Escalate
window.escalateFlag = async function (flagId) {
  const notes = prompt('Disciplinary review note for escalation:', 'Flagged for academic review');
  if (notes === null) return;
  try {
    const res = await fetch(`/api/dashboard/flags/${flagId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ status: 'escalated', notes: notes }),
    });
    if (res.ok) {
      const card = document.getElementById(`flag-card-${flagId}`);
      if (card) {
        card.querySelector('div:last-child').innerHTML =
          '<span style="font-size: 11px; color: #f87171; font-weight: 600;">⚠️ Escalated for Review</span>';
      }
      if (state.selectedSessionId) loadActiveSessionRoster(state.selectedSessionId);
    }
  } catch (err) {
    console.error('Escalate flag error:', err);
  }
};

// Projector Modal
window.openProjector = function (code, title) {
  document.getElementById('projectorCodeDisplay').innerText = code;
  document.getElementById('projectorAssignmentTitle').innerText = title;
  document.getElementById('projectorModal').classList.add('active');
};

document.getElementById('projectCodeBtn').addEventListener('click', () => {
  const currentSess = state.sessions.find((s) => s.id === state.selectedSessionId);
  if (currentSess) {
    openProjector(currentSess.access_code, currentSess.assignment_title);
  } else {
    alert('Please select a session first.');
  }
});

document.getElementById('closeProjectorBtn').addEventListener('click', () => {
  document.getElementById('projectorModal').classList.remove('active');
});

// Modals: New Session
const newSessionModal = document.getElementById('newSessionModal');
document.getElementById('openNewSessionModalBtn').addEventListener('click', () => {
  newSessionModal.classList.add('active');
  // Preset 15 seconds
  presetSessionTime(15);
});
document.getElementById('closeSessionModalBtn').addEventListener('click', () => {
  newSessionModal.classList.remove('active');
});

function presetSessionTime(secondsAhead) {
  const d = new Date(Date.now() + secondsAhead * 1000);
  // Format for datetime-local input
  const localIso = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  document.getElementById('modalSessionStartTimeInput').value = localIso;
}

document.getElementById('presetStartNowBtn').addEventListener('click', () => presetSessionTime(15));
document.getElementById('presetStart2mBtn').addEventListener('click', () => presetSessionTime(120));

document.getElementById('createSessionConfirmBtn').addEventListener('click', async () => {
  const assignId = parseInt(document.getElementById('modalSessionAssignmentSelect').value);
  const startTime = document.getElementById('modalSessionStartTimeInput').value;

  if (!assignId || !startTime) {
    alert('Please select an assignment and start time.');
    return;
  }

  try {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({
        assignment_id: assignId,
        start_time: new Date(startTime).toISOString(),
      }),
    });
    if (!res.ok) throw new Error('Failed to launch session');
    const newSess = await res.json();
    newSessionModal.classList.remove('active');
    await loadSessions();
    selectSessionForMonitor(newSess.id);
    openProjector(newSess.access_code, newSess.assignment_title);
  } catch (err) {
    alert(err.message);
  }
});

// Modals: New Assignment
const newAssignmentModal = document.getElementById('newAssignmentModal');
document.getElementById('openNewAssignmentModalBtn').addEventListener('click', () => {
  newAssignmentModal.classList.add('active');
});
document.getElementById('closeAssignModalBtn').addEventListener('click', () => {
  newAssignmentModal.classList.remove('active');
});

document.getElementById('saveAssignmentConfirmBtn').addEventListener('click', async () => {
  const title = document.getElementById('modalAssignTitle').value.trim();
  const statement = document.getElementById('modalAssignStatement').value.trim();
  const langs = document.getElementById('modalAssignLangs').value.trim();
  const starter = document.getElementById('modalAssignStarter').value.trim();

  const visIn = document.getElementById('modalVisInput').value.trim();
  const visOut = document.getElementById('modalVisOutput').value.trim();
  const hidIn = document.getElementById('modalHidInput').value.trim();
  const hidOut = document.getElementById('modalHidOutput').value.trim();

  if (!title || !statement) {
    alert('Please provide a title and statement.');
    return;
  }

  const payload = {
    title: title,
    problem_statement: statement,
    starter_code: starter || '',
    language_set: langs || 'python,cpp,java',
    visible_test_cases: visIn ? [{ id: 'v1', input: visIn, expected_output: visOut }] : [],
    hidden_test_cases: hidIn ? [{ id: 'h1', input: hidIn, expected_output: hidOut }] : [],
  };

  try {
    const res = await fetch('/api/assignments', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to save assignment');
    newAssignmentModal.classList.remove('active');
    loadAssignments();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById('refreshMonitorBtn').addEventListener('click', refreshMonitorView);

function escapeHtml(text) {
  return String(text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Start
initApp();
