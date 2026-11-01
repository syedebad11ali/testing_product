import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

/* G3b2a: account-only views are gated in nav() and routeFromHash(). GET /auth/me is a stubbed fetch with the server's real shape. */
const { document } = installDom();
let meCalls = 0, release = null, history_ = [];
function stubMe(user, { hold = false, fail = false } = {}) {
  globalThis.fetch = (url) => {
    meCalls += 1;
    assert.equal(url, '/api/v1/auth/me');
    if (fail) return Promise.reject(new TypeError('offline'));
    const reply = { ok: true, status: 200, text: async () => JSON.stringify({ user }) };
    return hold ? new Promise((resolve) => { release = () => resolve(reply); }) : Promise.resolve(reply);
  };
}
globalThis.history = { replaceState(_s, _t, url) { history_.push(url); globalThis.window.location.hash = ''; }, pushState() {} };
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };   // a browser's window.location IS globalThis.location
let dialogs = [];
document.activeElement = null;
document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
const origCreate = document.createElement;
document.createElement = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); }; return e; };

const { nav, routeFromHash } = await import('../../frontend/js/app/router.js');
const { state } = await import('../../frontend/js/state/store.js');
const { resetSessionUser, isSessionLoaded, isGuestSession, GUEST_BLOCKED_VIEWS } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');

const BLOCKED = ['verify', 'report', 'verlist', 'savedlist', 'reportslist', 'ownerverify', 'verify-document'];
const ROW = { id: 'u1', name: 'Sara', must_change_password: false };
const reset = (user, opts) => {
  resetSessionUser(); meCalls = 0; release = null; history_ = [];
  for (const d of [...dialogs]) d.remove();
  dialogs = []; state.view = 'home'; state.propId = null; window.location.hash = '';
  stubMe(user, opts);
  // closes any dialog the previous test left open (the module keeps one active dialog)
  const a = showLoginRequired(); a.close(); dialogs = [];
};
const dialogHref = () => { const box = dialogs[0] && dialogs[0].children[0]; const actions = box && box.children.find((c) => c.className === 'login-prompt-actions'); return actions && actions.children[0].href; };

test('the seven blocked views are exactly the ones the router gates', () => {
  assert.deepEqual([...GUEST_BLOCKED_VIEWS].sort(), [...BLOCKED].sort());
});

test('guest: nav() to each account-only view shows the dialog and stays put', async () => {
  for (const view of BLOCKED) {
    reset({ ...ROW, role: 'guest' });
    assert.equal(await nav(view, 'p1'), false, view);
    assert.equal(state.view, 'home', view);
    assert.equal(dialogs.length, 1, view);
    assert.equal(isGuestSession(), true, `${view}: guest session kept`);
  }
});

test('guest: direct hash navigation to account-only views is refused with the dialog', async () => {
  for (const [hash, view] of [['#owner-verification', 'ownerverify'], ['#verify-document', 'verify-document']]) {
    reset({ ...ROW, role: 'guest' });
    window.location.hash = hash;
    assert.equal(await routeFromHash(hash), false, hash);
    assert.notEqual(state.view, view, hash);
    assert.equal(dialogs.length, 1, hash);
    assert.equal(dialogHref(), `/login?next=${encodeURIComponent('/' + hash)}`, `${hash} return path preserved`);
    assert.deepEqual(history_, ['/'], `${hash}: refused hash is cleared`);
  }
});

test('guest: nav to a hash-backed view keeps that destination as the return path', async () => {
  reset({ ...ROW, role: 'guest' });
  await nav('ownerverify');
  assert.equal(dialogHref(), `/login?next=${encodeURIComponent('/#owner-verification')}`);
});

test('guest: nav to a view without a hash returns to the current page', async () => {
  reset({ ...ROW, role: 'guest' });
  window.location.pathname = '/listings'; window.location.search = '?q=house';
  await nav('savedlist');
  assert.equal(dialogHref(), `/login?next=${encodeURIComponent('/listings?q=house')}`);
  window.location.pathname = '/'; window.location.search = '';
});

test('registered user and admin keep every account-only view (nav and hash)', async () => {
  for (const role of ['user', 'admin']) {
    for (const view of BLOCKED) {
      reset({ ...ROW, role });
      assert.equal(await nav(view, 'p1'), true, `${role} ${view}`);
      assert.equal(state.view, view);
      assert.equal(dialogs.length, 0);
    }
    reset({ ...ROW, role });
    assert.equal(await routeFromHash('#owner-verification'), true);
    assert.equal(state.view, 'ownerverify');
    assert.equal(await routeFromHash('#verify-document'), true);
    assert.equal(state.view, 'verify-document');
    assert.equal(dialogs.length, 0);
  }
});

