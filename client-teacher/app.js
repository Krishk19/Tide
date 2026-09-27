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
  triageStudents: [],
  activeZoneFilter: 'all',
  viewMode: 'table',
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

// Segmented Theme Toggle (Light / Dark mode)
const teacherThemeLightBtn = document.getElementById('teacherThemeLightBtn');
const teacherThemeDarkBtn = document.getElementById('teacherThemeDarkBtn');
const legacyTeacherToggleBtn = document.getElementById('themeToggleBtn');
const savedTheme = localStorage.getItem('tide_theme') || 'dark';
applyTheme(savedTheme);

if (teacherThemeLightBtn) {
  teacherThemeLightBtn.addEventListener('click', () => applyTheme('light'));
}
if (teacherThemeDarkBtn) {
  teacherThemeDarkBtn.addEventListener('click', () => applyTheme('dark'));
}
if (legacyTeacherToggleBtn) {
  legacyTeacherToggleBtn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.body.className = 'theme-' + theme;
  localStorage.setItem('tide_theme', theme);

  if (teacherThemeLightBtn && teacherThemeDarkBtn) {
    if (theme === 'light') {
      teacherThemeLightBtn.classList.add('active');
      teacherThemeDarkBtn.classList.remove('active');
    } else {
      teacherThemeDarkBtn.classList.add('active');
      teacherThemeLightBtn.classList.remove('active');
    }
  }
}

