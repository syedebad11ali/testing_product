/* Admin dashboard: users (search/filter/sort/paginate, disable, role, ban/suspend, reinstate), login activity, reports, audit log.
 * Authorisation is enforced by the server on every call; this page only renders. Built with textContent/createElement
 * (no markup parsing), so stored names, reasons and message text cannot inject markup. */
import { fetchJson, loadCsrf } from '../services/http.js';

const API = '/api/v1/admin';
const $ = (s) => document.querySelector(s);
const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : '—');
const PER = 15;
const pages = { users: 1, events: 1, audit: 1 };

function cell(tr, text, cls) { const td = document.createElement('td'); td.textContent = text; if (cls) td.className = cls; tr.appendChild(td); return td; }
function say(msg) { $('#msg').textContent = msg || ''; }

async function call(path, options) {
  const { ok, data } = await fetchJson(`${API}${path}`, options);
  if (!ok) { say((data && data.error) || 'Request failed.'); if (data && data.code === 'auth_required') location.assign('/login'); return null; }
  say('');
  return data;
}

let totpStatus = 'none';

/** Native <dialog> asking for the authenticator code. `submit(code)` returns {ok, value} or {ok:false, error}; resolves to value, or null if cancelled. */
function askCode(submit) {
  const dlg = $('#stepup'), input = $('#su-code'), err = $('#su-err'), form = $('#su-form');
  input.value = ''; err.textContent = '';
  return new Promise((resolve) => {
    const finish = (value) => { form.removeEventListener('submit', onSubmit); $('#su-cancel').removeEventListener('click', onCancel); dlg.removeEventListener('cancel', onCancel); dlg.close(); resolve(value); };
    const onCancel = (e) => { if (e) e.preventDefault(); finish(null); };
    const onSubmit = async (e) => {
      e.preventDefault();
      const r = await submit(input.value.trim());
      if (r.ok) return finish(r.value);
      err.textContent = r.error || 'That code was not accepted.';
      input.select();
    };
    form.addEventListener('submit', onSubmit); $('#su-cancel').addEventListener('click', onCancel); dlg.addEventListener('cancel', onCancel);
    dlg.showModal(); input.focus();
  });
}

/** One-time step-up proof for an action class (moderation | role_change | csv_export), or null. */
const askProof = (action) => askCode(async (code) => {
  const { ok, data } = await fetchJson(`${API}/totp/stepup`, { method: 'POST', body: { code, action } });
  return ok ? { ok: true, value: data.proof } : { ok: false, error: data && data.error };
});

const actionClass = (path) => (path.endsWith('/role') ? 'role_change' : 'moderation');

async function act(path, body, reload = loadUsers) {
  const password = $('#reauth').value;
  if (!password) { say('Enter your password above to confirm this action.'); return; }
  const payload = { ...body, password };
  if (totpStatus === 'active') {
    const proof = await askProof(actionClass(path));
    if (!proof) { say('Action cancelled: two-factor confirmation is required.'); return; }
    payload.stepup = proof;
  }
  if (await call(path, { method: 'POST', body: payload })) { $('#reason').value = ''; reload(); loadAudit(); }
}

async function downloadCsv(kind) {
  let body = {};
  if (totpStatus === 'active') {
    const proof = await askProof('csv_export');
    if (!proof) { say('Export cancelled: two-factor confirmation is required.'); return; }
    body = { stepup: proof };
  }
  const token = await loadCsrf();
  const r = await fetch(`${API}/export/${kind}.csv`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(token ? { 'X-CSRF-Token': token } : {}) }, body: JSON.stringify(body) });
  if (!r.ok) { let m = 'Export failed.'; try { m = (await r.json()).error || m; } catch (_) { /* not json */ } say(m); return; }
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a'); a.href = url; a.download = `kpt-${kind}.csv`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  say(''); loadAudit();
}

async function loadTotp() {
  const { ok, data } = await fetchJson(`${API}/totp/status`);
  if (!ok) return;
  totpStatus = data.status;
  const text = { none: 'Two-factor is off for your account.', pending: 'Setup started but not confirmed yet.', active: 'Two-factor is on for your account.' }[data.status];
  $('#totp-state').textContent = text + (data.required ? ' Your organisation requires it for sensitive actions.' : '') + (data.configured ? '' : ' The server has no encryption key, so two-factor is unavailable.');
  $('#totp-start').hidden = data.status === 'active' || !data.configured;
  $('#totp-disable').hidden = data.status !== 'active';
  $('#totp-enroll').hidden = data.status !== 'pending' || $('#totp-secret').textContent === '';
}

