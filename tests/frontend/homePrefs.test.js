import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { restoreFilters, filtersPatch } from '../../frontend/js/features/homePrefs.js';
import { sanitize } from '../../frontend/js/core/prefs.js';
import { installDom } from './helpers/domStub.js';
import { createAccountServer } from './helpers/fakeAccountServer.js';

const AREAS = ['DHA Phase 6', 'Bahria Town', 'Gulshan-e-Iqbal'];
const TYPES = ['House', 'Apartment', 'Plot'];

test('restoreFilters maps saved codes back to the options the page offers (case-insensitive)', () => {
  assert.deepEqual(restoreFilters({ area: 'dha phase 6', ptype: 'house', sort: 'price_desc' }, AREAS, TYPES),
    { areaFilter: 'DHA Phase 6', typeFilter: 'House', sort: 'high' });
  assert.deepEqual(restoreFilters({ sort: 'price_asc' }, AREAS, TYPES), { sort: 'low' });
});

test('restoreFilters ignores unknown, tampered or malformed values and never returns them', () => {
  const evil = { area: '<img src=x onerror=1>', ptype: 'castle', sort: 'DROP TABLE', theme: 'dark' };
  assert.deepEqual(restoreFilters(evil, AREAS, TYPES), {});
  assert.deepEqual(restoreFilters({ area: 5, ptype: null, sort: ['newest'] }, AREAS, TYPES), {});
  assert.deepEqual(restoreFilters(null, AREAS, TYPES), {});
  assert.deepEqual(restoreFilters({ sort: 'relevance' }, AREAS, TYPES), {});   // valid cookie code the UI has no option for
});

test('filtersPatch produces values the shared sanitiser accepts, and clears with null', () => {
  const patch = filtersPatch({ areaFilter: 'DHA Phase 6', typeFilter: 'House', sort: 'low' });
  assert.deepEqual(sanitize(patch), { area: 'dha phase 6', ptype: 'house', sort: 'price_asc' });
  assert.deepEqual(sanitize(filtersPatch({ areaFilter: null, typeFilter: '', sort: 'large' })), {});   // "Largest" has no cookie code
  for (const area of AREAS) assert.ok('area' in sanitize(filtersPatch({ areaFilter: area, typeFilter: '', sort: 'newest' })), area);
});

test('home setters persist the choice and the free-text search is never stored', () => {
  const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
  const home = fs.readFileSync(path.join(root, 'frontend/js/features/home.js'), 'utf8');
  for (const fn of ['setArea', 'setTypeFilter', 'setSort']) assert.match(home, new RegExp(`function ${fn}\\([^)]*\\)\\{[^}]*saveHomeFilters`));
  assert.doesNotMatch(home.match(/function setSearch[^\n]*/)[0], /saveHomeFilters|writePrefs/);
});

/* G5.3a-c: home filters belong to the ACCOUNT. Registered users and admins load and save area / type / sort through the existing
 * account preferences API; guests, signed-out visitors and unresolved sessions use them in memory only; the shared kpt_prefs cookie never
 * holds them (old values are removed, not migrated). These tests drive the real home.js setters against a cookie jar with Preferences
 * consent GIVEN (so a leak into the cookie would really be stored) and the fake account server (same rules as backend/services/prefs.py). */
const { document: dom } = installDom();
const jar = new Map();
Object.defineProperty(dom, 'cookie', { configurable: true,
  get() { return [...jar].map(([k, v]) => `${k}=${v}`).join('; '); },
  set(line) { const [pair, ...attrs] = line.split('; '); const i = pair.indexOf('='); const [k, v] = [pair.slice(0, i), pair.slice(i + 1)];
    if (attrs.includes('Max-Age=0')) jar.delete(k); else jar.set(k, v); } });