// DOM Elements
const authSection = document.getElementById('authSection');
const liveMonitorSection = document.getElementById('liveMonitorSection');
const sessionsSection = document.getElementById('sessionsSection');
const assignmentsSection = document.getElementById('assignmentsSection');
const similaritySection = document.getElementById('similaritySection');

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

    [liveMonitorSection, sessionsSection, assignmentsSection, similaritySection].forEach((sec) => {
      if (sec) sec.classList.remove('active');
    });
    const targetSec = document.getElementById(targetId);
    if (targetSec) targetSec.classList.add('active');

    if (targetId === 'sessionsSection') loadSessions();
    if (targetId === 'assignmentsSection') loadAssignments();
    if (targetId === 'liveMonitorSection') refreshMonitorView();
    if (targetId === 'similaritySection') initSimilarityView();
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
      const qCount = (a.questions && a.questions.length > 0) ? a.questions.length : 1;
      card.innerHTML = `
        <div style="font-weight: 600; font-size: 15px; margin-bottom: 8px; color: var(--text);">${escapeHtml(a.title)}</div>
        <p style="font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 14px;">${escapeHtml(a.problem_statement.substring(0, 110))}...</p>
        <div style="display: flex; gap: 6px; font-size: 11px; margin-bottom: 6px; flex-wrap: wrap;">
          <span class="badge">${a.language_set}</span>
          <span class="badge" style="background: rgba(56, 189, 248, 0.12); color: #38bdf8;">${qCount > 1 ? qCount + ' Questions' : '1 Question'}</span>
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
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 12px;" onclick="exportSession(${s.id}, 'csv')" title="Export Marksheet CSV">📥 CSV</button>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 12px;" onclick="exportSession(${s.id}, 'json')" title="Export Dossier JSON">📁 JSON</button>
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
    const [sessRes, triageRes] = await Promise.all([
      fetch(`/api/sessions/${sessionId}`, { headers: { Authorization: `Bearer ${state.token}` } }),
      fetch(`/api/dashboard/triage?session_id=${sessionId}`, { headers: { Authorization: `Bearer ${state.token}` } }),
    ]);

    if (!sessRes.ok) return;
    const session = await sessRes.json();
    const triageData = triageRes.ok ? await triageRes.json() : null;

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

    // Update Triage Pill Counters
    if (triageData && triageData.counts) {
      document.getElementById('countZoneAll').innerText = triageData.counts.all || 0;
      document.getElementById('countZoneGreen').innerText = triageData.counts.green || 0;
      document.getElementById('countZoneYellow').innerText = triageData.counts.yellow || 0;
      document.getElementById('countZoneRed').innerText = triageData.counts.red || 0;
      state.triageStudents = triageData.students || [];
    } else {
      state.triageStudents = (session.students || []).map(s => ({
        ...s,
        zone: s.risk_score >= 60 ? 'red' : 'green',
        zone_reason: 'Active session',
        is_submitted: !!s.submitted_at
      }));
    }

    renderTriageRoster();
  } catch (err) {
    console.error('Failed to load roster:', err);
  }
}

function renderTriageRoster() {
  const tbody = document.getElementById('studentRosterTbody');
  const gridContainer = document.getElementById('studentSeatGrid');
  tbody.innerHTML = '';
  gridContainer.innerHTML = '';

  const allStudents = state.triageStudents || [];
  const filtered = state.activeZoneFilter === 'all'
    ? allStudents
    : allStudents.filter(s => s.zone === state.activeZoneFilter);

  if (filtered.length === 0) {
    const emptyMsg = allStudents.length === 0
      ? 'No students have joined this session yet. Project code on board!'
      : `No students matching health filter "${state.activeZoneFilter}".`;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">${emptyMsg}</td></tr>`;
    gridContainer.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 24px;">${emptyMsg}</div>`;
    return;
  }

  filtered.forEach((st) => {
    // 1. Table Row
    const tr = document.createElement('tr');
    const autosaveTime = st.last_autosaved_at ? new Date(st.last_autosaved_at).toLocaleTimeString() : 'Never';
    const statusBadge = st.is_submitted
      ? '<span class="badge" style="background: rgba(16, 185, 129, 0.1); color: #34d399; border-color: rgba(16, 185, 129, 0.25);">SUBMITTED</span>'
      : '<span class="badge" style="background: rgba(255, 255, 255, 0.08); color: var(--text);">TAKING EXAM</span>';

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

    let zoneBadge = '<span class="badge" style="background: rgba(16, 185, 129, 0.12); color: #34d399; font-size: 10px;">🟢 ON TRACK</span>';
    if (st.zone === 'yellow') {
      zoneBadge = '<span class="badge" style="background: rgba(245, 158, 11, 0.12); color: #fbbf24; font-size: 10px;">🟡 STRUGGLING</span>';
    } else if (st.zone === 'red') {
      zoneBadge = '<span class="badge" style="background: rgba(244, 63, 94, 0.15); color: #fda4af; font-size: 10px;">🔴 SUSPICIOUS</span>';
    }

    const extraTimeBadge = st.extra_time_seconds > 0
      ? `<span class="badge" style="background: rgba(16, 185, 129, 0.12); color: #34d399; font-size: 10px; margin-left: 4px;">+${Math.round(st.extra_time_seconds / 60)}m</span>`
      : '';

    const playbackBtn = `<button class="btn btn-secondary" style="padding: 2px 7px; font-size: 10px;" onclick="openPlaybackModal(${st.id}, '${escapeHtml(st.student_name)}')" title="Interactive keystroke & growth replay">⏪ Playback</button>`;
    const timelineBtn = `<button class="btn btn-secondary" style="padding: 2px 7px; font-size: 10px;" onclick="openForensicTimeline(${st.id}, '${escapeHtml(st.student_name)}', '${escapeHtml(st.student_identifier)}', ${risk})" title="Chronological audit timeline">📜 Timeline</button>`;

    const actionsHtml = st.is_submitted
      ? `<div style="display: flex; gap: 4px; align-items: center;"><span style="color: var(--text-tertiary); font-size: 10px; font-family: var(--font-mono);">Done</span>${playbackBtn}${timelineBtn}</div>`
      : `
        <div style="display: flex; gap: 4px; flex-wrap: wrap;">
          <button class="btn btn-secondary" style="padding: 2px 7px; font-size: 10px;" onclick="extendStudentTime(${st.id}, 5)" title="Grant +5 minutes extra time">+5m</button>
          <button class="btn btn-secondary" style="padding: 2px 7px; font-size: 10px; color: var(--warning);" onclick="openWarnModal(${st.id}, '${escapeHtml(st.student_name)}')" title="Send official warning modal">⚠️ Warn</button>
          <button class="btn btn-secondary" style="padding: 2px 7px; font-size: 10px; color: var(--danger);" onclick="forceSubmitStudent(${st.id}, '${escapeHtml(st.student_name)}')" title="Remotely submit exam">🛑 Force</button>
          ${playbackBtn}
          ${timelineBtn}
        </div>
      `;

    tr.innerHTML = `
      <td><strong>${escapeHtml(st.student_name)}</strong></td>
      <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">${escapeHtml(st.student_identifier)}</td>
      <td><div title="${escapeHtml(st.zone_reason || '')}">${zoneBadge}</div></td>
      <td>${riskBadge}</td>
      <td style="font-size: 12px; font-family: var(--font-mono); color: var(--text-muted);">${autosaveTime}</td>
      <td>${statusBadge}${extraTimeBadge}</td>
      <td>${actionsHtml}</td>
    `;
    tbody.appendChild(tr);

    // 2. Visual Seat Card
    const seatCard = document.createElement('div');
    seatCard.className = `seat-card zone-${st.zone}`;
    seatCard.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
        <strong style="font-size: 12px; color: var(--text);">${escapeHtml(st.student_name)}</strong>
        <span style="font-size: 10px; font-family: var(--font-mono); color: var(--text-tertiary);">${escapeHtml(st.student_identifier)}</span>
      </div>
      <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px; line-height: 1.3;">${escapeHtml(st.zone_reason || '')}</div>
      <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border); padding-top: 6px;">
        <span style="font-size: 10px; font-family: var(--font-mono);">${st.lines_count || 0} lines</span>
        <div style="display: flex; gap: 4px;">
          <button class="btn btn-secondary" style="padding: 1px 5px; font-size: 9px;" onclick="openPlaybackModal(${st.id}, '${escapeHtml(st.student_name)}')" title="Replay code">⏪</button>
          <button class="btn btn-secondary" style="padding: 1px 5px; font-size: 9px;" onclick="openForensicTimeline(${st.id}, '${escapeHtml(st.student_name)}', '${escapeHtml(st.student_identifier)}', ${risk})" title="Audit timeline">📜</button>
          ${!st.is_submitted ? `<button class="btn btn-secondary" style="padding: 1px 5px; font-size: 9px;" onclick="extendStudentTime(${st.id}, 5)" title="+5m">+5m</button>` : ''}
        </div>
      </div>
    `;
    gridContainer.appendChild(seatCard);
  });
}

// Triage Filter Pills & View Mode Toggles
document.querySelectorAll('.triage-pill').forEach((pill) => {
  pill.addEventListener('click', () => {
    document.querySelectorAll('.triage-pill').forEach((p) => p.classList.remove('active'));
    pill.classList.add('active');
    state.activeZoneFilter = pill.dataset.zone || 'all';
    renderTriageRoster();
  });
});

const viewTableBtn = document.getElementById('viewModeTableBtn');
const viewGridBtn = document.getElementById('viewModeGridBtn');
const tableContainer = document.getElementById('tableContainer');
const seatGridContainer = document.getElementById('seatGridContainer');

if (viewTableBtn && viewGridBtn) {
  viewTableBtn.addEventListener('click', () => {
    state.viewMode = 'table';
    viewTableBtn.classList.add('active');
    viewGridBtn.classList.remove('active');
    if (tableContainer) tableContainer.style.display = 'block';
    if (seatGridContainer) seatGridContainer.style.display = 'none';
  });

  viewGridBtn.addEventListener('click', () => {
    state.viewMode = 'grid';
    viewGridBtn.classList.add('active');
    viewTableBtn.classList.remove('active');
    if (tableContainer) tableContainer.style.display = 'none';
    if (seatGridContainer) seatGridContainer.style.display = 'block';
  });
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

// ==========================================================================
// Modals: Author Assignment (Multi-Question & Multi-Testcase Support)
// ==========================================================================
const newAssignmentModal = document.getElementById('newAssignmentModal');
const cancelAssignModalBtn = document.getElementById('cancelAssignModalBtn');
const addAnotherQuestionBtn = document.getElementById('addAnotherQuestionBtn');
const questionsCountLabel = document.getElementById('questionsCountLabel');
const modalQuestionsListContainer = document.getElementById('modalQuestionsListContainer');

let modalQuestions = [];

function initDefaultModalQuestions() {
  modalQuestions = [
    {
      id: 'q1',
      title: 'Question 1',
      problem_statement: '',
      starter_code: '',
      visible_test_cases: [
        { id: 'v1', input: '', expected_output: '' }
      ],
      hidden_test_cases: [
        { id: 'h1', input: '', expected_output: '' }
      ]
    }
  ];
}

function syncModalQuestionsFromDOM() {
  const cards = document.querySelectorAll('.modal-question-card');
  cards.forEach((card, qIdx) => {
    if (!modalQuestions[qIdx]) return;
    const titleInput = card.querySelector('.q-title-input');
    const stmtInput = card.querySelector('.q-stmt-input');
    const starterInput = card.querySelector('.q-starter-input');

    if (titleInput) modalQuestions[qIdx].title = titleInput.value;
    if (stmtInput) modalQuestions[qIdx].problem_statement = stmtInput.value;
    if (starterInput) modalQuestions[qIdx].starter_code = starterInput.value;

    // Visible tests
    const visRows = card.querySelectorAll('.vis-test-row');
    const visTests = [];
    visRows.forEach((row, tIdx) => {
      const inp = row.querySelector('.test-input')?.value || '';
      const out = row.querySelector('.test-output')?.value || '';
      visTests.push({ id: `v${tIdx + 1}`, input: inp, expected_output: out });
    });
    modalQuestions[qIdx].visible_test_cases = visTests;

    // Hidden tests
    const hidRows = card.querySelectorAll('.hid-test-row');
    const hidTests = [];
    hidRows.forEach((row, tIdx) => {
      const inp = row.querySelector('.test-input')?.value || '';
      const out = row.querySelector('.test-output')?.value || '';
      hidTests.push({ id: `h${tIdx + 1}`, input: inp, expected_output: out });
    });
    modalQuestions[qIdx].hidden_test_cases = hidTests;
  });
}

function renderModalQuestions() {
  if (!modalQuestionsListContainer) return;
  modalQuestionsListContainer.innerHTML = '';
  if (questionsCountLabel) questionsCountLabel.innerText = modalQuestions.length;

  modalQuestions.forEach((q, qIdx) => {
    const card = document.createElement('div');
    card.className = 'card modal-question-card';
    card.style.background = 'var(--bg-surface)';
    card.style.border = '1px solid var(--border-light)';
    card.style.padding = '16px';
    card.style.borderRadius = '8px';
    card.style.marginBottom = '8px';

    const canDelete = modalQuestions.length > 1;

    let visTestsHtml = '';
    (q.visible_test_cases || []).forEach((tc, tIdx) => {
      visTestsHtml += `
        <div class="vis-test-row" style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-muted);">Visible Test Case #${tIdx + 1}</span>
            <button type="button" class="btn btn-secondary" style="padding: 1px 6px; font-size: 10px; color: var(--danger);" onclick="removeModalTestCase(${qIdx}, 'visible', ${tIdx})">✕ Remove</button>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div>
              <label style="font-size: 10px; color: var(--text-tertiary); display: block; margin-bottom: 3px;">Input (stdin)</label>
              <textarea class="test-input" rows="2" style="font-family: var(--font-mono); font-size: 11px; width: 100%;" placeholder="e.g. 5&#10;1 2 3 4 5">${escapeHtml(tc.input || '')}</textarea>
            </div>
            <div>
              <label style="font-size: 10px; color: var(--text-tertiary); display: block; margin-bottom: 3px;">Expected Output (stdout)</label>
              <textarea class="test-output" rows="2" style="font-family: var(--font-mono); font-size: 11px; width: 100%;" placeholder="e.g. 5 4 3 2 1">${escapeHtml(tc.expected_output || '')}</textarea>
            </div>
          </div>
        </div>
      `;
    });

    let hidTestsHtml = '';
    (q.hidden_test_cases || []).forEach((tc, tIdx) => {
      hidTestsHtml += `
        <div class="hid-test-row" style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-muted);">Hidden Test Case #${tIdx + 1}</span>
            <button type="button" class="btn btn-secondary" style="padding: 1px 6px; font-size: 10px; color: var(--danger);" onclick="removeModalTestCase(${qIdx}, 'hidden', ${tIdx})">✕ Remove</button>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div>
              <label style="font-size: 10px; color: var(--text-tertiary); display: block; margin-bottom: 3px;">Input (stdin)</label>
              <textarea class="test-input" rows="2" style="font-family: var(--font-mono); font-size: 11px; width: 100%;" placeholder="e.g. 100&#10;...">${escapeHtml(tc.input || '')}</textarea>
            </div>
            <div>
              <label style="font-size: 10px; color: var(--text-tertiary); display: block; margin-bottom: 3px;">Expected Output (stdout)</label>
              <textarea class="test-output" rows="2" style="font-family: var(--font-mono); font-size: 11px; width: 100%;" placeholder="e.g. expected stdout">${escapeHtml(tc.expected_output || '')}</textarea>
            </div>
          </div>
        </div>
      `;
    });

    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 8px; flex: 1;">
          <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 700; font-size: 11px;">Q${qIdx + 1}</span>
          <input type="text" class="q-title-input" value="${escapeHtml(q.title || `Question ${qIdx + 1}`)}" placeholder="Question Title (e.g. Palindrome Check)" style="font-weight: 600; font-size: 13px; flex: 1; max-width: 380px; padding: 4px 8px;" />
        </div>
        ${canDelete ? `<button type="button" class="btn btn-secondary" style="padding: 2px 8px; font-size: 11px; color: var(--danger);" onclick="removeModalQuestion(${qIdx})">✕ Delete Question</button>` : ''}
      </div>

      <div class="form-group" style="margin-bottom: 10px;">
        <label style="font-size: 11.5px; font-weight: 600;">Problem Statement & Specifications</label>
        <textarea class="q-stmt-input" rows="3" placeholder="Enter problem statement, input/output formats, constraints..." style="font-size: 12px;">${escapeHtml(q.problem_statement || '')}</textarea>
      </div>

      <div class="form-group" style="margin-bottom: 14px;">
        <label style="font-size: 11.5px; font-weight: 600;">Starter Code (Optional)</label>
        <textarea class="q-starter-input" rows="3" style="font-family: var(--font-mono); font-size: 11px;" placeholder="# Initial code loaded in student editor&#10;def solve():&#10;    pass">${escapeHtml(q.starter_code || '')}</textarea>
      </div>

      <!-- Test Cases Grid -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; border-top: 1px solid var(--border); padding-top: 10px;">
        <!-- Visible Tests Column -->
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div>
              <strong style="font-size: 11.5px; color: var(--text);">Visible Test Cases (${(q.visible_test_cases || []).length})</strong>
              <div style="font-size: 10px; color: var(--text-tertiary);">Runs locally on kiosk when student tests code</div>
            </div>
            <button type="button" class="btn btn-secondary" style="font-size: 10px; padding: 2px 7px;" onclick="addModalTestCase(${qIdx}, 'visible')">+ Add Test</button>
          </div>
          <div class="vis-tests-container">${visTestsHtml || '<div style="color: var(--text-disabled); font-size: 11px; font-style: italic; padding: 8px 0;">No visible test cases yet.</div>'}</div>
        </div>

        <!-- Hidden Tests Column -->
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div>
              <strong style="font-size: 11.5px; color: var(--text);">Hidden Test Cases (${(q.hidden_test_cases || []).length})</strong>
              <div style="font-size: 10px; color: var(--text-tertiary);">Never sent to kiosk; server evaluates on submission</div>
            </div>
            <button type="button" class="btn btn-secondary" style="font-size: 10px; padding: 2px 7px;" onclick="addModalTestCase(${qIdx}, 'hidden')">+ Add Test</button>
          </div>
          <div class="hid-tests-container">${hidTestsHtml || '<div style="color: var(--text-disabled); font-size: 11px; font-style: italic; padding: 8px 0;">No hidden test cases yet.</div>'}</div>
        </div>
      </div>
    `;

    modalQuestionsListContainer.appendChild(card);
  });
}

