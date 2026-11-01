import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';
import { createAccountServer } from './helpers/fakeAccountServer.js';

/* G5.1: saving or removing a favorite needs an account. toggleSave() (home heart, detail heart, detail Save Property) awaits the one
 * existing GET /auth/me; only a registered user or admin changes state.saved and storage. Guests, signed-out visitors and an
 * unresolved session get the existing login dialog and nothing else changes. */
const { document } = installDom();
const KEY = 'kpt_favorite_properties';
let requests = [], dialogs = [];
const account = createAccountServer();     // G5.2: an allowed change is stored on the account; blocked ones must never reach it
function stubSession(user, { fail = false } = {}) {
  account.user = user; account.prefs.clear();
  globalThis.fetch = (url, options) => {
    requests.push(String(url));
    if (fail) return Promise.reject(new TypeError('offline'));
    return account.fetch(url, options);
  };
}
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };
document.activeElement = null;
document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
const origCreate = document.createElement;
document.createElement = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); }; return e; };

const { state } = await import('../../frontend/js/state/store.js');
const { toggleSave } = await import('../../frontend/js/features/home.js');
const { resetSessionUser } = await import('../../frontend/js/services/sessionUser.js');
const { clearFavorites } = await import('../../frontend/js/features/favorites.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');

const ROW = { id: 'u1', name: 'Sara' };
let writes;
const realSet = localStorage.setItem.bind(localStorage);
localStorage.setItem = (k, v) => { if (k === KEY) writes += 1; return realSet(k, v); };

function heart(id) {
  const classes = new Set(); const attrs = {};
  return { dataset: { favoriteId: id }, classList: { toggle(n, on) { on ? classes.add(n) : classes.delete(n); }, contains: (n) => classes.has(n) },
    setAttribute(n, v) { attrs[n] = v; }, hasAttribute: () => false, querySelector: () => ({ textContent: '♡' }), attrs, isSaved: () => classes.has('saved') };
}
function reset(user, opts, saved = ['p2']) {
  { const a = showLoginRequired(); a.close(); }
  dialogs = []; requests = []; writes = 0; resetSessionUser(); clearFavorites();
  stubSession(user, opts);
  if (user && user.role !== 'guest') account.prefs.set(user.id, { saved });
  saved.forEach((id) => state.saved.add(id)); realSet(KEY, JSON.stringify(saved));
}
const stored = () => [...((account.prefs.get('u1') || {}).saved || [])].sort();

test('guest attempting to save: dialog, nothing saved, storage not written', async () => {
  reset({ ...ROW, role: 'guest' });
  const h = heart('p1'); document.querySelectorAll = () => [h];
  assert.equal(await toggleSave('p1'), false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual([...state.saved], ['p2']);
  assert.equal(account.requests.filter((r) => r.method === 'PUT').length, 0, 'the account was never written');
  assert.equal(writes, 0, 'no favorites write');
  assert.equal(h.isSaved(), false, 'the control did not change');
  assert.equal(h.attrs['aria-pressed'], undefined);
});

test('signed-out visitor attempting to save: dialog, nothing saved', async () => {
  reset(null);
  assert.equal(await toggleSave('p1'), false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual([...state.saved], ['p2']);
  assert.equal(writes, 0);
});

test('guest attempting to remove: dialog, the favorite stays', async () => {
  reset({ ...ROW, role: 'guest' }, undefined, ['p1', 'p2']);
  assert.equal(await toggleSave('p1'), false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual([...state.saved], ['p1', 'p2']);
  assert.equal(account.requests.filter((r) => r.method === 'PUT').length, 0, 'the account was never written');
  assert.equal(writes, 0);
});

test('unresolved session (API unreachable) is not authorised', async () => {
  reset(null, { fail: true });
  assert.equal(await toggleSave('p1'), false);
  assert.equal(dialogs.length, 1);
  assert.deepEqual([...state.saved], ['p2']);
  assert.equal(writes, 0);
});

test('a tap while the session is still loading waits for it, then decides; state is untouched meanwhile', async () => {
  { const a = showLoginRequired(); a.close(); }
  dialogs = []; writes = 0; resetSessionUser(); clearFavorites(); state.saved.add('p2'); account.requests = [];
  let release;
  globalThis.fetch = () => new Promise((resolve) => { release = () => resolve({ ok: true, status: 200, text: async () => JSON.stringify({ user: { ...ROW, role: 'guest' } }) }); });
  const pending = toggleSave('p1');
  await Promise.resolve();
  assert.deepEqual([...state.saved], ['p2']); assert.equal(dialogs.length, 0);
  release();
  assert.equal(await pending, false);
  assert.equal(dialogs.length, 1); assert.deepEqual([...state.saved], ['p2']); assert.equal(writes, 0);
});

test('repeated attempts reuse one dialog and make one session request', async () => {
  reset({ ...ROW, role: 'guest' });
  await Promise.all([toggleSave('p1'), toggleSave('p3'), toggleSave('p2')]);
  assert.equal(dialogs.length, 1);
  assert.equal(requests.length, 1);
  assert.deepEqual([...state.saved], ['p2']); assert.equal(writes, 0);
});

test('registered user can save and then remove', async () => {
  reset({ ...ROW, id: 'u1', role: 'user' });
  const h = heart('p1'); document.querySelectorAll = () => [h];
  assert.equal(await toggleSave('p1'), true);
  assert.equal(dialogs.length, 0);
  assert.deepEqual([...state.saved].sort(), ['p1', 'p2']); assert.deepEqual(stored(), ['p1', 'p2']);
  assert.equal(h.isSaved(), true); assert.equal(h.attrs['aria-pressed'], 'true');
  assert.equal(await toggleSave('p1'), true);
  assert.deepEqual([...state.saved], ['p2']); assert.deepEqual(stored(), ['p2']);
  assert.equal(h.isSaved(), false); assert.equal(dialogs.length, 0);
});

test('admin can save', async () => {
  reset({ ...ROW, id: 'u1', role: 'admin' });
  assert.equal(await toggleSave('p1'), true);
  assert.deepEqual([...state.saved].sort(), ['p1', 'p2']); assert.deepEqual(stored(), ['p1', 'p2']);
  assert.equal(dialogs.length, 0);
});