globalThis.location = { protocol: 'https:', hash: '', pathname: '/', search: '' };
globalThis.window.location = globalThis.location;
globalThis.event = { target: { classList: { add() {} } } };      // setArea() marks the clicked chip
let dialogs = 0;
dom.body.appendChild = (node) => { dialogs += 1; return node; };  // any login dialog would be appended here

const cookies = await import('../../frontend/js/core/cookies.js');
const { state } = await import('../../frontend/js/state/store.js');
const home = await import('../../frontend/js/features/home.js');
const { AREAS: PAGE_AREAS, PROPERTIES } = await import('../../frontend/js/data/properties.js');
const { loadSessionUser, resetSessionUser, isAccountSession } = await import('../../frontend/js/services/sessionUser.js');
const { saveHomeFilters, loadHomeFilters, clearHomeFilters, homeFiltersStatus, homeFiltersSettled } = await import('../../frontend/js/features/homePrefs.js');
const { syncPrefsAfterLogin } = await import('../../frontend/js/services/accountApi.js');

const server = createAccountServer();
const AREA = PAGE_AREAS[0], AREA2 = PAGE_AREAS[1], TYPE = PROPERTIES[0].type;
const A = { id: 'a1', name: 'Aisha Khan', role: 'user' }, B = { id: 'b1', name: 'Bilal Ahmed', role: 'admin' }, GUEST = { id: 'g1', name: 'Guest', role: 'guest' };
const PAGES = [PAGE_AREAS, [...new Set(PROPERTIES.map((p) => p.type))]];
const DEFAULTS = { areaFilter: null, typeFilter: '', sort: 'newest' };
const view = () => ({ areaFilter: state.areaFilter, typeFilter: state.typeFilter, sort: state.sort });
const LEGACY = { area: AREA2.toLowerCase(), ptype: TYPE.toLowerCase(), sort: 'price_asc' };   // what an earlier version left in the shared cookie

let holds = [], failMe = false;
const holdResponse = (method) => { let release; const gate = new Promise((r) => { release = r; }); holds.push({ method, gate }); return release; };   // server answers at once; the browser gets it later
globalThis.fetch = async (url, options = {}) => {
  if (failMe && String(url).endsWith('/auth/me')) throw new TypeError('offline');
  const response = await server.fetch(url, options);
  const i = holds.findIndex((h) => String(url) === '/api/v1/auth/prefs' && h.method === (options.method || 'GET'));
  if (i >= 0) { const [h] = holds.splice(i, 1); await h.gate; }
  return response;
};
async function setup(user, { resolve = true, unreachable = false, cookie = {} } = {}) {
  clearHomeFilters();                                              // resets the module's queue/loads left by the previous test
  holds = []; failMe = unreachable; dialogs = 0;
  jar.clear(); cookies._resetForTests(); resetSessionUser(); server.prefs.clear(); server.requests.length = 0; server.user = user; server.failNext = null;
  Object.assign(state, DEFAULTS, { search: '' });
  cookies.writeConsent({ preferences: true });
  cookies.writePrefs({ theme: 'dark', lang: 'ur', ...cookie }); cookies._resetForTests();   // the cookie only: this visit's memory starts empty
  return resolve ? loadSessionUser() : null;
}
const storedCookie = () => (jar.has('kpt_prefs') ? JSON.parse(decodeURIComponent(jar.get('kpt_prefs'))) : {});
const onServer = (user) => server.prefs.get(user.id) || {};
const prefsCalls = () => server.requests.filter((r) => r.path === '/api/v1/auth/prefs');
const puts = () => prefsCalls().filter((r) => r.method === 'PUT');
const wait = () => new Promise((r) => setImmediate(r));
const useFilters = () => { home.setArea(AREA); home.setTypeFilter(TYPE); home.setSort('high'); home.setSearch('marla'); };
const CODES = { area: AREA.toLowerCase(), ptype: TYPE.toLowerCase(), sort: 'price_desc' };
const noFilters = (prefs) => FILTER_KEYS.every((k) => !(k in prefs));
const FILTER_KEYS = ['area', 'ptype', 'sort'];

