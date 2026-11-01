import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

/* G4a2: authentication errors from the three chat calls (/chat, /chat/session, /chat/feedback) while a registered user is using the
 * main Property Assistant. Response shapes are the backend's real ones: {"error": "<message>", "code": "<code>", "request_id": ...}
 * (backend/errors.py) with the statuses/codes from backend/security/guards.py. fetch is a stub that records every request. */
const { document } = installDom();
const BACKEND_TEXT = 'RAW-BACKEND-AUTH-TEXT';
const GREETING = 'Assalam o Alaikum! I can estimate property prices, compare areas and search our property records. How can I help?';
let requests = [], navigations = [], dialogs = [], routes = {}, held = {};
const registry = new Map();   // selector -> element, for document/body querySelector
const mk = (tag = 'div') => {
  const e = { tagName: tag, id: '', textContent: '', innerHTML: '', className: '', dataset: {}, style: {}, children: [], value: '', disabled: false, handlers: {}, isConnected: true, attrs: {},
    classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle() {}, contains(c) { return this._s.has(c); } },
    setAttribute(k, v) { this.attrs[k] = v; this[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener(t, f) { this.handlers[t] = f; }, removeEventListener() {},
    remove() { this.isConnected = false; dialogs = dialogs.filter((d) => d !== this); },
    querySelector(sel) { return registry.get(sel) || (registry.set(sel, mk()), registry.get(sel)); },
    querySelectorAll(sel) { return this.children.filter((c) => c.tagName === sel); },
    scrollIntoView() {}, focus() {}, scrollTop: 0, scrollHeight: 0 };
  return e;
};
const byId = new Map();
document.getElementById = (id) => { if (!byId.has(id)) byId.set(id, mk()); return byId.get(id); };
document.createElement = mk;
document.querySelector = (sel) => registry.get(sel) || (registry.set(sel, mk()), registry.get(sel));
document.querySelectorAll = () => [];
document.activeElement = null;
document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '', assign(url) { navigations.push(url); } };

function reply(status, body) { return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(body) }; }
const CHAT_OK = { reply: 'Hello from the assistant', source: 'x', from_data: true, specialist: 'Property Assistant', chips: [], cards: [], actions: [], message_id: 'm1' };
globalThis.fetch = (url) => {
  const u = String(url); requests.push(u);
  if (u === '/api/v1/auth/me') return Promise.resolve(reply(200, { user: { id: 'u1', name: 'Sara', role: routes.role || 'user' } }));
  const key = u.endsWith('/chat/session') ? 'session' : u.endsWith('/chat/feedback') ? 'feedback' : 'chat';
  const r = routes[key];
  if (r instanceof Error) return Promise.reject(r);
  const out = reply(r.status, r.body);
  return held[key] ? new Promise((resolve) => { held[key] = () => resolve(out); }) : Promise.resolve(out);
};

const { openChat } = await import('../../frontend/js/features/chat.js');
const { chatState, chatRuntime } = await import('../../frontend/js/state/store.js');
const { resetSessionUser } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');

const err = (status, code, error = BACKEND_TEXT) => ({ status, body: { error, code, request_id: 'r1' } });
const AUTH = { 'login: 401 auth_required': err(401, 'auth_required'), 'login: 403 guest_not_allowed': err(403, 'guest_not_allowed') };
const PASSWORD = err(403, 'password_change_required');
const ok = { session: { status: 200, body: { continuity: false } }, feedback: { status: 200, body: { ok: true } }, chat: { status: 200, body: CHAT_OK } };

async function setup(over = {}) {
  { const a = showLoginRequired(); a.close(); }
  dialogs = []; requests = []; navigations = []; held = {}; routes = { ...ok, ...over };
  registry.clear(); byId.clear();
  chatState.messages = []; chatState.continuity = false; chatRuntime.busy = false; chatRuntime.initialized = false; chatRuntime.restored = false;
  resetSessionUser();
  await openChat();
  await new Promise((r) => setTimeout(r, 0));   // let restoreChatSession settle
}
const form = () => registry.get('.assistant-compose'), input = () => registry.get('.assistant-input');
const thread = () => registry.get('.assistant-thread');
async function send(text = 'hi') { input().value = text; form().handlers.submit({ preventDefault() {} }); await new Promise((r) => setTimeout(r, 0)); await new Promise((r) => setTimeout(r, 0)); }
const rowsOf = (role) => thread().children.filter((c) => c.className === `chat-message ${role}`);
const chatCalls = () => requests.filter((u) => u.endsWith('/chat'));
const sessionCalls = () => requests.filter((u) => u.endsWith('/chat/session'));
const dialogText = () => dialogs.map((d) => JSON.stringify(d, (k, v) => (k === 'handlers' || k === 'classList' ? undefined : v))).join('');
const feedbackButtons = () => { const row = rowsOf('assistant').pop(); const fb = row.children.find((c) => c.className === 'chat-feedback'); return fb ? fb.children : []; };
const settle = () => new Promise((r) => setTimeout(r, 0));