window.addModalTestCase = function(qIdx, type) {
  syncModalQuestionsFromDOM();
  if (!modalQuestions[qIdx]) return;
  if (type === 'visible') {
    modalQuestions[qIdx].visible_test_cases = modalQuestions[qIdx].visible_test_cases || [];
    modalQuestions[qIdx].visible_test_cases.push({
      id: `v${modalQuestions[qIdx].visible_test_cases.length + 1}`,
      input: '',
      expected_output: ''
    });
  } else {
    modalQuestions[qIdx].hidden_test_cases = modalQuestions[qIdx].hidden_test_cases || [];
    modalQuestions[qIdx].hidden_test_cases.push({
      id: `h${modalQuestions[qIdx].hidden_test_cases.length + 1}`,
      input: '',
      expected_output: ''
    });
  }
  renderModalQuestions();
};

window.removeModalTestCase = function(qIdx, type, tIdx) {
  syncModalQuestionsFromDOM();
  if (!modalQuestions[qIdx]) return;
  if (type === 'visible' && modalQuestions[qIdx].visible_test_cases) {
    modalQuestions[qIdx].visible_test_cases.splice(tIdx, 1);
  } else if (type === 'hidden' && modalQuestions[qIdx].hidden_test_cases) {
    modalQuestions[qIdx].hidden_test_cases.splice(tIdx, 1);
  }
  renderModalQuestions();
};