function assertFiltersWorkButAreNotStored(label) {
  assert.deepEqual(view(), { areaFilter: AREA, typeFilter: TYPE, sort: 'high' }, `${label}: area, type and sort change`);
  assert.equal(state.search, 'marla', `${label}: search changes`);
  assert.match(dom.getElementById('listTitle').textContent, new RegExp(AREA), `${label}: the list is re-rendered with the filter`);
  assert.ok(noFilters(storedCookie()), `${label}: nothing in kpt_prefs`);
  assert.ok(noFilters(cookies.readPrefs()), `${label}: nothing kept in memory prefs either`);
  assert.deepEqual([storedCookie().theme, storedCookie().lang], ['dark', 'ur'], `${label}: theme and language untouched`);
  assert.equal(prefsCalls().length, 0, `${label}: the account preferences API is not called`);
  assert.equal(dialogs, 0, `${label}: no login dialog`);
}

test('guest: area, type, sort and search work in memory, nothing is stored in the cookie or sent to the API', async () => {
  await setup(GUEST); assert.equal(isAccountSession(), false);
  useFilters(); await homeFiltersSettled();
  assertFiltersWorkButAreNotStored('guest');
  assert.equal(homeFiltersStatus(), 'idle');
});

test('signed-out visitor: filters work in memory, nothing is stored or sent', async () => {
  await setup(null); assert.equal(isAccountSession(), false);
  useFilters(); await homeFiltersSettled();
  assertFiltersWorkButAreNotStored('signed out');
});

test('unresolved session (not loaded yet, or /auth/me unreachable) cannot persist, and does not block filtering', async () => {
  await setup(A, { resolve: false });
  assert.equal(isAccountSession(), false);
  useFilters(); await homeFiltersSettled();
  assertFiltersWorkButAreNotStored('not loaded');
  await setup(A, { unreachable: true }); assert.equal(isAccountSession(), false);
  useFilters(); await homeFiltersSettled();
  assertFiltersWorkButAreNotStored('unreachable');
});

test('registered user and admin: area, type and sort are saved on THEIR account through the API, never in the cookie; search is not sent', async () => {
  for (const user of [A, B]) {
    await setup(user); assert.equal(isAccountSession(), true);
    useFilters(); await homeFiltersSettled();
    assert.deepEqual(onServer(user), CODES, `${user.role}: stored on the account`);
    assert.equal(homeFiltersStatus(), 'saved');
    assert.ok(noFilters(storedCookie()), 'not in the shared cookie'); assert.ok(noFilters(cookies.readPrefs()));
    assert.deepEqual([storedCookie().theme, storedCookie().lang], ['dark', 'ur'], 'theme and language cookie untouched');
    assert.equal(state.search, 'marla'); assert.equal(JSON.stringify(server.requests).includes('marla'), false, 'the search text is never sent');
    assert.ok(puts().length >= 1 && puts().every((r) => !('user_id' in r.body) && !('id' in r.body) && !('user_id' in r.body.prefs)), 'no user id in any request');
    assert.equal(dialogs, 0);
  }
});

test('saveHomeFilters reports whether a save was queued (false for a guest, true for an account)', async () => {
  await setup(GUEST); assert.equal(saveHomeFilters({ areaFilter: AREA, typeFilter: '', sort: 'low' }), false);
  await setup(A); assert.equal(saveHomeFilters({ areaFilter: AREA, typeFilter: '', sort: 'low' }), true); await homeFiltersSettled();
  assert.equal(onServer(A).sort, 'price_asc');
});