function wireTotp() {
  $('#totp-start').addEventListener('click', async () => {
    const password = $('#reauth').value;
    if (!password) { say('Enter your password above first.'); return; }
    const data = await call('/totp/enroll/start', { method: 'POST', body: { password } });
    if (!data) return;
    $('#totp-secret').textContent = data.secret; $('#totp-uri').textContent = data.otpauth_uri;
    $('#totp-enroll').hidden = false; $('#totp-code').focus();
  });
  $('#totp-confirm').addEventListener('click', async () => {
    if (await call('/totp/enroll/confirm', { method: 'POST', body: { code: $('#totp-code').value.trim() } })) {
      $('#totp-secret').textContent = ''; $('#totp-uri').textContent = ''; $('#totp-code').value = '';
      say('Two-factor is on.'); loadTotp(); loadAudit();
    }
  });
  $('#totp-disable').addEventListener('click', async () => {
    const password = $('#reauth').value;
    if (!password) { say('Enter your password above first.'); return; }
    const done = await askCode(async (code) => {
      const { ok, data } = await fetchJson(`${API}/totp/disable`, { method: 'POST', body: { password, code } });
      return ok ? { ok: true, value: true } : { ok: false, error: data && data.error };
    });
    if (done) { say('Two-factor is off.'); loadTotp(); loadAudit(); }
  });
}

function reasonOrNag() {
  const reason = $('#reason').value.trim();
  if (reason.length < 3) say('Enter a reason (3 to 300 characters) first.');
  return reason;
}

function actionButton(label, handler) {
  const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.addEventListener('click', handler); return b;
}

function pager(id, key, total, reload) {
  const box = $(id); box.replaceChildren();
  const last = Math.max(1, Math.ceil(total / PER));
  const prev = actionButton('Previous', () => { pages[key] -= 1; reload(); });
  const next = actionButton('Next', () => { pages[key] += 1; reload(); });
  prev.disabled = pages[key] <= 1; next.disabled = pages[key] >= last;
  const label = document.createElement('span'); label.textContent = `Page ${pages[key]} of ${last}`;
  box.append(prev, label, next);
}

export function banSummary(ban) {
  if (!ban) return '';
  const until = ban.expires_at ? `until ${fmt(ban.expires_at)}` : 'permanent';
  return `${ban.kind} (${until}) by ${ban.actor}, ${fmt(ban.created_at)}: ${ban.reason}`;
}

async function loadUsers() {
  const qs = new URLSearchParams({ q: $('#q').value.trim(), status: $('#fStatus').value, role: $('#fRole').value, sort: $('#fSort').value,
    dir: $('#fSort').value === 'name' ? 'asc' : 'desc', page: pages.users, per_page: PER });
  const data = await call(`/users?${qs}`);
  if (!data) return;
  $('#total').textContent = `${data.total} user${data.total === 1 ? '' : 's'}`;
  const body = $('#users tbody'); body.replaceChildren();
  for (const u of data.users) {
    const tr = document.createElement('tr');
    cell(tr, u.name); cell(tr, u.login); cell(tr, u.role); cell(tr, u.status, u.status === 'active' ? 'admin-ok' : 'admin-fail');
    cell(tr, banSummary(u.ban), 'admin-ban'); cell(tr, fmt(u.created_at)); cell(tr, fmt(u.last_login_at));
    const actions = document.createElement('td');
    if (u.status === 'banned') {
      actions.append(actionButton('Reinstate', () => { const reason = reasonOrNag(); if (reason.length >= 3) act(`/users/${u.id}/unban`, { reason }); }));
    } else {
      actions.append(
        actionButton(u.status === 'active' ? 'Disable' : 'Enable', () => act(`/users/${u.id}/status`, { status: u.status === 'active' ? 'disabled' : 'active', reason: $('#reason').value.trim() })),
        actionButton('Ban / Suspend', () => {
          const reason = reasonOrNag(); if (reason.length < 3) return;
          const kind = $('#banKind').value;
          act(`/users/${u.id}/ban`, kind === 'permanent' ? { kind: 'permanent', reason } : { kind: 'temporary', days: Number(kind), reason });
        }));
    }
    actions.append(
      actionButton(u.role === 'admin' ? 'Make user' : 'Make admin', () => act(`/users/${u.id}/role`, { role: u.role === 'admin' ? 'user' : 'admin' })),
      actionButton('Force logout', async () => { if (await call(`/users/${u.id}/logout`, { method: 'POST', body: {} })) { say('Sessions revoked.'); loadAudit(); } }));
    tr.appendChild(actions); body.appendChild(tr);
  }
  pager('#usersPager', 'users', data.total, loadUsers);
}