test('guest browsing is unchanged: home, detail, listing (no dialog, no session lookup needed)', async () => {
  reset({ ...ROW, role: 'guest' });
  assert.equal(await nav('home'), true); assert.equal(state.view, 'home');
  assert.equal(await nav('detail', 'p3'), true); assert.equal(state.view, 'detail'); assert.equal(state.propId, 'p3');
  assert.equal(await routeFromHash('#/plot/DEMO-KPT-1648'), true);
  assert.equal(state.view, 'listing'); assert.equal(state.propId, 'DEMO-KPT-1648');
  assert.equal(dialogs.length, 0);
  assert.equal(meCalls, 0, 'open views never wait for the session');
});

test('open views switch synchronously (before any await)', () => {
  reset({ ...ROW, role: 'guest' });
  nav('detail', 'p9'); assert.equal(state.view, 'detail');
  routeFromHash('#/house/ABC-123'); assert.equal(state.view, 'listing');
});

test('signed-out visitor is treated like a guest: dialog, no navigation', async () => {
  reset(null);
  assert.equal(await nav('verlist'), false);
  assert.equal(await routeFromHash('#verify-document'), false);
  assert.equal(state.view, 'home');
  assert.equal(dialogs.length, 1);
});

test('unreachable session API is unknown, never a registered account', async () => {
  reset(null, { fail: true });
  assert.equal(await nav('report', 'p1'), false);
  assert.equal(state.view, 'home');
  assert.equal(dialogs.length, 1);
});

test('session not loaded yet: the decision waits for the one /auth/me answer', async () => {
  reset({ ...ROW, role: 'user' }, { hold: true });
  assert.equal(isSessionLoaded(), false);
  let done = false;
  const p = nav('savedlist').then((r) => { done = true; return r; });
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(done, false, 'no decision while unresolved');
  assert.equal(state.view, 'home');
  assert.equal(dialogs.length, 0);
  release();
  assert.equal(await p, true);
  assert.equal(state.view, 'savedlist');
  assert.equal(meCalls, 1);
});

test('session not loaded yet and the answer is guest: dialog only after the answer', async () => {
  reset({ ...ROW, role: 'guest' }, { hold: true });
  const p = nav('verify', 'p1');
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(dialogs.length, 0);
  release();
  assert.equal(await p, false);
  assert.equal(dialogs.length, 1);
});

test('invalid or unknown hash routes change nothing and open nothing', async () => {
  reset({ ...ROW, role: 'guest' });
  for (const h of ['', '#', '#nope', '#owner-verification/', '#/plot/x', '#/admin', '#VERIFY-DOCUMENT', '#/plot/ab%0a', '#//evil.com', undefined]) {
    assert.equal(await routeFromHash(h === undefined ? '#unknown-route' : h), false, String(h));
  }
  assert.equal(state.view, 'home');
  assert.equal(dialogs.length, 0);
  assert.equal(meCalls, 0);
});

test('repeated attempts never stack dialogs and never loop', async () => {
  reset({ ...ROW, role: 'guest' });
  for (let i = 0; i < 4; i++) { await nav('verlist'); await routeFromHash('#verify-document'); await nav('report', 'p1'); }
  assert.equal(dialogs.length, 1, 'one dialog only');
  assert.equal(meCalls, 1, 'one /auth/me for the whole page');
  assert.equal(state.view, 'home');
  assert.equal(isGuestSession(), true);
});

test('a slow older navigation cannot override a newer one', async () => {
  reset({ ...ROW, role: 'user' }, { hold: true });
  const slow = nav('savedlist');
  const fast = nav('detail', 'p2');     // open view: applied immediately and supersedes the pending check
  assert.equal(state.view, 'detail');
  release();
  assert.equal(await slow, false);
  assert.equal(await fast, true);
  assert.equal(state.view, 'detail');
});

test('refused calls never delete or invalidate the guest session (no network call besides /auth/me)', async () => {
  reset({ ...ROW, role: 'guest' });
  const urls = [];
  const inner = globalThis.fetch;
  globalThis.fetch = (u, ...a) => { urls.push(u); return inner(u, ...a); };
  for (const v of BLOCKED) await nav(v);
  assert.deepEqual([...new Set(urls)], ['/api/v1/auth/me']);
  assert.equal(isGuestSession(), true);
});
