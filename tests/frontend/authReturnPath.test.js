/* G3b2b: after a SUCCESSFUL authentication (email/password login, signup, Google) the page returns to a validated `next`.
 * Pure-logic tests plus the real post()/finishAuth()/setupGoogle() driven with a stubbed fetch and a fake form.
 * The Google tests use a MOCKED Google Identity Services object: they prove our handling of its callback, NOT live Google OAuth. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { installDom } from './helpers/domStub.js';

const A = await import('../../frontend/js/auth-page.js');   // imported BEFORE the DOM stub exists, so the page's init() does not run
const { document } = installDom();
const { safeNext, loginUrl } = await import('../../frontend/js/features/loginPrompt.js');
const SRC = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'frontend', 'js', 'auth-page.js'), 'utf8');

const VALID = ['/listings', '/listings?q=house&area=Gulshan', '/#/property/p1', '/#/plot/DEMO-KPT-1648', '/#owner-verification', '/#verify-document', '/messages', '/loginx'];
const UNSAFE = ['//evil.example', '///evil.example', '/\\evil.example', '/\\/evil.example', 'https://evil.example', 'http://evil.example/x', 'javascript:alert(1)',
  'data:text/html,x', 'evil.example', 'listings', '', '/a\tb', '/a\nb', '/a\u0000b', '/a\u007fb', '/a\\b', '/' + 'a'.repeat(2048), null, undefined, 42, {}, ['/x']];
const LOOPS = ['/login', '/login?next=/listings', '/login#/x', '/signup', '/signup?next=%2F', '/nice-try', '/developer-login', '/LOGIN', '/Login/', '/login.html', '/signup.html',
  '/%6cogin', '/%73ignup', '/a/../login', '/./login', '/x/./../login/', '//login'];

test('valid internal destinations and SPA hashes are kept exactly', () => {
  for (const next of VALID) { assert.equal(A.returnPath(next), next, next); assert.equal(A.afterLogin('/', next), next, next); }
});

test('every unsafe redirect becomes the default "/" (and loops back to sign-in pages are dropped)', () => {
  for (const next of [...UNSAFE, ...LOOPS]) { assert.equal(A.returnPath(next), '/', String(next)); assert.equal(A.afterLogin('/', next), '/', String(next)); }
});

test('one validator: safeRedirect IS safeNext, and returnPath only ever narrows it', () => {
  for (const v of [...VALID, ...UNSAFE, ...LOOPS]) {
    assert.equal(A.safeRedirect(v), safeNext(v), String(v));
    const r = A.returnPath(v);
    assert.ok(r === '/' || r === safeNext(v), String(v));
  }
  assert.doesNotMatch(SRC, /\.test\(target\)/, 'no second hand-written validation regex in auth-page.js');
});

test('missing or invalid next keeps the existing default; the server redirect still wins', () => {
  for (const next of [null, undefined, '', 'nope', '//x']) assert.equal(A.afterLogin('/', next), '/');
  assert.equal(A.afterLogin('/admin', '/listings'), '/admin');          // admin default unchanged
  assert.equal(A.afterLogin('/nice-try', '/listings'), '/nice-try');    // the server's honeypot redirect is not overridden or blocked
  assert.equal(A.afterLogin('//evil.example', '/listings'), '/listings');
});

/* ---- finishAuth: the single exit for every successful flow ---- */
test('finishAuth: preferences are merged first, then the validated next is opened', async () => {
  const order = [];
  await A.finishAuth({ redirect: '/' }, '/#owner-verification', { sync: async () => order.push('sync'), assign: (u) => order.push(`go:${u}`) });
  assert.deepEqual(order, ['sync', 'go:/#owner-verification']);
});

test('finishAuth: a hostile next is replaced by "/" and a nice-try redirect skips the preference sync', async () => {
  const order = [];
  await A.finishAuth({ redirect: '/' }, 'https://evil.example', { sync: async () => order.push('sync'), assign: (u) => order.push(`go:${u}`) });
  await A.finishAuth({ redirect: '/nice-try' }, '/listings', { sync: async () => order.push('SYNC!'), assign: (u) => order.push(`go:${u}`) });
  assert.deepEqual(order, ['sync', 'go:/', 'go:/nice-try']);
});

test('finishAuth: the remember note is shown, then waited on, before leaving', async () => {
  const order = [];
  await A.finishAuth({ redirect: '/', remember_note: 'Not remembered.' }, '/listings', { sync: async () => {}, note: (m) => order.push(`note:${m}`), wait: async (ms) => order.push(`wait:${ms}`), assign: (u) => order.push(`go:${u}`) });
  assert.deepEqual(order, ['note:Not remembered.', 'wait:3000', 'go:/listings']);
});

/* ---- post(): email/password login and signup call onOk (-> finishAuth) only on the server's success answer ---- */
function fakeForm() {
  const bits = {};
  const el = (k) => (bits[k] ||= { hidden: true, disabled: false, textContent: '', classList: { toggle() {}, add() {}, remove() {} }, setAttribute() {}, querySelector: (sel) => el(sel), querySelectorAll: () => [] });
  return { bits, setAttribute() {}, querySelector: (sel) => el(sel), querySelectorAll: () => [] };
}
let sent = [];
function server(handler) {
  globalThis.fetch = async (url, opts = {}) => {
    sent.push(url);
    if (url === '/api/v1/auth/csrf') return { ok: true, status: 200, text: async () => JSON.stringify({ csrf_token: 't' }) };
    const { status = 200, body } = await handler(url, opts);
    return { ok: status < 400, status, text: async () => JSON.stringify(body) };
  };
}

