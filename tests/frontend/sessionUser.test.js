import test from 'node:test';
import assert from 'node:assert/strict';

/* GET /auth/me is answered by a stubbed fetch with the server's real shape: {user: {id, name, role, must_change_password}} or {user: null}. */
let calls = 0;
let release = null;
function stubMe(user, { status = 200, hold = false, fail = false } = {}) {
  globalThis.fetch = (url) => {
    calls += 1;
    assert.equal(url, '/api/v1/auth/me');
    if (fail) return Promise.reject(new TypeError('offline'));
    const reply = { ok: status < 400, status, text: async () => JSON.stringify({ user }) };
    if (!hold) return Promise.resolve(reply);
    return new Promise((resolve) => { release = () => resolve(reply); });
  };
}

const m = await import('../../frontend/js/services/sessionUser.js');
const { loadSessionUser, resetSessionUser, isGuestSession, isSessionLoaded, guestBlockedView, GUEST_BLOCKED_VIEWS } = m;
const reset = () => { resetSessionUser(); calls = 0; release = null; };
const ROW = { id: 'u1', name: 'Sara', must_change_password: false };

test('a guest session is detected', async () => {
  reset(); stubMe({ ...ROW, role: 'guest' });
  await loadSessionUser();
  assert.equal(isSessionLoaded(), true);
  assert.equal(isGuestSession(), true);
});

test('a registered user and an admin are not guests', async () => {
  for (const role of ['user', 'admin']) {
    reset(); stubMe({ ...ROW, role });
    const u = await loadSessionUser();
    assert.equal(u.role, role);
    assert.equal(isSessionLoaded(), true, role);
    assert.equal(isGuestSession(), false, role);
  }
});

test('an anonymous (null) session and an unreachable API are not guests, but are "loaded"', async () => {
  reset(); stubMe(null, { status: 200 });
  assert.equal(await loadSessionUser(), null);
  assert.equal(isGuestSession(), false); assert.equal(isSessionLoaded(), true);
  reset(); stubMe(null, { fail: true });
  assert.equal(await loadSessionUser(), null);
  assert.equal(isGuestSession(), false); assert.equal(isSessionLoaded(), true);
  reset(); stubMe({ ...ROW, role: 'guest' }, { status: 500 });   // an error response is not trusted as a session
  assert.equal(await loadSessionUser(), null);
  assert.equal(isGuestSession(), false);
});

test('before the session has loaded nothing is classified: not a guest, and isSessionLoaded() says unknown', async () => {
  reset(); stubMe({ ...ROW, role: 'guest' }, { hold: true });
  const pending = loadSessionUser();
  assert.equal(isSessionLoaded(), false);
  assert.equal(isGuestSession(), false, 'unknown must not look like a guest ...');
  assert.equal(isSessionLoaded() && !isGuestSession(), false, '... nor like a registered user (callers check isSessionLoaded())');
  release(); await pending;
  assert.equal(isSessionLoaded(), true); assert.equal(isGuestSession(), true);
  reset(); assert.equal(isGuestSession(), false); assert.equal(isSessionLoaded(), false);   // before any call at all
});

test('one request only; the answer is shared by every caller; reset starts over', async () => {
  reset(); stubMe({ ...ROW, role: 'guest' });
  const [a, b] = await Promise.all([loadSessionUser(), loadSessionUser()]);
  assert.equal(a, b); await loadSessionUser();
  assert.equal(calls, 1, 'no second /auth/me request');
  resetSessionUser(); assert.equal(isSessionLoaded(), false); assert.equal(isGuestSession(), false);
  stubMe({ ...ROW, role: 'user' }); await loadSessionUser();
  assert.equal(calls, 2); assert.equal(isGuestSession(), false);
});

test('a late answer that arrives after a reset does not overwrite the new state', async () => {
  reset(); stubMe({ ...ROW, role: 'guest' }, { hold: true });
  const old = loadSessionUser(); const staleRelease = release;
  resetSessionUser();
  stubMe({ ...ROW, role: 'user' }); await loadSessionUser();
  assert.equal(isGuestSession(), false);
  staleRelease(); await old;
  assert.equal(isGuestSession(), false, 'the stale guest answer is ignored');
  assert.equal(isSessionLoaded(), true);
});

test('every account-only view is recognized by guestBlockedView()', () => {
  const expected = ['verify', 'report', 'verlist', 'savedlist', 'reportslist', 'ownerverify', 'verify-document'];
  assert.deepEqual([...GUEST_BLOCKED_VIEWS], expected);
  for (const v of expected) assert.equal(guestBlockedView(v), true, v);
  assert.throws(() => { 'use strict'; GUEST_BLOCKED_VIEWS.push('home'); }, TypeError, 'the list is frozen');
});

test('ordinary browse views and bad values are not blocked', () => {
  for (const v of ['home', 'detail', 'listing', '', 'Verify', 'verify ', 'verify-doc', 'constructor', '__proto__', undefined, null, 5, {}, ['verify']]) assert.equal(guestBlockedView(v), false, String(v));
});

test('the list matches the real router: every blocked view exists in VIEWS and the browse views are the only others', async () => {
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  const router = readFileSync(fileURLToPath(new URL('../../frontend/js/app/router.js', import.meta.url)), 'utf8');   // read only
  const body = router.slice(router.indexOf('const VIEWS = {'), router.indexOf('};', router.indexOf('const VIEWS = {')));
  const keys = [...body.matchAll(/^\s*(?:'([a-z-]+)'|([a-z]+)):\s*\(\)/gm)].map((x) => x[1] || x[2]);
  assert.ok(keys.length >= 10, `parsed VIEWS keys: ${keys}`);
  for (const v of GUEST_BLOCKED_VIEWS) assert.ok(keys.includes(v), `router VIEWS has ${v}`);
  assert.deepEqual(keys.filter((k) => !guestBlockedView(k)).sort(), ['detail', 'home', 'listing'], 'unblocked views = the browse views');
});
