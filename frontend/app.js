/* ── Config ── */
// Switch between local and hosted backend
const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API = IS_LOCAL ? 'http://localhost:8000' : 'https://footballgpt-backend.onrender.com';

/* ── State ── */
let isTyping = false;

/* ── DOM References ── */
const messagesEl  = document.getElementById('messages');
const chatInput   = document.getElementById('chat-input');
const sendBtn     = document.getElementById('send-btn');
const statusDot   = document.getElementById('status-dot');
const statusText  = document.getElementById('status-text');
const statTotal   = document.getElementById('stat-total');
const statAcc     = document.getElementById('stat-accuracy');
const statFix     = document.getElementById('stat-fixtures');
const teamA       = document.getElementById('team-a');
const teamB       = document.getElementById('team-b');
const btnRefresh  = document.getElementById('btn-refresh');
const btnSummary  = document.getElementById('btn-summary');

/* ── Init ─────────────────────────────────────────────────────── */

async function init() {
  bindEvents();
  await checkHealth();
  await loadStats();
}

function bindEvents() {
  // Send button
  sendBtn.addEventListener('click', sendMessage);

  // Enter to send, Shift+Enter for newline
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea
  chatInput.addEventListener('input', () => autoResize(chatInput));

  // Sidebar buttons
  btnRefresh.addEventListener('click', refreshMatches);
  btnSummary.addEventListener('click', loadSummary);

  // Competition pills
  document.querySelectorAll('.pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      askAbout(pill.dataset.comp);
    });
  });

  // Suggestion chips
  document.querySelectorAll('.suggestion').forEach((btn) => {
    btn.addEventListener('click', () => {
      chatInput.value = btn.textContent;
      sendMessage();
    });
  });
}

/* ── Health & Stats ────────────────────────────────────────────── */

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const data = await r.json();

    if (data.football_api_key_set && data.anthropic_api_key_set) {
      statusDot.classList.add('online');
      statusText.textContent = 'all systems go';
    } else {
      const missing = [];
      if (!data.football_api_key_set) missing.push('football key');
      if (!data.anthropic_api_key_set) missing.push('anthropic key');
      statusText.textContent = `missing: ${missing.join(', ')}`;
      showToast(`⚠️ Missing API keys: ${missing.join(', ')}`, 5000);
    }
  } catch {
    statusText.textContent = 'backend offline';
    showToast('⚠️ Cannot connect to backend. Is it running on port 8000?', 5000);
  }
}

async function loadStats() {
  try {
    const [predR, matchR] = await Promise.all([
      fetch(`${API}/predictions`),
      fetch(`${API}/matches/upcoming`),
    ]);
    const predData  = await predR.json();
    const matchData = await matchR.json();

    statTotal.textContent = predData.accuracy?.total ?? 0;
    const acc = predData.accuracy?.accuracy;
    statAcc.textContent = acc != null ? `${acc}%` : 'N/A';
    statFix.textContent = matchData.count ?? 0;
  } catch {
    // Silently fail — backend may not be running yet
  }
}

/* ── Messages ─────────────────────────────────────────────────── */

function hideWelcome() {
  const w = document.getElementById('welcome');
  if (w) w.remove();
}

function appendMessage(role, text, extra = {}) {
  hideWelcome();

  const wrap = document.createElement('div');
  wrap.className = `message ${role}`;

  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (role === 'system-msg') {
    wrap.innerHTML = `<div class="message-text" style="color:var(--text-dim);font-size:13px;">${text}</div>`;
  } else {
    const avatar = role === 'assistant'
      ? `<div class="avatar ai">⚽</div>`
      : `<div class="avatar user">👤</div>`;

    const savedBadge = extra.prediction_saved
      ? `<div class="saved-badge">✓ prediction saved</div>`
      : '';

    wrap.innerHTML = `
      ${avatar}
      <div class="message-content">
        <div class="message-text">${formatText(text)}</div>
        ${savedBadge}
        <div class="message-time">${now}</div>
      </div>
    `;
  }

  messagesEl.appendChild(wrap);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return wrap;
}

