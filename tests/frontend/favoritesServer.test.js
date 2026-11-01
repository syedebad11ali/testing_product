import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';
import { createAccountServer } from './helpers/fakeAccountServer.js';

/* G5.2: favorites belong to the signed-in account and live on the server (account preferences). The fake server applies the same rules
 * as the backend (union, `remove`, 30-item limit, session decides the account). The legacy global key is only ever deleted. */
const { document } = installDom();
const LEGACY = 'kpt_favorite_properties';
localStorage.setItem(LEGACY, JSON.stringify(['LEGACY-1', 'LEGACY-2']));   // what an older version left in this browser
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };
document.activeElement = null;
document.removeEventListener = () => {};
let dialogs = [], notices = [];
const origCreate = document.createElement;
const makeEl = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); notices = notices.filter((n) => n !== e); }; return e; };
document.createElement = makeEl;
document.body.appendChild = (node) => { (node.id === 'favNotice' ? notices : dialogs).push(node); return node; };
document.getElementById = (id) => notices.find((n) => n.id === id) || null;

const server = createAccountServer();
globalThis.fetch = (...a) => server.fetch(...a);
const { state, favoritesRuntime } = await import('../../frontend/js/state/store.js');
const { toggleSave } = await import('../../frontend/js/features/home.js');
const { ensureFavoritesLoaded, clearFavorites, MESSAGES, SAVED_LIMIT } = await import('../../frontend/js/features/favorites.js');
const { renderSubList } = await import('../../frontend/js/features/property.js');
const { resetSessionUser } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');
const { syncPrefsAfterLogin } = await import('../../frontend/js/services/accountApi.js');

const A = { id: 'a1', name: 'Aisha Khan', role: 'user' }, B = { id: 'b1', name: 'Bilal Ahmed', role: 'user' };
const ids = () => [...state.saved].sort();
const serverList = (user) => (server.prefs.get(user.id) || {}).saved || [];
function reset(user) {
  { const d = showLoginRequired(); d.close(); }
  dialogs = []; notices = []; server.requests = []; server.failNext = null; server.holdNext = null;
  server.prefs.clear(); clearFavorites(); resetSessionUser(); server.user = user;
}
function heart(id) {
  const classes = new Set(); const attrs = {}; const text = { textContent: '♡' };
  return { dataset: { favoriteId: id }, classList: { toggle(n, on) { on ? classes.add(n) : classes.delete(n); }, contains: (n) => classes.has(n) },
    setAttribute(n, v) { attrs[n] = v; }, hasAttribute: () => false, querySelector: () => text, attrs, text, isSaved: () => classes.has('saved') };
}
const prefsWrites = () => server.requests.filter((r) => r.method === 'PUT');

test('the legacy global key is ignored, deleted and never migrated into an account', async () => {
  assert.deepEqual([...state.saved], [], 'nothing is loaded from browser storage');
  assert.equal(localStorage.getItem(LEGACY), null, 'legacy key removed when the app state loads');
  localStorage.setItem(LEGACY, JSON.stringify(['LEGACY-1']));        // e.g. written back by an old tab
  reset(A);
  assert.equal(await ensureFavoritesLoaded(), true);
  assert.deepEqual([...state.saved], [], 'still not loaded from storage');
  assert.equal(localStorage.getItem(LEGACY), null, 'cleared when favorites reset');
  assert.deepEqual(serverList(A), [], 'not copied into the first account either');
  assert.deepEqual(prefsWrites(), [], 'loading writes nothing');
});

test('loads the account favorites from the server', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P1', 'P2'], theme: 'dark' });
  assert.equal(await ensureFavoritesLoaded(), true);
  assert.deepEqual(ids(), ['P1', 'P2']);
  assert.equal(favoritesRuntime.status, 'ready');
  assert.deepEqual(server.requests.filter((r) => r.path === '/api/v1/auth/prefs').map((r) => r.method), ['GET']);
  await ensureFavoritesLoaded();
  assert.equal(server.requests.filter((r) => r.path === '/api/v1/auth/prefs').length, 1, 'loaded once per account');
});

test('saving goes through the preferences API (only the new id, no user id) and updates the controls after success', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P2'], theme: 'dark', lang: 'ur', recent: ['R1'] });
  const h = heart('P1'); document.querySelectorAll = () => [h];
  assert.equal(await toggleSave('P1'), true);
  assert.deepEqual(prefsWrites().map((r) => r.body), [{ prefs: { saved: ['P1'] } }]);
  assert.ok(!JSON.stringify(prefsWrites()).includes('user'), 'no browser-supplied account');
  assert.deepEqual(ids(), ['P1', 'P2']); assert.deepEqual(serverList(A).sort(), ['P1', 'P2']);
  assert.equal(h.isSaved(), true); assert.equal(h.attrs['aria-pressed'], 'true'); assert.equal(h.text.textContent, '♥');
});