test('guest, signed-out and unreachable visitors cannot load filters: not from the account, not from an old cookie; old cookie filters are removed, theme and language stay', async () => {
  server.prefs.set('someone-else', { ...CODES });
  for (const [label, user, opts] of [['guest', GUEST, {}], ['signed out', null, {}], ['unreachable', A, { unreachable: true }]]) {
    await setup(user, { ...opts, cookie: LEGACY });
    server.prefs.set(A.id, { ...CODES }); server.requests.length = 0;
    assert.equal(await loadHomeFilters(state, ...PAGES), false, label);
    assert.deepEqual(view(), DEFAULTS, `${label}: page keeps its defaults`);
    assert.equal(prefsCalls().length, 0, `${label}: the preferences API is not read`);
    assert.ok(noFilters(storedCookie()), `${label}: old filters removed from the shared cookie`);
    assert.deepEqual([cookies.readPrefs().theme, cookies.readPrefs().lang], ['dark', 'ur'], `${label}: theme and language still available`);
  }
});

test('an unresolved session is not authenticated: nothing is loaded while GET /auth/me is pending, and a guest answer loads nothing', async () => {
  await setup(GUEST, { resolve: false, cookie: LEGACY });
  let release; const gate = new Promise((r) => { release = r; });
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => { if (String(url).endsWith('/auth/me')) await gate; return realFetch(url, options); };
  try {
    let settled = false; const pending = loadHomeFilters(state, ...PAGES).then((v) => { settled = true; return v; });
    await wait();
    assert.equal(settled, false, 'still waiting for the session'); assert.deepEqual(view(), DEFAULTS); assert.equal(prefsCalls().length, 0);
    release(); assert.equal(await pending, false); assert.deepEqual(view(), DEFAULTS); assert.equal(prefsCalls().length, 0);
  } finally { globalThis.fetch = realFetch; }
});

test('registered user and admin load their own stored filters from the API (not from the cookie); the cookie keeps theme and language and loses old filters', async () => {
  for (const user of [A, B]) {
    await setup(user, { cookie: LEGACY });
    server.prefs.set(user.id, { ...CODES, theme: 'light', lang: 'en', saved: ['P1'] });
    assert.equal(await loadHomeFilters(state, ...PAGES), true, user.role);
    assert.deepEqual(view(), { areaFilter: AREA, typeFilter: TYPE, sort: 'high' }, `${user.role}: the account's values, not the cookie's`);
    assert.ok(noFilters(storedCookie()), 'old cookie filters removed');
    assert.deepEqual([storedCookie().theme, storedCookie().lang], ['dark', 'ur'], 'cookie theme/language untouched');
    assert.deepEqual(prefsCalls().map((r) => r.method), ['GET'], 'one read, no write');
    assert.deepEqual(onServer(user).saved, ['P1']);
  }
});

test('account A and account B have separate filters and never see each other\'s', async () => {
  await setup(A);
  home.setArea(AREA); home.setTypeFilter(TYPE); home.setSort('high'); await homeFiltersSettled();
  // B uses the same browser
  clearHomeFilters(); resetSessionUser(); server.user = B; Object.assign(state, DEFAULTS); await loadSessionUser();
  assert.equal(await loadHomeFilters(state, ...PAGES), false, 'B has nothing stored: A\'s filters do not appear');
  assert.deepEqual(view(), DEFAULTS);
  home.setArea(AREA2); home.setSort('low'); await homeFiltersSettled();
  assert.deepEqual(onServer(B), { area: AREA2.toLowerCase(), sort: 'price_asc' });
  assert.deepEqual(onServer(A), CODES, 'B\'s changes did not touch A');
  // back to A
  clearHomeFilters(); resetSessionUser(); server.user = A; Object.assign(state, DEFAULTS); await loadSessionUser();
  assert.equal(await loadHomeFilters(state, ...PAGES), true);
  assert.deepEqual(view(), { areaFilter: AREA, typeFilter: TYPE, sort: 'high' }, 'A gets A\'s own filters back');
});

