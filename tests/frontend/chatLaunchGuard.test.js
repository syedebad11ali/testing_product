import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { installDom } from './helpers/domStub.js';

/* G4a1: the main Property Assistant launch buttons are protected. Every button calls openChat(), which awaits the one existing
 * GET /auth/me. Only a registered user or admin opens the panel; guests, signed-out visitors and an unresolved session get the
 * existing login dialog, with no panel, no chat API request and no change to the guest session or the chat history.
 * fetch is a stub that records every URL, so "no request" is checked on the wire, not assumed. */
const { document, byId } = installDom();
let requests = [];
function stubSession(user, { fail = false } = {}) {
  globalThis.fetch = (url) => {
    requests.push(String(url));
    if (String(url) === '/api/v1/auth/me') {
      if (fail) return Promise.reject(new TypeError('offline'));
      return Promise.resolve({ ok: true, status: 200, text: async () => JSON.stringify({ user }), json: async () => ({ user }) });
    }
    return Promise.resolve({ ok: true, status: 200, text: async () => '{}', json: async () => ({}) });   // chat endpoints: must never be reached by blocked users
  };
}
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };
globalThis.history = { replaceState() {}, pushState() {} };
let dialogs = [];
document.activeElement = null;
document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
const origCreate = document.createElement;
document.createElement = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); }; return e; };

// the DOM stub does not parse innerHTML, so give the transcript container the child nodes renderChat() looks up
{ const body = document.getElementById('chatBody'); body.querySelector = () => origCreate(); }

const { openChat, closeChat } = await import('../../frontend/js/features/chat.js');
const { ACTIONS } = await import('../../frontend/js/ui/actions.js');
const { chatState } = await import('../../frontend/js/state/store.js');
const { resetSessionUser, isGuestSession } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');

const ROW = { id: 'u1', name: 'Sara', must_change_password: false };
const panel = () => byId.get('chatPanel') || document.getElementById('chatPanel');
const chatRequests = () => requests.filter((u) => u !== '/api/v1/auth/me');
function reset(user, opts) {
  resetSessionUser(); requests = [];
  closeChat();
  const a = showLoginRequired(); a.close(); dialogs = [];   // the module keeps one active dialog: clear anything a previous test left
  stubSession(user, opts);
}

test('guest cannot open chat: dialog shown, panel closed, no chat request, guest session kept', async () => {
  reset({ ...ROW, role: 'guest' });
  chatState.messages = [{ role: 'user', text: 'kept' }];
  assert.equal(await openChat(), false);
  assert.equal(panel().classList.contains('open'), false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual(chatRequests(), []);
  assert.deepEqual(requests, ['/api/v1/auth/me']);
  assert.equal(isGuestSession(), true, 'guest session untouched');
  assert.deepEqual(chatState.messages, [{ role: 'user', text: 'kept' }], 'chat history untouched');
  chatState.messages = [];
});

test('signed-out visitor cannot open chat', async () => {
  reset(null);
  assert.equal(await openChat(), false);
  assert.equal(panel().classList.contains('open'), false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual(chatRequests(), []);
});

test('unresolved session (API unreachable) is blocked like a signed-out visitor', async () => {
  reset(null, { fail: true });
  assert.equal(await openChat(), false);
  assert.equal(panel().classList.contains('open'), false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual(chatRequests(), []);
});

test('a click while the session is still loading waits for it, then decides', async () => {
  resetSessionUser(); requests = []; closeChat(); { const a = showLoginRequired(); a.close(); dialogs = []; }
  let release;
  globalThis.fetch = (url) => { requests.push(String(url)); return new Promise((resolve) => { release = () => resolve({ ok: true, status: 200, text: async () => JSON.stringify({ user: { ...ROW, role: 'guest' } }) }); }); };
  const pending = openChat();
  await Promise.resolve();
  assert.equal(panel().classList.contains('open'), false, 'not opened while unresolved');
  assert.equal(dialogs.length, 0, 'no verdict before the session answers');
  release();
  assert.equal(await pending, false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual(chatRequests(), []);
});

test('registered user can open chat', async () => {
  reset({ ...ROW, role: 'user' });
  assert.equal(await openChat(), true);
  assert.equal(panel().classList.contains('open'), true);
  assert.equal(dialogs.length, 0);
});

test('admin can open chat', async () => {
  reset({ ...ROW, role: 'admin' });
  assert.equal(await openChat(), true);
  assert.equal(panel().classList.contains('open'), true);
  assert.equal(dialogs.length, 0);
});

test('no request other than GET /auth/me is sent for any blocked visitor, however often they click', async () => {
  for (const user of [{ ...ROW, role: 'guest' }, null]) {
    reset(user);
    await Promise.all([openChat(), openChat(), openChat()]);
    assert.deepEqual(chatRequests(), [], 'no chat/session/feedback request');
    assert.equal(requests.length, 1, 'the session is fetched once and shared');
    assert.equal(panel().classList.contains('open'), false);
  }
});

test('no duplicate dialog: repeated clicks reuse the one open dialog', async () => {
  reset({ ...ROW, role: 'guest' });
  await openChat(); await openChat();
  await Promise.all([openChat(), openChat()]);
  assert.equal(dialogs.length, 1);
});

test('the dialog uses the shared copy and the Property Assistant name', async () => {
  reset({ ...ROW, role: 'guest' });
  await openChat();
  const box = dialogs[0].children[0];
  const texts = box.children.map((c) => c.textContent);
  assert.ok(texts.includes('Login required'));
  assert.ok(texts.includes('Create an account or log in to use this feature.'));
  assert.ok(texts.includes('Feature: Property Assistant'));
});

test('every main launch button reaches the chat only through the guarded openChat()', () => {
  assert.equal(ACTIONS.openChat, openChat);
  const index = fs.readFileSync('frontend/index.html', 'utf8');
  assert.match(index, /id="chatFab" data-onclick="openChat\(\)"/);
  assert.match(index, /data-onclick="openChat\(\);closeDrawer\(\);"[^>]*>[^<]*Learn how verification works/);
  assert.match(fs.readFileSync('frontend/js/features/drawer.js', 'utf8'), /data-onclick="openChat\(\);closeDrawer\(\);"/);
  // nothing else may open the panel: the only place that adds .open to #chatPanel is the guarded openChat() path
  const offenders = [];
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = `${d}/${e.name}`;
    if (e.isDirectory()) return walk(p);
    if (p.endsWith('features/chat.js') || !/\.(js|html)$/.test(p)) return;
    if (/chatPanel/.test(fs.readFileSync(p, 'utf8')) && !p.endsWith('index.html')) offenders.push(p);
  });
  walk('frontend/js');
  assert.deepEqual(offenders, []);
  const chat = fs.readFileSync('frontend/js/features/chat.js', 'utf8');
  assert.equal((chat.match(/openChatPanel\(\)/g) || []).length, 2, 'declared once, called once (inside openChat)');
});
