import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

/* G6.2a-3 (S4): the property DETAIL page shows the owner (initials, name, role) only to a loaded registered user or admin. Guests, signed-out
 * visitors, a session that is still loading and a failed lookup get a neutral "Listed by <seller type>" card with a login button (fail closed).
 * Public details stay for everyone. Display-only protection: the demo records are synthetic and properties.js is still a public file. */
const { document } = installDom();
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.requestAnimationFrame = (fn) => fn();
let dialogs = [];
document.activeElement = null; document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
const origCreate = document.createElement;
document.createElement = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); }; return e; };

let fetchUrls = [], release = null;
function stubSession(user, { hold = false, fail = false } = {}) {
  globalThis.fetch = (url) => {
    fetchUrls.push(String(url));
    if (fail) return Promise.reject(new TypeError('offline'));
    const reply = { ok: true, status: 200, text: async () => JSON.stringify({ user }) };
    return hold ? new Promise((resolve) => { release = () => resolve(reply); }) : Promise.resolve(reply);
  };
}

const { renderDetail, ownerCardHtml, showOwnerLogin } = await import('../../frontend/js/features/property.js');
const { PROPERTIES } = await import('../../frontend/js/data/properties.js');
const { ACTIONS } = await import('../../frontend/js/ui/actions.js');
const { resetSessionUser, loadSessionUser, isAccountSession } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');

const ROW = { id: 'u1', name: 'Sara', must_change_password: false };
const initials = (o) => o.split(' ').map((w) => w[0]).slice(0, 2).join('');
const reset = () => { resetSessionUser(); fetchUrls = []; release = null; for (const d of [...dialogs]) d.remove(); dialogs = []; showLoginRequired().close(); dialogs = []; };
async function as(user, opts) { reset(); stubSession(user, opts); if (opts && opts.hold) { loadSessionUser(); return; } await loadSessionUser(); }

const NOT_ACCOUNT = [
  ['signed-out', null, {}], ['guest', { ...ROW, role: 'guest' }, {}], ['failed lookup', null, { fail: true }], ['session still loading', { ...ROW, role: 'user' }, { hold: true }],
];

function assertNeutral(html, p, label) {
  assert.ok(!html.includes(p.owner), `${label} ${p.id}: owner name present`);
  assert.ok(!html.includes('class="owner-avatar"'), `${label} ${p.id}: initials block present`);
  assert.ok(!html.includes(`${p.ownerRole} · ${p.sellerType}`) && !html.includes('class="owner-role">' + p.ownerRole), `${label} ${p.id}: owner role line present`);
  assert.ok(html.includes('data-owner-hidden'), `${label} ${p.id}: neutral card missing`);
  assert.ok(html.includes('Log in or sign up to see the owner details.'), `${label} ${p.id}: login note missing`);
  assert.ok(html.includes(`Listed by ${p.sellerType}`), `${label} ${p.id}: seller type missing`);
  for (const other of PROPERTIES) assert.ok(!html.includes(other.owner), `${label} ${p.id}: another owner leaked`);
}

test('guest, signed-out, loading and failed-lookup visitors see a neutral card on every detail page', async () => {
  for (const [label, user, opts] of NOT_ACCOUNT) {
    await as(user, opts);
    assert.equal(isAccountSession(), false, label);
    for (const p of PROPERTIES) assertNeutral(renderDetail(p.id), p, label);
    if (release) { release(); await loadSessionUser(); }
  }
});

test('public property details are unchanged for everyone (title, price, area, plot, size, seller type, verify button)', async () => {
  for (const [label, user, opts] of [...NOT_ACCOUNT, ['user', { ...ROW, role: 'user' }, {}]]) {
    await as(user, opts);
    for (const p of PROPERTIES) {
      const html = renderDetail(p.id);
      for (const needle of [p.title, p.priceLabel, p.area, p.size, p.sellerType, 'Verify This Property']) assert.ok(html.includes(needle), `${label} ${p.id}: "${needle}" missing`);
    }
    if (release) { release(); await loadSessionUser(); }
  }
});

test('registered user and admin see the owner card (initials, name, role)', async () => {
  for (const role of ['user', 'admin']) {
    await as({ ...ROW, role });
    assert.equal(isAccountSession(), true, role);
    for (const p of PROPERTIES) {
      const html = renderDetail(p.id);
      assert.ok(html.includes(`<div class="owner-name">${p.owner}</div>`), `${role} ${p.id}: name`);
      assert.ok(html.includes(`<div class="owner-avatar">${initials(p.owner)}</div>`), `${role} ${p.id}: initials`);
      assert.ok(html.includes(`${p.ownerRole} · ${p.sellerType}`), `${role} ${p.id}: role line`);
      assert.ok(!html.includes('data-owner-hidden'), `${role} ${p.id}: neutral card shown to an account`);
    }
  }
});

test('a session that finishes loading flips the card from neutral to owner (the re-render hook sees isAccountSession change)', async () => {
  await as({ ...ROW, role: 'user' }, { hold: true });
  assert.ok(renderDetail('p1').includes('data-owner-hidden'));
  release(); await loadSessionUser();
  assert.ok(renderDetail('p1').includes(PROPERTIES[0].owner));
});

test('ownerCardHtml fails closed for anything that is not exactly true', () => {
  const p = PROPERTIES[0];
  for (const v of [null, undefined, {}, [], 'user', 'admin', 'true', 1, 0, false, NaN, { role: 'user' }, () => true]) {
    const html = ownerCardHtml(p, v);
    assert.ok(!html.includes(p.owner) && html.includes('data-owner-hidden'), String(typeof v));
  }
  assert.ok(ownerCardHtml(p, true).includes(p.owner));
});

test('the neutral card\'s button uses the shared login dialog: no navigation, no request, one dialog', async () => {
  await as({ ...ROW, role: 'guest' });
  assert.equal(typeof ACTIONS.showOwnerLogin, 'function', 'registered in the delegated action table');
  assert.match(renderDetail('p1'), /data-onclick="showOwnerLogin\(\)"/);
  const before = fetchUrls.length;
  ACTIONS.showOwnerLogin(); showOwnerLogin(); ACTIONS.showOwnerLogin();
  assert.equal(dialogs.length, 1, 'one dialog, never stacked');
  assert.equal(fetchUrls.length, before, 'no request');
  assert.equal(globalThis.location.hash, '', 'no navigation');
});

test('no owner field leaks through other guest-visible markup of the detail page', async () => {
  await as({ ...ROW, role: 'guest' });
  const html = renderDetail('p3');
  const owner = PROPERTIES[2];
  for (const secret of [owner.owner, owner.cnic, initials(owner.owner) + '</div>']) assert.ok(!html.includes(secret), 'leak');
  assert.ok(!/00000-\d{7}-\d/.test(html), 'no CNIC-shaped value in guest markup');
});