test('favorites and every other preference survive filter updates; clearing a filter really removes it', async () => {
  await setup(A);
  const others = { theme: 'light', lang: 'en', saved: ['P1', 'P2'], recent: ['R1'], compare: ['C1'], dismissed: ['intro'], min_price: 5000000 };
  server.prefs.set(A.id, { ...others, area: AREA2.toLowerCase() });
  home.setArea(AREA); home.setTypeFilter(TYPE); home.setSort('high'); await homeFiltersSettled();
  assert.deepEqual(onServer(A), { ...others, ...CODES });
  home.setArea(null); home.setTypeFilter(''); home.setSort('large'); await homeFiltersSettled();   // "All areas", "All types", a sort with no stored code
  assert.deepEqual(onServer(A), others, 'filters gone, everything else (saved, recent, theme, lang, ...) exactly as it was');
  assert.deepEqual(storedCookie(), { theme: 'dark', lang: 'ur' });
});

test('API failure does not produce falsely persisted filters: the screen keeps the choice, nothing is claimed stored, nothing goes to the cookie, the next change recovers', async () => {
  await setup(A); server.prefs.set(A.id, { sort: 'price_asc' });
  for (const failure of [500, 'network']) {
    server.failNext = failure; home.setSort('high'); await homeFiltersSettled();
    assert.equal(state.sort, 'high', `${failure}: the filter still works on screen`);
    assert.equal(homeFiltersStatus(), 'error', `${failure}: not reported as saved`);
    assert.deepEqual(onServer(A), { sort: 'price_asc' }, `${failure}: the account is unchanged`);
    assert.ok(noFilters(storedCookie()) && noFilters(cookies.readPrefs()), `${failure}: no cookie or memory fallback`);
  }
  home.setSort('low'); await homeFiltersSettled();
  assert.equal(homeFiltersStatus(), 'saved'); assert.deepEqual(onServer(A), { sort: 'price_asc' });
  home.setArea(AREA); await homeFiltersSettled();
  assert.deepEqual(onServer(A), { sort: 'price_asc', area: AREA.toLowerCase() }, 'a later change stores the full current selection');
  // a value the server's sanitiser silently drops is not "saved" either
  saveHomeFilters({ areaFilter: 'Bad<Area>', typeFilter: '', sort: 'newest' }); await homeFiltersSettled();
  assert.equal(homeFiltersStatus(), 'error'); assert.equal(onServer(A).area, AREA.toLowerCase(), 'the account still has its last confirmed area');
});

test('a failed or invalid load restores nothing and falls back to nothing (no cookie)', async () => {
  await setup(A, { cookie: LEGACY }); server.prefs.set(A.id, { ...CODES });
  server.failNext = 500;
  assert.equal(await loadHomeFilters(state, ...PAGES), false); assert.deepEqual(view(), DEFAULTS); assert.ok(noFilters(storedCookie()));
  server.failNext = 'network';
  assert.equal(await loadHomeFilters(state, ...PAGES), false); assert.deepEqual(view(), DEFAULTS);
  home.setSort('low'); await homeFiltersSettled(); assert.equal(onServer(A).sort, 'price_asc', 'saving still works afterwards');
});

test('rapid changes are sent one at a time, the newest selection wins on the server, and an older answer never changes the screen', async () => {
  await setup(A);
  const release = holdResponse('PUT');
  home.setArea(AREA); await wait();                       // first save in flight (its answer is held)
  home.setTypeFilter(TYPE); home.setSort('high'); home.setSort('low');   // queued behind it: only the newest selection is kept
  assert.equal(puts().length, 1, 'one request in flight at a time');
  assert.deepEqual(view(), { areaFilter: AREA, typeFilter: TYPE, sort: 'low' });
  release(); await homeFiltersSettled();
  assert.equal(puts().length, 2, 'the queued selections were coalesced into one request');
  assert.deepEqual(puts()[1].body.prefs, { area: AREA.toLowerCase(), ptype: TYPE.toLowerCase(), sort: 'price_asc' });
  assert.deepEqual(onServer(A), { area: AREA.toLowerCase(), ptype: TYPE.toLowerCase(), sort: 'price_asc' }, 'newest wins');
  assert.deepEqual(view(), { areaFilter: AREA, typeFilter: TYPE, sort: 'low' }, 'answers never overwrote the selection');
  assert.equal(homeFiltersStatus(), 'saved');
});