for (const [label, response] of Object.entries(AUTH)) {
  test(`chat submission, ${label}: dialog, no false reply, no retry, no raw text`, async () => {
    await setup({ chat: response });
    await send('hello');
    assert.equal(dialogs.length, 1, 'shared login dialog shown');
    assert.equal(rowsOf('error').length, 0, 'no error bubble');
    assert.deepEqual(rowsOf('assistant').map((r) => r.children[0].textContent), [GREETING], 'only the opening greeting: no assistant reply inserted');
    assert.deepEqual(chatState.messages, [{ role: 'user', text: 'hello' }], 'history kept, nothing invented');
    assert.equal(chatCalls().length, 1, 'no automatic retry');
    assert.deepEqual(navigations, []);
    assert.ok(!dialogText().includes(BACKEND_TEXT) && !JSON.stringify(thread().children).includes(BACKEND_TEXT), 'raw backend text never shown');
    assert.equal(chatRuntime.busy, false, 'loading state released');
    assert.ok(!thread().children.some((c) => c.className.includes('chat-typing') && c.isConnected), 'typing indicator removed');
  });

  test(`session retrieval, ${label}: dialog, transcript untouched, one request`, async () => {
    await setup({ session: response });
    assert.equal(dialogs.length, 1);
    assert.equal(sessionCalls().length, 1);
    assert.deepEqual(chatState.messages, []);
    assert.notEqual(chatState.continuity, true);
    assert.deepEqual(navigations, []);
    assert.ok(!dialogText().includes(BACKEND_TEXT));
  });

  test(`feedback, ${label}: dialog, buttons usable again, no retry`, async () => {
    await setup();
    await send('hello');
    assert.equal(dialogs.length, 0);
    routes.feedback = response;
    const [up] = feedbackButtons();
    up.handlers.click();
    await settle(); await settle();
    assert.equal(dialogs.length, 1);
    assert.equal(requests.filter((u) => u.endsWith('/chat/feedback')).length, 1);
    assert.equal(up.disabled, false);
    assert.equal(up['aria-pressed'], 'false');
    assert.equal(chatState.messages.length, 2, 'conversation kept');
    assert.ok(!dialogText().includes(BACKEND_TEXT));
  });
}

test('password_change_required goes to the existing password-change page on all three operations, never the login dialog', async () => {
  assert.equal((await import('../../frontend/js/features/chat.js')).PASSWORD_CHANGE_URL, '/login?change=1');
  await setup({ session: PASSWORD });
  assert.deepEqual(navigations, ['/login?change=1'], 'session retrieval'); assert.equal(dialogs.length, 0);
  await setup({ chat: PASSWORD });
  await send('hello');
  assert.deepEqual(navigations, ['/login?change=1'], 'message submission'); assert.equal(dialogs.length, 0);
  assert.equal(rowsOf('error').length, 0); assert.deepEqual(chatState.messages, [{ role: 'user', text: 'hello' }]);
  await setup();
  await send('hello');
  routes.feedback = PASSWORD;
  feedbackButtons()[0].handlers.click(); await settle(); await settle();
  assert.deepEqual(navigations, ['/login?change=1'], 'feedback'); assert.equal(dialogs.length, 0);
});

test('several rejected calls at once give one password-change navigation and one dialog', async () => {
  await setup();
  await send('hello');
  routes.feedback = PASSWORD; routes.chat = PASSWORD;
  feedbackButtons()[0].handlers.click(); feedbackButtons()[1].handlers.click();
  await send('again'); await settle();
  assert.deepEqual(navigations, ['/login?change=1']);
  await setup({ chat: err(401, 'auth_required'), session: err(403, 'guest_not_allowed') });
  await send('a'); await send('b');
  assert.equal(dialogs.length, 1, 'duplicate dialogs prevented');
});