for (const [flow, route] of [['login', 'login'], ['signup', 'signup']]) {
  test(`${flow}: success calls onOk with the server answer, which then returns to next`, async () => {
    sent = []; server(() => ({ body: { redirect: '/', user: { role: 'user' } } }));
    const form = fakeForm(), landed = [];
    await A.post(form, route, { x: 1 }, 'Go', (data) => A.finishAuth(data, '/#/property/p1', { sync: async () => {}, assign: (u) => landed.push(u) }));
    assert.deepEqual(landed, ['/#/property/p1']);
    assert.ok(sent.includes(`/api/v1/auth/${route}`));
  });
  test(`${flow}: a failed attempt never redirects and shows the server message`, async () => {
    for (const status of [400, 401, 403, 409, 429, 500]) {
      sent = []; server(() => ({ status, body: { error: 'Nope.', code: 'x' } }));
      const form = fakeForm(); let called = 0;
      await A.post(form, route, {}, 'Go', () => { called += 1; });
      assert.equal(called, 0, `${flow} ${status}`);
      assert.equal(form.bits['[data-banner]'].textContent, 'Nope.');
    }
  });
  test(`${flow}: no redirect while the request is still pending; an unreachable server never redirects`, async () => {
    let release; const landed = [];
    globalThis.fetch = async (url) => url === '/api/v1/auth/csrf' ? { ok: true, status: 200, text: async () => '{"csrf_token":"t"}' } : new Promise((r) => { release = () => r({ ok: true, status: 200, text: async () => '{"redirect":"/"}' }); });
    const p = A.post(fakeForm(), route, {}, 'Go', (d) => A.finishAuth(d, '/listings', { sync: async () => {}, assign: (u) => landed.push(u) }));
    await new Promise((r) => setTimeout(r, 10));
    assert.deepEqual(landed, [], 'nothing before the server answers');
    release(); await p;
    assert.deepEqual(landed, ['/listings']);
    globalThis.fetch = async () => { throw new TypeError('offline'); };
    const form = fakeForm(); let called = 0;
    await A.post(form, route, {}, 'Go', () => { called += 1; });
    assert.equal(called, 0);
  });
}

/* ---- Google (MOCKED GIS object and fake verifier-less server) ---- */
async function googleHarness(authAnswer) {
  sent = [];
  let cb; const reloads = [];
  server((url) => {
    if (url === '/api/v1/auth/google/config') return { body: { configured: true, client_id: 'cid', nonce: 'n' } };
    if (url === '/api/v1/auth/google') return authAnswer;
    return { status: 404, body: {} };
  });
  globalThis.window.google = { accounts: { id: { initialize: (cfg) => { cb = cfg.callback; }, renderButton() {} } } };
  document.createElement = () => ({ set onload(f) { queueMicrotask(f); } });
  document.head.append = () => {};
  document.querySelector = () => ({ querySelector: () => ({ textContent: '' }) });
  document.querySelectorAll = () => [];
  globalThis.window.location.reload = () => reloads.push(1);
  const done = []; const banners = [];
  await A.setupGoogle((form, msg) => banners.push(msg), (data) => done.push(data));
  return { cb: () => cb, done, banners, reloads };
}

test('google (mocked): a verified credential hands the server answer to the success handler once', async () => {
  const h = await googleHarness({ body: { redirect: '/', user: { role: 'user' } } });
  await h.cb()({ credential: 'tok' });
  assert.equal(h.done.length, 1);
  assert.equal(h.done[0].redirect, '/');
  const landed = [];
  await A.finishAuth(h.done[0], '/#verify-document', { sync: async () => {}, assign: (u) => landed.push(u) });
  assert.deepEqual(landed, ['/#verify-document']);
});

test('google (mocked): cancelled, rejected or unreachable sign-in never reaches the success handler', async () => {
  const h = await googleHarness({ status: 401, body: { error: 'Google sign-in failed.', code: 'google_failed' } });
  await h.cb()(undefined);
  await h.cb()({});
  await h.cb()({ credential: 'bad' });
  assert.equal(h.done.length, 0);
  assert.ok(h.banners.includes('Google sign-in failed.'));
  assert.equal(h.reloads.length, 1, 'a fresh nonce is fetched after a rejected credential (existing behaviour)');
});

test('every successful flow is wired to the one exit (finishAuth via done)', () => {
  assert.match(SRC, /post\(forms\.login, 'login'[^\n]*labels\.login, done\)/);
  assert.match(SRC, /post\(forms\.signup, 'signup'[^\n]*labels\.signup, done\)/);
  assert.match(SRC, /setupGoogle\(banner, \(data\) => done\(data\)/);
  assert.match(SRC, /const done = \(data\) => finishAuth\(data, next,/);
  assert.match(SRC, /const next = params\.get\('next'\);/);
});

test('round trip: the dialog\'s /login?next=... link comes back as the same destination after login', () => {
  for (const v of VALID) {
    const next = new URLSearchParams(new URL(loginUrl(v), 'http://x').search).get('next');
    assert.equal(next, v, v);
    assert.equal(A.afterLogin('/', next), v, v);
  }
  for (const v of ['/login', '//evil.example']) assert.equal(A.afterLogin('/', new URLSearchParams(new URL(loginUrl(v), 'http://x').search).get('next')), '/');
});