window.removeModalQuestion = function(qIdx) {
  syncModalQuestionsFromDOM();
  if (modalQuestions.length > 1) {
    modalQuestions.splice(qIdx, 1);
    renderModalQuestions();
  }
};

if (addAnotherQuestionBtn) {
  addAnotherQuestionBtn.addEventListener('click', () => {
    syncModalQuestionsFromDOM();
    const nextNum = modalQuestions.length + 1;
    modalQuestions.push({
      id: `q${nextNum}`,
      title: `Question ${nextNum}`,
      problem_statement: '',
      starter_code: '',
      visible_test_cases: [{ id: 'v1', input: '', expected_output: '' }],
      hidden_test_cases: [{ id: 'h1', input: '', expected_output: '' }]
    });
    renderModalQuestions();
  });
}

const openNewAssignmentModalBtn = document.getElementById('openNewAssignmentModalBtn');
if (openNewAssignmentModalBtn) {
  openNewAssignmentModalBtn.addEventListener('click', () => {
    document.getElementById('modalAssignTitle').value = '';
    document.getElementById('modalAssignLangs').value = 'python,cpp,java';
    initDefaultModalQuestions();
    renderModalQuestions();
    newAssignmentModal.classList.add('active');
  });
}

const closeAssignModalBtn = document.getElementById('closeAssignModalBtn');
if (closeAssignModalBtn) {
  closeAssignModalBtn.addEventListener('click', () => {
    newAssignmentModal.classList.remove('active');
  });
}

if (cancelAssignModalBtn) {
  cancelAssignModalBtn.addEventListener('click', () => {
    newAssignmentModal.classList.remove('active');
  });
}

const saveAssignmentConfirmBtn = document.getElementById('saveAssignmentConfirmBtn');
if (saveAssignmentConfirmBtn) {
  saveAssignmentConfirmBtn.addEventListener('click', async () => {
    syncModalQuestionsFromDOM();
    const title = document.getElementById('modalAssignTitle').value.trim();
    const langs = document.getElementById('modalAssignLangs').value.trim() || 'python,cpp,java';

    if (!title) {
      alert('Please enter an Assessment Title.');
      return;
    }

    const hasStmt = modalQuestions.some(q => q.problem_statement && q.problem_statement.trim().length > 0);
    if (!hasStmt) {
      alert('Please provide a problem statement for at least one question.');
      return;
    }

    // Clean questions
    const cleanQuestions = modalQuestions.map((q, idx) => ({
      id: q.id || `q${idx + 1}`,
      title: q.title?.trim() || `Question ${idx + 1}`,
      problem_statement: q.problem_statement?.trim() || '',
      starter_code: q.starter_code || '',
      visible_test_cases: (q.visible_test_cases || []).filter(t => (t.input && t.input.trim()) || (t.expected_output && t.expected_output.trim())),
      hidden_test_cases: (q.hidden_test_cases || []).filter(t => (t.input && t.input.trim()) || (t.expected_output && t.expected_output.trim()))
    }));

    const firstQ = cleanQuestions[0];
    const payload = {
      title: title,
      language_set: langs,
      problem_statement: firstQ.problem_statement,
      starter_code: firstQ.starter_code,
      visible_test_cases: firstQ.visible_test_cases,
      hidden_test_cases: firstQ.hidden_test_cases,
      questions: cleanQuestions
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
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to save assessment');
      }
      newAssignmentModal.classList.remove('active');
      loadAssignments();
    } catch (err) {
      alert(err.message);
    }
  });
}