test('removing goes through the API and keeps every unrelated preference field', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P1', 'P2'], theme: 'dark', lang: 'ur', sort: 'newest', area: 'malir', recent: ['R1'], compare: ['C1'] });
  const h = heart('P1'); document.querySelectorAll = () => [h];
  await ensureFavoritesLoaded(); h.classList.toggle('saved', true);
  assert.equal(await toggleSave('P1'), true);
  assert.deepEqual(prefsWrites().map((r) => r.body), [{ prefs: {}, remove: { saved: ['P1'] } }]);
  assert.deepEqual(ids(), ['P2']);
  assert.deepEqual(server.prefs.get(A.id), { theme: 'dark', lang: 'ur', sort: 'newest', area: 'malir', recent: ['R1'], compare: ['C1'], saved: ['P2'] });
  assert.equal(h.isSaved(), false); assert.equal(h.text.textContent, '♡');
});

test('API failure never leaves a property looking saved (save and remove, HTTP error and network error)', async () => {
  for (const failure of [500, 'network', 409]) {
    reset(A); server.prefs.set(A.id, { saved: ['P2'] });
    const h = heart('P1'); document.querySelectorAll = () => [h];
    await ensureFavoritesLoaded();
    server.failNext = failure;
    assert.equal(await toggleSave('P1'), false, `save fails (${failure})`);
    assert.deepEqual(ids(), ['P2']); assert.equal(h.isSaved(), false); assert.equal(h.attrs['aria-pressed'], undefined);
    assert.equal(notices.length, 1, 'error message shown'); assert.equal(notices[0].textContent, MESSAGES.save);
    assert.deepEqual(serverList(A), ['P2']);
    server.failNext = failure;
    assert.equal(await toggleSave('P2'), false, `remove fails (${failure})`);
    assert.deepEqual(ids(), ['P2'], 'still saved: the server did not remove it');
    assert.equal(notices[0].textContent, MESSAGES.remove);
    assert.equal(dialogs.length, 0);
  }
});

test('a failed load is an error, not an empty successful list; the next tap retries', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P2'] });
  server.failNext = 500;
  assert.equal(await ensureFavoritesLoaded(), false);
  assert.equal(favoritesRuntime.status, 'error');
  assert.match(renderSubList('saved'), /could not load your saved properties/);
  assert.doesNotMatch(renderSubList('saved'), /haven.t saved any properties yet/);
  assert.equal(await toggleSave('P1'), true, 'retry loads first, then saves');
  assert.deepEqual(ids(), ['P1', 'P2']); assert.equal(favoritesRuntime.status, 'ready');
  const failed = createAccountServer(); failed.user = A; failed.failNext = 500;
  reset(A); server.failNext = 500;
  assert.equal(await toggleSave('P1'), false, 'cannot save while the list is unknown');
  assert.equal(notices[0].textContent, MESSAGES.load); assert.deepEqual(prefsWrites(), []);
});

test('while an account list is loading nothing is shown; an empty result is only claimed after a successful load', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P1'] });
  assert.match(renderSubList('saved'), /Loading your saved properties/);
  let release; server.holdNext = new Promise((r) => { release = r; });
  const pending = ensureFavoritesLoaded();
  await new Promise((r) => setImmediate(r));
  assert.deepEqual([...state.saved], []); assert.match(renderSubList('saved'), /Loading your saved properties/);
  release(); await pending;
  assert.deepEqual(ids(), ['P1']);
  reset(A);
  assert.equal(await ensureFavoritesLoaded(), true);
  assert.match(renderSubList('saved'), /haven.t saved any properties yet/);
});

test('account switch: A saves P1, logout clears memory, B does not see P1, A sees P1 again', async () => {
  reset(A);
  assert.equal(await toggleSave('P1'), true);
  assert.deepEqual(ids(), ['P1']); assert.deepEqual(serverList(A), ['P1']);
  clearFavorites();                                                   // what the Log out / Exit buttons do
  assert.deepEqual([...state.saved], [], 'in-memory favorites cleared on logout');
  assert.equal(favoritesRuntime.status, 'idle'); assert.equal(favoritesRuntime.userId, null);
  assert.equal(localStorage.getItem(LEGACY), null);
  assert.deepEqual(serverList(A), ['P1'], 'server favorites are not deleted by logout');
  resetSessionUser(); server.user = B;
  assert.equal(await ensureFavoritesLoaded(), true);
  assert.deepEqual([...state.saved], [], 'B does not see A\'s favorite');
  assert.equal(await toggleSave('P5'), true);
  assert.deepEqual(ids(), ['P5']); assert.deepEqual(serverList(B), ['P5']); assert.deepEqual(serverList(A), ['P1']);
  clearFavorites(); resetSessionUser(); server.user = A;
  assert.equal(await ensureFavoritesLoaded(), true);
  assert.deepEqual(ids(), ['P1'], 'A still has its server-side favorite');
});

test('a different account in the same page drops the previous list before loading (no logout hook needed)', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P1'] });
  await ensureFavoritesLoaded(); assert.deepEqual(ids(), ['P1']);
  resetSessionUser(); server.user = B; server.prefs.set(B.id, { saved: ['P7'] });
  let release; server.holdNext = new Promise((r) => { release = r; });
  const pending = ensureFavoritesLoaded();
  await new Promise((r) => setImmediate(r));
  assert.deepEqual([...state.saved], [], 'A\'s list is not shown while B\'s loads');
  release(); await pending;
  assert.deepEqual(ids(), ['P7']);
});