async function loadEvents() {
  const qs = new URLSearchParams({ q: $('#eq').value.trim(), outcome: $('#eOutcome').value, method: $('#eMethod').value, page: pages.events, per_page: PER });
  const data = await call(`/login-events?${qs}`);
  if (!data) return;
  const body = $('#events tbody'); body.replaceChildren();
  for (const e of data.events) {
    const tr = document.createElement('tr');
    cell(tr, fmt(e.ts)); cell(tr, e.identifier || '—'); cell(tr, e.method);
    cell(tr, e.success ? 'success' : 'failed', e.success ? 'admin-ok' : 'admin-fail'); cell(tr, e.reason || ''); cell(tr, e.ip_hash || '');
    body.appendChild(tr);
  }
  pager('#eventsPager', 'events', data.total, loadEvents);
}

async function loadAudit() {
  const data = await call(`/audit?page=${pages.audit}&per_page=${PER}`);
  if (!data) return;
  const body = $('#audit tbody'); body.replaceChildren();
  for (const a of data.entries) {
    const tr = document.createElement('tr');
    cell(tr, fmt(a.ts)); cell(tr, a.actor || '—'); cell(tr, a.action); cell(tr, a.target || ''); cell(tr, a.detail || '', 'admin-ban');
    body.appendChild(tr);
  }
  pager('#auditPager', 'audit', data.total, loadAudit);
}

async function showThread(id) {
  const data = await call(`/reports/${id}/thread`);
  if (!data) return;
  const box = $('#thread');
  box.textContent = `Buyer: ${data.buyer} · Seller: ${data.seller}\n\n` + data.messages.map((m) => `${m.reported ? '>> REPORTED MESSAGE >> ' : ''}[${new Date(m.ts / 1000).toLocaleString()}] ${m.from}: ${m.body}`).join('\n');
  box.hidden = false; loadAudit();
}

async function loadReports() {
  const data = await call('/reports?status=open');
  if (!data) return;
  const body = $('#reports tbody'); body.replaceChildren();
  for (const r of data.reports) {
    const tr = document.createElement('tr');
    cell(tr, fmt(r.created_at)); cell(tr, r.reporter); cell(tr, r.reason, 'admin-ban');
    const actions = document.createElement('td');
    actions.append(actionButton('Open thread', () => showThread(r.id)),
      actionButton('Resolve', async () => {
        const reason = reasonOrNag(); if (reason.length < 3) return;
        if (await call(`/reports/${r.id}/resolve`, { method: 'POST', body: { reason } })) { $('#thread').hidden = true; loadReports(); loadAudit(); }
      }));
    tr.appendChild(actions); body.appendChild(tr);
  }
}

if (typeof document !== 'undefined' && $('#users')) {
  let timer;
  const debounced = (key, fn) => () => { pages[key] = 1; clearTimeout(timer); timer = setTimeout(fn, 250); };
  $('#q').addEventListener('input', debounced('users', loadUsers));
  for (const id of ['#fStatus', '#fRole', '#fSort']) $(id).addEventListener('change', debounced('users', loadUsers));
  $('#eq').addEventListener('input', debounced('events', loadEvents));
  for (const id of ['#eOutcome', '#eMethod']) $(id).addEventListener('change', debounced('events', loadEvents));
  $('#logout').addEventListener('click', async () => { await fetchJson('/api/v1/auth/logout', { method: 'POST', body: {} }); location.assign('/login'); });
  $('#exportUsers').addEventListener('click', () => downloadCsv('users'));
  $('#exportEvents').addEventListener('click', () => downloadCsv('login-events'));
  wireTotp(); loadTotp();
  loadUsers(); loadEvents(); loadReports(); loadAudit();
}