document.getElementById('refreshMonitorBtn').addEventListener('click', refreshMonitorView);

// Remote Classroom Controls
window.extendStudentTime = async function(studentId, minutes = 5) {
  if (!state.selectedSessionId || !state.token) return;
  try {
    const res = await fetch(`/api/sessions/${state.selectedSessionId}/students/${studentId}/extend-time`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ added_minutes: minutes, reason: 'Compensatory time granted by instructor' }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to extend time');
    }
    loadActiveSessionRoster(state.selectedSessionId);
  } catch (err) {
    alert(`Error extending time: ${err.message}`);
  }
};

window.openWarnModal = function(studentId, studentName) {
  document.getElementById('warnTargetStudentId').value = studentId;
  document.getElementById('warnModalTitle').innerText = `Send Warning to ${studentName}`;
  document.getElementById('warnMessageInput').value = 'Warning from Instructor: Maintain exam focus on your screen. Suspicious movement has been logged.';
  document.getElementById('warnStudentModal').classList.add('active');
};

document.getElementById('closeWarnModalBtn').addEventListener('click', () => {
  document.getElementById('warnStudentModal').classList.remove('active');
});

document.getElementById('sendWarnConfirmBtn').addEventListener('click', async () => {
  const studentId = document.getElementById('warnTargetStudentId').value;
  const message = document.getElementById('warnMessageInput').value.trim();
  if (!studentId || !message || !state.selectedSessionId) return;

  try {
    const res = await fetch(`/api/sessions/${state.selectedSessionId}/students/${studentId}/warn`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ message: message }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to send warning');
    }
    document.getElementById('warnStudentModal').classList.remove('active');
  } catch (err) {
    alert(`Error sending warning: ${err.message}`);
  }
});