test('403 forbidden and other unrelated errors keep their existing handling (no login dialog, no navigation)', async () => {
  for (const [status, code, msg] of [[403, 'forbidden', 'Not allowed here.'], [403, 'csrf_failed', 'CSRF'], [401, 'something_else', 'Other 401'], [429, 'rate_limited', 'Too many messages, slow down.'], [500, 'internal_error', 'The assistant could not answer right now.'], [503, 'ai_unavailable', 'Provider down']]) {
    await setup({ chat: err(status, code, msg) });
    await send('hello');
    assert.equal(dialogs.length, 0, `${status} ${code}`);
    assert.deepEqual(navigations, []);
    assert.equal(rowsOf('error').length, 1, `${status} ${code}: existing error bubble`);
    assert.equal(rowsOf('error')[0].children[0].textContent, msg, 'existing message text');
    assert.equal(chatRuntime.busy, false);
  }
  await setup({ chat: new TypeError('offline') });
  await send('hello');
  assert.equal(dialogs.length, 0);
  assert.equal(rowsOf('error')[0].children[0].textContent, 'Could not reach Property Assistance. Check that the chatbot server is running and try again.');
  await setup({ session: err(403, 'forbidden') });
  assert.equal(dialogs.length, 0, 'session: forbidden stays silent as before'); assert.deepEqual(navigations, []);
  await setup(); await send('x');
  routes.feedback = err(403, 'forbidden');
  feedbackButtons()[0].handlers.click(); await settle(); await settle();
  assert.equal(dialogs.length, 0, 'feedback: forbidden stays silent as before');
});

test('registered user: conversation, loading state, feedback and session restore are unchanged', async () => {
  await setup({ session: { status: 200, body: { continuity: true, history: [{ role: 'user', text: 'earlier' }, { role: 'assistant', text: 'earlier answer' }], welcome: { text: 'Welcome back', chips: ['a'] } } } });
  assert.equal(chatState.continuity, true);
  assert.deepEqual(chatState.messages.map((m) => m.text), ['earlier', 'earlier answer', 'Welcome back']);
  await send('hello');
  assert.equal(dialogs.length, 0); assert.deepEqual(navigations, []);
  assert.equal(chatState.messages.at(-1).text, 'Hello from the assistant');
  assert.equal(chatState.messages.at(-1).extras.messageId, 'm1');
  assert.equal(chatState.messages.at(-1).meta, 'From property data');
  assert.equal(chatRuntime.busy, false);
  const fb = feedbackButtons(); assert.equal(fb.length, 2);
  fb[0].handlers.click(); await settle(); await settle();
  assert.equal(requests.filter((u) => u.endsWith('/chat/feedback')).length, 1);
  assert.equal(fb[0].disabled, true, 'feedback stays recorded'); assert.equal(dialogs.length, 0);
  await setup({ role: 'admin' });
  await send('hello');
  assert.equal(chatState.messages.at(-1).text, 'Hello from the assistant');
});

test('a pending reply cannot change the UI or history after an authentication failure', async () => {
  await setup();
  await send('first');                                         // normal exchange, gives us a message with feedback buttons
  held.chat = true;
  await send('second');                                        // pending
  assert.equal(chatRuntime.busy, true);
  routes.feedback = err(401, 'auth_required');
  feedbackButtons()[0].handlers.click(); await settle(); await settle();
  assert.equal(dialogs.length, 1);
  const before = JSON.stringify(chatState.messages);
  held.chat();                                                 // the stale answer arrives
  await settle(); await settle();
  assert.equal(JSON.stringify(chatState.messages), before, 'no reply added to history');
  assert.equal(rowsOf('assistant').filter((r) => r.children.some((c) => c.textContent === 'Hello from the assistant')).length, 1, 'only the first exchange is on screen');
  assert.equal(chatRuntime.busy, false, 'loading state released'); assert.equal(rowsOf('error').length, 0);
});

test('a pending session restore cannot overwrite the UI after an authentication failure', async () => {
  { const a = showLoginRequired(); a.close(); }
  dialogs = []; requests = []; navigations = []; registry.clear(); byId.clear(); resetSessionUser();
  chatState.messages = []; chatState.continuity = false; chatRuntime.busy = false; chatRuntime.initialized = false; chatRuntime.restored = false;
  routes = { ...ok, chat: err(403, 'guest_not_allowed'), session: { status: 200, body: { continuity: true, history: [{ role: 'user', text: 'stale' }] } } };
  held = { session: true };
  await openChat(); await settle();
  await send('hello');                                         // rejected while the restore is still pending
  assert.equal(dialogs.length, 1);
  held.session(); await settle(); await settle();
  assert.notEqual(chatState.continuity, true, 'stale restore ignored');
  assert.deepEqual(chatState.messages, [{ role: 'user', text: 'hello' }]);
});

test('Start over after an authentication failure keeps the history instead of resetting it', async () => {
  await setup({ session: { status: 200, body: { continuity: true, history: [{ role: 'user', text: 'kept' }, { role: 'assistant', text: 'kept too' }] } } });
  routes.chat = err(401, 'auth_required');
  registry.get('.assistant-reset').handlers.click(); await settle(); await settle();
  assert.equal(dialogs.length, 1);
  assert.deepEqual(chatState.messages.map((m) => m.text), ['kept', 'kept too']);
});