test('a stale load answer does not overwrite a filter chosen while it was loading', async () => {
  await setup(A); server.prefs.set(A.id, { sort: 'price_desc', area: AREA.toLowerCase() });
  const release = holdResponse('GET');
  const loading = loadHomeFilters(state, ...PAGES); await wait();
  home.setSort('low'); await homeFiltersSettled();                      // chosen during the load (the held answer still says "high")
  release();
  assert.equal(await loading, true);
  assert.deepEqual(view(), { areaFilter: AREA, typeFilter: '', sort: 'low' }, 'sort kept, the untouched area restored');
  assert.equal(onServer(A).sort, 'price_asc');
});

test('a late answer or queued save from another account / after logout is ignored and never reaches the wrong account', async () => {
  // queued save of A is dropped when B has taken over
  await setup(A);
  let release = holdResponse('PUT');
  home.setArea(AREA); await wait(); home.setTypeFilter(TYPE);             // A: one in flight, one queued
  resetSessionUser(); server.user = B; await loadSessionUser();           // the same page is now B's session
  release(); await homeFiltersSettled();
  assert.equal(puts().length, 1, 'A\'s queued change was not sent');
  assert.deepEqual(onServer(B), {}, 'nothing of A reached B');
  assert.deepEqual(onServer(A), { area: AREA.toLowerCase(), sort: 'newest' }, 'only the first save (the full selection at that moment) was sent');
  // a late load answer for A is ignored once B's load has started
  await setup(A); server.prefs.set(A.id, { ...CODES }); server.prefs.set(B.id, { area: AREA2.toLowerCase() });
  release = holdResponse('GET');
  const loadA = loadHomeFilters(state, ...PAGES); await wait();
  resetSessionUser(); server.user = B; await loadSessionUser();
  assert.equal(await loadHomeFilters(state, ...PAGES), true);
  release();
  assert.equal(await loadA, false, 'A\'s answer arrived late');
  assert.deepEqual(view(), { areaFilter: AREA2, typeFilter: '', sort: 'newest' }, 'B\'s own values only');
  // logout: a queued save and a load in flight are both dropped, and the account's stored filters stay on the server
  await setup(A); server.prefs.set(A.id, { sort: 'price_desc' });
  release = holdResponse('PUT'); home.setArea(AREA); await wait(); home.setTypeFilter(TYPE);
  clearHomeFilters(); release(); await homeFiltersSettled();
  assert.equal(puts().length, 1, 'the queued change was dropped'); assert.equal(homeFiltersStatus(), 'idle');
  await setup(A); server.prefs.set(A.id, { ...CODES }); release = holdResponse('GET');
  const late = loadHomeFilters(state, ...PAGES); await wait(); clearHomeFilters(); release();
  assert.equal(await late, false); assert.deepEqual(view(), DEFAULTS);
  assert.deepEqual(onServer(A), CODES, 'logout does not erase the account\'s filters');
});

test('login sync never copies old cookie filters into the account or the account\'s filters into the cookie; theme and language still sync', async () => {
  await setup(A, { cookie: { ...LEGACY, theme: 'dark' } });
  cookies.writePrefs({ ...LEGACY });                                       // make sure memory and cookie both carry them
  server.prefs.set(A.id, { ...CODES, lang: 'en', saved: ['P7'] });
  await syncPrefsAfterLogin();
  const put = puts().at(-1); assert.ok(put, 'the sync still PUTs');
  assert.deepEqual({ area: put.body.prefs.area, ptype: put.body.prefs.ptype, sort: put.body.prefs.sort }, CODES, 'only the account\'s own filters travel');
  assert.deepEqual({ area: onServer(A).area, ptype: onServer(A).ptype, sort: onServer(A).sort }, CODES, 'the cookie\'s filters did not replace them');
  assert.ok(noFilters(storedCookie()), 'the account\'s filters are not written into the shared cookie');
  assert.equal(storedCookie().lang, 'ur', 'language: the device choice still wins the merge, as before'); assert.equal(storedCookie().theme, 'dark');
  assert.equal(onServer(A).lang, 'ur', 'and it is synced to the account as before');
  assert.deepEqual(onServer(A).saved, ['P7']);
});