function formatText(text) {
  // Escape HTML to prevent injection
  text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // MATCH line
  text = text.replace(/MATCH:\s*(.+)/g, (_, m) =>
    `<strong style="color:var(--text)">⚽ ${m}</strong>`);

  // PREDICTION line
  text = text.replace(/PREDICTION:\s*(.+)/g, (_, p) => {
    const lower = p.toLowerCase();
    let cls = 'draw';
    if (lower.includes('home') || lower.includes('win')) cls = 'win';
    if (lower.includes('away')) cls = 'loss';
    return `<span class="prediction-badge ${cls}">⚡ PREDICTION: ${p}</span>`;
  });

  // CONFIDENCE line
  text = text.replace(/CONFIDENCE:\s*(High|Medium|Low)/gi, (_, c) => {
    const cls = c.toLowerCase() === 'high' ? 'win' : c.toLowerCase() === 'low' ? 'loss' : 'draw';
    return `<span class="prediction-badge ${cls}">CONFIDENCE: ${c}</span>`;
  });

  // PREDICTED SCORE line
  text = text.replace(/PREDICTED SCORE:\s*(.+)/g, (_, s) =>
    `<span style="color:var(--accent);font-family:'DM Mono',monospace;font-weight:700">PREDICTED SCORE: ${s}</span>`);

  // Horizontal dividers
  text = text.replace(/^---$/gm, "<hr style='border-color:var(--border);margin:8px 0'>");

  // Bold markdown
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  return text;
}

function showTyping() {
  const el = document.createElement('div');
  el.className = 'typing';
  el.id = 'typing-indicator';
  el.innerHTML = `
    <div class="avatar ai">⚽</div>
    <div class="typing-dots">
      <span></span><span></span><span></span>
    </div>
  `;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

/* ── Send Message ─────────────────────────────────────────────── */

async function sendMessage() {
  const message = chatInput.value.trim();
  if (!message || isTyping) return;

  const home = teamA.value.trim();
  const away = teamB.value.trim();

  chatInput.value = '';
  chatInput.style.height = 'auto';
  isTyping = true;
  sendBtn.disabled = true;

  appendMessage('user', message);
  showTyping();

  try {
    const r = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, team_a: home, team_b: away }),
    });

    if (!r.ok) {
      const err = await r.json();
      throw new Error(err.detail || 'Server error');
    }

    const data = await r.json();
    removeTyping();
    appendMessage('assistant', data.reply, { prediction_saved: data.prediction_saved });
    await loadStats();

  } catch (e) {
    removeTyping();
    appendMessage('system-msg', `⚠️ Error: ${e.message}`);
  }

  isTyping = false;
  sendBtn.disabled = false;
  chatInput.focus();
}

/* ── Sidebar Actions ──────────────────────────────────────────── */

async function refreshMatches() {
  btnRefresh.classList.add('loading');
  btnRefresh.textContent = '⏳ Refreshing...';

  try {
    const r = await fetch(`${API}/matches/refresh`, { method: 'POST' });
    const data = await r.json();
    appendMessage('system-msg', `✅ Refreshed: ${data.upcoming_fetched} upcoming fixtures, ${data.results_fetched} recent results.`);
    await loadStats();
  } catch (e) {
    appendMessage('system-msg', `⚠️ Could not refresh: ${e.message}`);
  }

  btnRefresh.classList.remove('loading');
  btnRefresh.innerHTML = '<span class="icon">🔄</span> Refresh Fixtures';
}

async function loadSummary() {
  isTyping = true;
  sendBtn.disabled = true;
  appendMessage('user', 'Give me a summary of the current data.');
  showTyping();

  try {
    const r = await fetch(`${API}/chat/summary`);
    const data = await r.json();
    removeTyping();
    appendMessage('assistant', data.summary);
  } catch (e) {
    removeTyping();
    appendMessage('system-msg', `⚠️ ${e.message}`);
  }

  isTyping = false;
  sendBtn.disabled = false;
}

function askAbout(topic) {
  chatInput.value = `Tell me about ${topic} — upcoming fixtures and latest results.`;
  chatInput.focus();
}

/* ── Helpers ──────────────────────────────────────────────────── */

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

function showToast(msg, duration = 3000) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), duration);
}

/* ── Start ────────────────────────────────────────────────────── */
init();