test('a load that finishes after logout is ignored', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P1'] });
  let release; server.holdNext = new Promise((r) => { release = r; });
  const pending = ensureFavoritesLoaded();
  await new Promise((r) => setImmediate(r));
  clearFavorites();
  release(); assert.equal(await pending, false);
  assert.deepEqual([...state.saved], []); assert.equal(favoritesRuntime.status, 'idle');
});

test('guests and signed-out visitors stay blocked and no favorites request is made (G5.1)', async () => {
  for (const user of [{ id: 'g1', name: 'Guest', role: 'guest' }, null]) {
    reset(user);
    assert.equal(await toggleSave('P1'), false);
    assert.equal(dialogs.length, 1);
    assert.deepEqual(server.requests.filter((r) => r.path === '/api/v1/auth/prefs'), []);
    assert.deepEqual([...state.saved], []);
  }
});

test('an expired session while saving shows the login dialog and nothing is shown as saved', async () => {
  reset(A); server.prefs.set(A.id, { saved: ['P2'] });
  await ensureFavoritesLoaded();
  server.failNext = 401;
  assert.equal(await toggleSave('P1'), false);
  assert.equal(dialogs.length, 1); assert.deepEqual([...state.saved], []); assert.equal(notices.length, 0);
});

test('the 30-item limit: the client refuses the 31st without a request; the server refusal (409) is reported and changes nothing', async () => {
  const full = Array.from({ length: SAVED_LIMIT }, (_, i) => `P${i}`);
  reset(A); server.prefs.set(A.id, { saved: full });
  await ensureFavoritesLoaded();
  assert.equal(await toggleSave('EXTRA'), false);
  assert.equal(notices[0].textContent, MESSAGES.limit); assert.deepEqual(prefsWrites(), []);
  assert.equal(await toggleSave('P0'), true, 'removing is still possible');
  assert.equal(state.saved.size, 29);
  // another device filled the list meanwhile: the server says no
  server.prefs.set(A.id, { saved: [...Array.from({ length: 28 }, (_, i) => `P${i + 1}`), 'X1', 'X2'] });
  assert.equal(await toggleSave('EXTRA'), false);
  assert.equal(notices.at(-1).textContent, MESSAGES.limit); assert.equal(state.saved.has('EXTRA'), false);
});

test('rapid taps are sent one after another and end in the right state', async () => {
  reset(A);
  const results = await Promise.all([toggleSave('P1'), toggleSave('P1'), toggleSave('P1')]);
  assert.deepEqual(results, [true, true, true]);
  assert.deepEqual(ids(), ['P1'], 'save, remove, save');
  assert.deepEqual(prefsWrites().map((r) => (r.body.remove ? 'remove' : 'add')), ['add', 'remove', 'add']);
});

test('after login the browser-wide preferences cookie never carries a saved list into an account (or receives one), legacy key deleted', async () => {
  reset(null);
  const jar = new Map();                                              // a minimal cookie jar so the real cookies.js runs with Preferences consent
  Object.defineProperty(document, 'cookie', { configurable: true,
    get: () => [...jar].map(([k, v]) => `${k}=${v}`).join('; '),
    set: (line) => { const [pair, ...attrs] = String(line).split('; '); const i = pair.indexOf('='); const name = pair.slice(0, i), value = pair.slice(i + 1);
      if (attrs.includes('Max-Age=0')) jar.delete(name); else jar.set(name, value); } });
  const { writeConsent, writePrefs, readPrefs, getCookie } = await import('../../frontend/js/core/cookies.js');
  writeConsent({ preferences: true });
  localStorage.setItem(LEGACY, JSON.stringify(['LEGACY-9']));
  writePrefs({ saved: ['FROM-OTHER-ACCOUNT'], theme: 'dark' });       // what an earlier account's data in this browser's cookie could look like
  assert.deepEqual(JSON.parse(getCookie('kpt_prefs')).saved, ['FROM-OTHER-ACCOUNT']);
  server.user = B; server.prefs.set(B.id, { saved: ['P7'], lang: 'ur' });
  await syncPrefsAfterLogin();
  const put = prefsWrites().at(-1);
  assert.ok(put, 'the sync still PUTs');
  assert.ok(!JSON.stringify(put.body).includes('FROM-OTHER-ACCOUNT'), 'the device saved list is not merged into the account');
  assert.equal(put.body.prefs.theme, 'dark', 'other preferences still sync');
  assert.deepEqual(serverList(B), ['P7'], 'the account keeps only its own favorites');
  const cookie = JSON.parse(getCookie('kpt_prefs'));
  assert.equal(cookie.saved, undefined, 'the account list is not written into the shared cookie');
  assert.equal(cookie.lang, 'ur', 'the account\'s other preferences are'); assert.equal(readPrefs().saved, undefined);
  assert.equal(localStorage.getItem(LEGACY), null);
  delete document.cookie;
});