test('clearHomeFilters removes only area, ptype and sort from the shared cookie and this visit\'s memory', async () => {
  await setup(A, { cookie: { ...LEGACY, recent: ['p1'] } });
  cookies.writePrefs({ ...LEGACY });                                       // in memory too
  assert.equal(clearHomeFilters(), true);
  assert.deepEqual(storedCookie(), { theme: 'dark', lang: 'ur', recent: ['p1'] });
  assert.ok(noFilters(cookies.readPrefs())); assert.deepEqual([cookies.readPrefs().theme, cookies.readPrefs().lang, cookies.readPrefs().recent], ['dark', 'ur', ['p1']]);
  assert.equal(clearHomeFilters(), false, 'second call: nothing left to remove');
});

test('clearHomeFilters strips old filters from a cookie that is not currently readable (no Preferences consent) and never creates a cookie', async () => {
  jar.clear(); cookies._resetForTests();
  assert.equal(clearHomeFilters(), false); assert.equal(jar.has('kpt_prefs'), false, 'no cookie created');
  jar.set('kpt_prefs', encodeURIComponent(JSON.stringify({ ...LEGACY, theme: 'dark', lang: 'ur' })));   // no kpt_consent at all
  assert.equal(cookies.readPrefs().area, undefined, 'unreadable without consent');
  assert.equal(clearHomeFilters(), true);
  assert.deepEqual(storedCookie(), { theme: 'dark', lang: 'ur' });
  jar.set('kpt_prefs', encodeURIComponent(JSON.stringify(LEGACY)));                                     // only filters: the cookie goes away
  clearHomeFilters(); assert.equal(jar.has('kpt_prefs'), false);
});

test('both logout buttons (Log out and guest Exit) clear old cookie filters and leave theme, language and the account\'s stored filters', async () => {
  const { initAuthNav } = await import('../../frontend/js/features/authNav.js');
  const origCreate = dom.createElement, handlers = [];
  dom.createElement = () => { const e = origCreate(); e.addEventListener = (type, fn) => { if (type === 'click') handlers.push(e.className === 'auth-logout' ? fn : null); }; return e; };
  const assigned = []; globalThis.location.assign = (to) => assigned.push(to);
  try {
    for (const [label, user] of [['Log out', A], ['Exit', GUEST]]) {
      await setup(user, { cookie: { ...LEGACY, recent: ['p1'] } }); handlers.length = 0; assigned.length = 0;
      if (user.role !== 'guest') server.prefs.set(user.id, { ...CODES });
      for (const id of ['authLink', 'mobileAuthLink']) { const el = dom.getElementById(id); el.children = []; el.replaceChildren = function () { this.children = []; }; }
      assert.ok(jar.get('kpt_prefs').includes('area'), 'old filters are in the cookie before logout');
      await initAuthNav();
      const click = handlers.find(Boolean); assert.ok(click, `${label} button exists`);
      await click();
      assert.deepEqual(storedCookie(), { theme: 'dark', lang: 'ur', recent: ['p1'] }, label);
      assert.deepEqual(assigned, ['/login'], label);
      if (user.role !== 'guest') assert.deepEqual(onServer(user), CODES, 'the account keeps its filters');
    }
  } finally { dom.createElement = origCreate; delete globalThis.location.assign; }
});