window.forceSubmitStudent = async function(studentId, studentName) {
  if (!confirm(`Are you sure you want to remotely freeze and finalize submission for ${studentName}?\nThis action cannot be undone.`)) {
    return;
  }
  if (!state.selectedSessionId || !state.token) return;

  try {
    const res = await fetch(`/api/sessions/${state.selectedSessionId}/students/${studentId}/force-submit`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${state.token}`,
      },
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to force submit');
    }
    loadActiveSessionRoster(state.selectedSessionId);
  } catch (err) {
    alert(`Error force submitting: ${err.message}`);
  }
};

// Modals: Broadcast Announcement
const broadcastModal = document.getElementById('broadcastModal');
document.getElementById('broadcastModalBtn').addEventListener('click', () => {
  if (!state.selectedSessionId) {
    alert('Please select an active session first.');
    return;
  }
  broadcastModal.classList.add('active');
});
document.getElementById('closeBroadcastModalBtn').addEventListener('click', () => {
  broadcastModal.classList.remove('active');
});

document.getElementById('sendBroadcastConfirmBtn').addEventListener('click', async () => {
  if (!state.selectedSessionId || !state.token) return;
  const msg = document.getElementById('broadcastMessageTextarea').value.trim();
  const type = document.getElementById('broadcastTypeSelect').value;

  if (!msg) {
    alert('Please write an announcement notice.');
    return;
  }

  try {
    const res = await fetch(`/api/sessions/${state.selectedSessionId}/broadcast`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ message: msg, type: type }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to broadcast announcement');
    }
    const data = await res.json();
    broadcastModal.classList.remove('active');
    document.getElementById('broadcastMessageTextarea').value = '';
    alert(`Announcement broadcast to ${data.recipient_count} student terminals.`);
  } catch (err) {
    alert(`Broadcast error: ${err.message}`);
  }
});

// ==========================================================================
// Code Playback Forensic Scrubber System
// ==========================================================================
const playbackState = {
  data: null,
  currentIndex: 0,
  isPlaying: false,
  timer: null,
  speed: 5,
};

window.openPlaybackModal = async function(studentId, studentName) {
  if (!state.selectedSessionId || !state.token) return;
  try {
    const res = await fetch(`/api/sessions/${state.selectedSessionId}/students/${studentId}/playback`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to load playback data');
    }
    const data = await res.json();
    playbackState.data = data;
    playbackState.currentIndex = 0;
    playbackState.isPlaying = false;
    if (playbackState.timer) clearInterval(playbackState.timer);

    // Populate modal headers
    document.getElementById('playbackStudentTitle').innerText = `${data.student_name} (${data.student_identifier})`;
    const mins = Math.floor(data.total_duration_seconds / 60);
    const secs = data.total_duration_seconds % 60;
    document.getElementById('playbackStudentSubtitle').innerText = `${data.assignment_title} • ${data.total_snapshots} Keyframes Recorded • Duration: ${mins}m ${secs}s`;

    // Configure slider
    const slider = document.getElementById('playbackTimelineSlider');
    slider.min = 0;
    slider.max = Math.max(0, data.snapshots.length - 1);
    slider.value = 0;

    // Render timeline markers
    renderPlaybackMarkers(data);

    // Render initial keyframe
    renderPlaybackKeyframe(0);

    // Reset Play button
    document.getElementById('pbPlayToggleBtn').innerText = '▶ Play';

    // Show modal
    document.getElementById('playbackModal').classList.add('active');
  } catch (err) {
    alert(`Playback error: ${err.message}`);
  }
};

function renderPlaybackMarkers(data) {
  const track = document.getElementById('playbackMarkerTrack');
  track.innerHTML = '';
  const totalSnapshots = data.snapshots.length;
  if (totalSnapshots <= 1) return;

  // Add dots on track for paste events
  data.snapshots.forEach((s, idx) => {
    if (s.is_paste_event || s.delta_chars >= 40) {
      const pct = (idx / (totalSnapshots - 1)) * 100;
      const dot = document.createElement('div');
      dot.style.position = 'absolute';
      dot.style.left = `${pct}%`;
      dot.style.top = '2px';
      dot.style.width = '8px';
      dot.style.height = '8px';
      dot.style.borderRadius = '50%';
      dot.style.background = '#f43f5e';
      dot.style.transform = 'translateX(-50%)';
      dot.title = `Paste Keyframe ${idx + 1}: +${s.delta_chars} chars at ${s.time_str}`;
      dot.style.cursor = 'pointer';
      dot.onclick = () => {
        playbackState.currentIndex = idx;
        renderPlaybackKeyframe(idx);
      };
      track.appendChild(dot);
    }
  });
}

function renderPlaybackKeyframe(index) {
  if (!playbackState.data || !playbackState.data.snapshots.length) return;
  const snapshots = playbackState.data.snapshots;
  const safeIdx = Math.max(0, Math.min(index, snapshots.length - 1));
  playbackState.currentIndex = safeIdx;

  const current = snapshots[safeIdx];
  const slider = document.getElementById('playbackTimelineSlider');
  slider.value = safeIdx;

  // Display code
  document.getElementById('playbackCodeDisplay').innerText = current.code || '(empty starter code)';
  document.getElementById('playbackCodeStats').innerText = `Lines: ${current.lines_count} • Characters: ${current.chars_count} • Δ: +${current.delta_chars}c / +${current.delta_lines}L`;
  document.getElementById('playbackKeyframeTs').innerText = `Snapshot: ${current.time_str}`;

  // Time label
  const curMins = String(Math.floor(current.relative_seconds / 60)).padStart(2, '0');
  const curSecs = String(current.relative_seconds % 60).padStart(2, '0');
  document.getElementById('playbackCurrentTimeLabel').innerText = `${curMins}:${curSecs} (Keyframe ${safeIdx + 1} of ${snapshots.length})`;

  const totMins = String(Math.floor(playbackState.data.total_duration_seconds / 60)).padStart(2, '0');
  const totSecs = String(playbackState.data.total_duration_seconds % 60).padStart(2, '0');
  document.getElementById('playbackTotalTimeLabel').innerText = `Duration: ${totMins}:${totSecs}`;

  // Anomaly Callout Banner
  const anomalyBanner = document.getElementById('playbackAnomalyBanner');
  const anomalyText = document.getElementById('playbackAnomalyText');
  if (current.is_paste_event || current.delta_chars >= 40) {
    anomalyBanner.style.display = 'block';
    anomalyText.innerText = `Sudden bulk insertion of +${current.delta_chars} characters (+${current.delta_lines} lines) detected at ${current.time_str}. External paste or copied template.`;
  } else {
    anomalyBanner.style.display = 'none';
  }
}

// Scrubber Controls
document.getElementById('playbackTimelineSlider').addEventListener('input', (e) => {
  renderPlaybackKeyframe(Number(e.target.value));
});

document.getElementById('pbFirstBtn').addEventListener('click', () => {
  renderPlaybackKeyframe(0);
});

document.getElementById('pbPrevBtn').addEventListener('click', () => {
  renderPlaybackKeyframe(playbackState.currentIndex - 1);
});

document.getElementById('pbNextBtn').addEventListener('click', () => {
  renderPlaybackKeyframe(playbackState.currentIndex + 1);
});

document.getElementById('pbLastBtn').addEventListener('click', () => {
  if (playbackState.data) {
    renderPlaybackKeyframe(playbackState.data.snapshots.length - 1);
  }
});

document.getElementById('pbPlayToggleBtn').addEventListener('click', () => {
  if (playbackState.isPlaying) {
    // Pause
    playbackState.isPlaying = false;
    clearInterval(playbackState.timer);
    document.getElementById('pbPlayToggleBtn').innerText = '▶ Play';
  } else {
    // Play
    if (!playbackState.data || !playbackState.data.snapshots.length) return;
    if (playbackState.currentIndex >= playbackState.data.snapshots.length - 1) {
      playbackState.currentIndex = 0;
      renderPlaybackKeyframe(0);
    }
    playbackState.isPlaying = true;
    document.getElementById('pbPlayToggleBtn').innerText = '⏸ Pause';

    const speed = Number(document.getElementById('playbackSpeedSelect').value) || 5;
    const intervalMs = Math.max(100, Math.floor(1000 / speed));

    playbackState.timer = setInterval(() => {
      if (playbackState.currentIndex < playbackState.data.snapshots.length - 1) {
        renderPlaybackKeyframe(playbackState.currentIndex + 1);
      } else {
        playbackState.isPlaying = false;
        clearInterval(playbackState.timer);
        document.getElementById('pbPlayToggleBtn').innerText = '▶ Play';
      }
    }, intervalMs);
  }
});

document.getElementById('playbackSpeedSelect').addEventListener('change', () => {
  if (playbackState.isPlaying) {
    // Restart interval with new speed
    clearInterval(playbackState.timer);
    const speed = Number(document.getElementById('playbackSpeedSelect').value) || 5;
    const intervalMs = Math.max(100, Math.floor(1000 / speed));
    playbackState.timer = setInterval(() => {
      if (playbackState.currentIndex < playbackState.data.snapshots.length - 1) {
        renderPlaybackKeyframe(playbackState.currentIndex + 1);
      } else {
        playbackState.isPlaying = false;
        clearInterval(playbackState.timer);
        document.getElementById('pbPlayToggleBtn').innerText = '▶ Play';
      }
    }, intervalMs);
  }
});

document.getElementById('closePlaybackModalBtn').addEventListener('click', () => {
  if (playbackState.timer) clearInterval(playbackState.timer);
  playbackState.isPlaying = false;
  document.getElementById('playbackModal').classList.remove('active');
});

function escapeHtml(text) {
  return String(text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ==========================================================================
// AST Code Similarity & Plagiarism Studio
// ==========================================================================
function initSimilarityView() {
  const select = document.getElementById('similaritySessionSelect');
  if (!select) return;

  select.innerHTML = '';
  if (!state.sessions || state.sessions.length === 0) {
    select.innerHTML = '<option value="">No sessions available</option>';
    return;
  }

  state.sessions.forEach((s) => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = `${s.access_code} - ${s.assignment_title} (${s.status})`;
    if (s.id === state.selectedSessionId) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });

  if (!state.selectedSessionId && state.sessions.length > 0) {
    select.value = state.sessions[0].id;
  }

  loadSimilarityMatrix();
}

const runSimilarityScanBtn = document.getElementById('runSimilarityScanBtn');
if (runSimilarityScanBtn) {
  runSimilarityScanBtn.addEventListener('click', () => loadSimilarityMatrix());
}

const similaritySessionSelect = document.getElementById('similaritySessionSelect');
if (similaritySessionSelect) {
  similaritySessionSelect.addEventListener('change', () => loadSimilarityMatrix());
}

const similarityThresholdSelect = document.getElementById('similarityThresholdSelect');
if (similarityThresholdSelect) {
  similarityThresholdSelect.addEventListener('change', () => loadSimilarityMatrix());
}

async function loadSimilarityMatrix() {
  const select = document.getElementById('similaritySessionSelect');
  const threshSelect = document.getElementById('similarityThresholdSelect');
  const tbody = document.getElementById('similarityTableBody');
  if (!select || !select.value) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">Please select a session first.</td></tr>';
    return;
  }

  const sessionId = select.value;
  const threshold = threshSelect ? threshSelect.value : 65;

  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">Computing AST representations and cross-student similarity matrix...</td></tr>';
  }

  try {
    const res = await fetch(`/api/sessions/${sessionId}/similarity-matrix?threshold=${threshold}`, {
      headers: { Authorization: `Bearer ${state.token}` }
    });
    if (!res.ok) throw new Error('Failed to compute similarity matrix');
    const data = await res.json();

    document.getElementById('simKpiStudents').innerText = data.total_students || 0;
    document.getElementById('simKpiPairs').innerText = data.total_pairs_compared || 0;
    document.getElementById('simKpiFlagged').innerText = data.flagged_pairs_count || 0;

    if (!data.pairs || data.pairs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 36px 20px;">✓ No code similarity found exceeding ${threshold}% threshold across ${data.total_pairs_compared} student pair comparisons. Clean exam session.</td></tr>`;
      return;
    }

    tbody.innerHTML = '';
    data.pairs.forEach((pair, idx) => {
      const tr = document.createElement('tr');
      const score = pair.similarity_pct;
      let badgeClass = 'low';
      if (score >= 75) badgeClass = 'high';
      else if (score >= 50) badgeClass = 'medium';

      const tagsHtml = (pair.correlation_tags || []).map(t => {
        const isAlert = t.includes('Paste') || t.includes('Cheat') || t.includes('Near-Identical');
        return `<span class="correlation-tag ${isAlert ? 'alert' : ''}">${escapeHtml(t)}</span>`;
      }).join('');

      tr.innerHTML = `
        <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-tertiary);">#${idx + 1}</td>
        <td>
          <strong>${escapeHtml(pair.student_a.name)}</strong>
          <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(pair.student_a.identifier)}</div>
        </td>
        <td>
          <strong>${escapeHtml(pair.student_b.name)}</strong>
          <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(pair.student_b.identifier)}</div>
        </td>
        <td>
          <span class="similarity-match-badge ${badgeClass}">${score}% Match</span>
          <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-tertiary); margin-top: 2px;">${pair.shared_kgrams} shared k-grams</div>
        </td>
        <td style="font-family: var(--font-mono); font-size: 11px; text-transform: uppercase;">${escapeHtml(pair.language)}</td>
        <td>${tagsHtml || '<span style="color: var(--text-tertiary); font-size: 11px;">None</span>'}</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 11px;" onclick="openSimilarityDiffModal(${sessionId}, ${pair.student_a.id}, ${pair.student_b.id})">🔍 Compare Diff</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--danger); padding: 24px;">${escapeHtml(err.message)}</td></tr>`;
  }
}

window.openSimilarityDiffModal = async function(sessionId, stAId, stBId) {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/similarity-diff?student_a=${stAId}&student_b=${stBId}`, {
      headers: { Authorization: `Bearer ${state.token}` }
    });
    if (!res.ok) throw new Error('Failed to load code diff');
    const diff = await res.json();

    document.getElementById('simDiffScoreBadge').innerText = `${diff.similarity_pct}% Structural Match`;
    document.getElementById('simDiffStudentAName').innerText = diff.student_a.name;
    document.getElementById('simDiffStudentARoll').innerText = `(${diff.student_a.identifier})`;
    document.getElementById('simDiffStudentAMeta').innerText = `${diff.student_a.line_count} lines • ${diff.student_a.language}`;
    document.getElementById('simDiffCodeA').innerText = diff.student_a.code || '// No code submitted';

    document.getElementById('simDiffStudentBName').innerText = diff.student_b.name;
    document.getElementById('simDiffStudentBRoll').innerText = `(${diff.student_b.identifier})`;
    document.getElementById('simDiffStudentBMeta').innerText = `${diff.student_b.line_count} lines • ${diff.student_b.language}`;
    document.getElementById('simDiffCodeB').innerText = diff.student_b.code || '// No code submitted';

    // Tags
    const tagsContainer = document.getElementById('simDiffCorrelationTags');
    tagsContainer.innerHTML = '';
    const tags = diff.correlation_tags || [];
    if (diff.similarity_pct >= 90) tags.push('Near-Identical AST Structure');
    tags.forEach(t => {
      const span = document.createElement('span');
      span.className = 'correlation-tag alert';
      span.innerText = t;
      tagsContainer.appendChild(span);
    });

    // Unified diff
    document.getElementById('simDiffUnifiedText').innerText = diff.diff_text || 'Exact identical code blocks or AST match.';

    document.getElementById('similarityDiffModal').classList.add('active');
  } catch (err) {
    alert(err.message);
  }
};

const closeSimDiffModalBtn = document.getElementById('closeSimilarityDiffModalBtn');
if (closeSimDiffModalBtn) {
  closeSimDiffModalBtn.addEventListener('click', () => {
    document.getElementById('similarityDiffModal').classList.remove('active');
  });
}

const simDiffUnifiedToggle = document.getElementById('simDiffUnifiedToggle');
if (simDiffUnifiedToggle) {
  simDiffUnifiedToggle.addEventListener('click', () => {
    const body = document.getElementById('simDiffUnifiedBody');
    const label = document.getElementById('simDiffToggleLabel');
    if (body.style.display === 'none') {
      body.style.display = 'block';
      if (label) label.innerText = 'Hide Raw Diff ▴';
    } else {
      body.style.display = 'none';
      if (label) label.innerText = 'Toggle Raw Diff ▾';
    }
  });
}

// ==========================================================================
// University Marksheet (CSV) & Full Dossier (JSON) Export Handlers
// ==========================================================================
window.exportSession = async function(sessionId, format) {
  const sessId = sessionId || state.selectedSessionId;
  if (!sessId) {
    alert('Please select an active session first.');
    return;
  }
  try {
    const res = await fetch(`/api/sessions/${sessId}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${state.token}` }
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to export session dossier');
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = format === 'csv' ? `marksheet_session_${sessId}.csv` : `dossier_session_${sessId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    alert('Export error: ' + err.message);
  }
};

const exportMarksheetBtn = document.getElementById('exportMarksheetBtn');
if (exportMarksheetBtn) {
  exportMarksheetBtn.addEventListener('click', () => {
    window.exportSession(state.selectedSessionId, 'csv');
  });
}

const exportDossierBtn = document.getElementById('exportDossierBtn');
if (exportDossierBtn) {
  exportDossierBtn.addEventListener('click', () => {
    window.exportSession(state.selectedSessionId, 'json');
  });
}

// ==========================================================================
// Forensic Timeline Modal Handlers
// ==========================================================================
window.openForensicTimeline = async function(studentId, studentName, studentIdentifier, riskScore) {
  if (!state.selectedSessionId || !state.token) {
    alert('Please select an active session first.');
    return;
  }

  const modal = document.getElementById('forensicTimelineModal');
  const titleEl = document.getElementById('timelineStudentTitle');
  const badgeEl = document.getElementById('timelineRiskBadge');
  const metaEl = document.getElementById('timelineStudentMeta');
  const listEl = document.getElementById('forensicTimelineList');

  if (titleEl) titleEl.innerText = `${studentName} (${studentIdentifier})`;
  if (metaEl) metaEl.innerText = `Full chronological forensic audit trail for Student ID #${studentId}`;

  const score = riskScore != null ? Number(riskScore) : 0;
  if (badgeEl) {
    badgeEl.innerText = `Risk: ${score}/100`;
    if (score >= 50) {
      badgeEl.style.background = 'rgba(244, 63, 94, 0.15)';
      badgeEl.style.color = '#fda4af';
    } else if (score >= 20) {
      badgeEl.style.background = 'rgba(245, 158, 11, 0.15)';
      badgeEl.style.color = '#fbbf24';
    } else {
      badgeEl.style.background = 'rgba(34, 197, 94, 0.15)';
      badgeEl.style.color = '#4ade80';
    }
  }

  if (listEl) {
    listEl.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; text-align: center; padding: 28px;">Loading forensic audit timeline...</div>';
  }
  if (modal) modal.classList.add('active');

  try {
    const res = await fetch(`/api/sessions/${state.selectedSessionId}/students/${studentId}/timeline`, {
      headers: { Authorization: `Bearer ${state.token}` }
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to retrieve timeline');
    }
    const data = await res.json();
    const events = data.events || [];

    if (events.length === 0) {
      if (listEl) listEl.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; text-align: center; padding: 28px;">No audit events recorded for this terminal.</div>';
      return;
    }

    if (listEl) {
      listEl.innerHTML = '';
      events.forEach((ev) => {
        const item = document.createElement('div');
        let borderColor = 'var(--border)';
        let badgeBg = 'var(--bg-subtle)';
        let badgeColor = 'var(--text-muted)';

        if (ev.severity === 'critical') {
          borderColor = 'rgba(244, 63, 94, 0.4)';
          badgeBg = 'rgba(244, 63, 94, 0.15)';
          badgeColor = '#fda4af';
        } else if (ev.severity === 'warning' || ev.severity === 'high') {
          borderColor = 'rgba(245, 158, 11, 0.4)';
          badgeBg = 'rgba(245, 158, 11, 0.15)';
          badgeColor = '#fbbf24';
        } else if (ev.severity === 'success') {
          borderColor = 'rgba(16, 185, 129, 0.4)';
          badgeBg = 'rgba(16, 185, 129, 0.15)';
          badgeColor = '#34d399';
        } else if (ev.severity === 'info') {
          borderColor = 'rgba(56, 189, 248, 0.4)';
          badgeBg = 'rgba(56, 189, 248, 0.15)';
          badgeColor = '#38bdf8';
        }

        item.style.cssText = `background: var(--bg-surface); border: 1px solid ${borderColor}; border-radius: 6px; padding: 10px 14px; display: flex; flex-direction: column; gap: 4px;`;

        const timeStr = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : '--:--:--';
        item.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="badge" style="background: ${badgeBg}; color: ${badgeColor}; font-size: 10px; font-weight: 700;">${escapeHtml(ev.badge || ev.type)}</span>
              <strong style="font-size: 12.5px; color: var(--text);">${escapeHtml(ev.title)}</strong>
            </div>
            <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary);">${timeStr}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-muted); line-height: 1.4;">${escapeHtml(ev.description)}</div>
        `;
        listEl.appendChild(item);
      });
    }
  } catch (err) {
    if (listEl) listEl.innerHTML = `<div style="color: var(--danger); font-size: 12px; text-align: center; padding: 24px;">${escapeHtml(err.message)}</div>`;
  }
};

const closeTimelineModalBtn = document.getElementById('closeTimelineModalBtn');
if (closeTimelineModalBtn) {
  closeTimelineModalBtn.addEventListener('click', () => {
    const modal = document.getElementById('forensicTimelineModal');
    if (modal) modal.classList.remove('active');
  });
}

// Start
initApp();
