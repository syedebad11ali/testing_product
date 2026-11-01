import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

/* G6.2a-1: the property page's "Upload document to check" used to read nothing, wait 1.5 s and show a fixed "Reference match: Yes".
 * It is gone. The page now says plainly that a per-property file check is not available there, and points to the existing,
 * login-gated document check. These tests prove: no file input / delayed result / success wording on the page, a stray .txt cannot
 * produce a match through the real flow, the removed handler cannot be reached, and the document check keeps its access gate. */
const { document } = installDom();
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.requestAnimationFrame = (fn) => fn();
let dialogs = [];
document.activeElement = null;
document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
const origCreate = document.createElement;
document.createElement = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); }; return e; };

let fetchUrls = [], fileReads = 0;
function stubSession(user) {
  globalThis.fetch = (url) => {
    fetchUrls.push(String(url));
    return Promise.resolve({ ok: true, status: 200, text: async () => JSON.stringify({ user }) });
  };
}
globalThis.FileReader = class { readAsDataURL() { fileReads += 1; } readAsArrayBuffer() { fileReads += 1; } };

const propertyModule = await import('../../frontend/js/features/property.js');
const { renderVerify, renderReport } = propertyModule;
const { PROPERTIES } = await import('../../frontend/js/data/properties.js');
const { ACTIONS } = await import('../../frontend/js/ui/actions.js');
const { state, docState, resetDocState } = await import('../../frontend/js/state/store.js');
const { resetSessionUser } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');

const ROW = { id: 'u1', name: 'Sara', must_change_password: false };
const txt = () => ({ files: [{ name: 'definitely-not-a-property-document.txt', type: 'text/plain', size: 3 }], value: '' });
const noticeOf = (html, id) => {
  const from = html.indexOf(`id="docnotice-${id}"`);
  assert.ok(from > -1, `${id}: the honest notice is present`);
  return html.slice(from, html.indexOf('</button>', from) + 9);
};
function reset(user) {
  resetSessionUser(); resetDocState(); fetchUrls = []; fileReads = 0;
  state.view = 'home'; state.propId = null;
  for (const d of [...dialogs]) d.remove();
  dialogs = [];
  stubSession(user);
  showLoginRequired().close(); dialogs = [];
}

test('every property verify page: no file input, no fake result panel, no success wording, honest notice instead', () => {
  for (const p of PROPERTIES) {
    const html = renderVerify(p.id);
    assert.ok(!/type="file"/.test(html), `${p.id}: a file input is still offered`);
    assert.ok(!/handleDocUpload|fileup-|id="ar-|id="proc-|Extracting/.test(html), `${p.id}: fake upload markup remains`);
    assert.ok(!/Reference match/i.test(html), `${p.id}: "Reference match" is shown`);
    const notice = noticeOf(html, p.id);
    assert.match(notice, /not available on this page/);
    assert.match(notice, /no file is read or checked here/);
    assert.match(notice, /indicative only and is not official ownership authentication/);
    assert.ok(!/verified|reference match|\byes\b|\bmatch(es|ed)?\b/i.test(notice.replace(/not official ownership authentication/g, '')), `${p.id}: notice carries success wording`);
    assert.match(notice, /data-onclick="openVerifyDocument\(\)"/);
  }
  for (const p of PROPERTIES) assert.ok(!/Reference match/i.test(renderReport(p.id)), `${p.id}: report shows "Reference match"`);
});

test('the fake handler is gone: not exported, not in the action table, and an injected data-onchange for it reaches nothing', () => {
  assert.equal(propertyModule.handleDocUpload, undefined);
  assert.equal(ACTIONS.handleDocUpload, undefined);
  for (const p of PROPERTIES) {
    const names = [...renderVerify(p.id).matchAll(/data-on\w+="(\w+)\(/g)].map((m) => m[1]);
    for (const n of names) assert.equal(typeof ACTIONS[n], 'function', `${p.id}: ${n} is not a registered action`);
  }
});

test('no fixed delayed result: the rendered page is unchanged 1.7 s later and nothing is scheduled by the page itself', async () => {
  reset({ ...ROW, role: 'user' });
  const timers = [];
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn, ms, ...a) => { timers.push(ms); return realSetTimeout(fn, ms, ...a); };
  try {
    document.getElementById('app').innerHTML = renderVerify('p1');
    const before = document.getElementById('app').innerHTML;
    assert.deepEqual(timers.filter((ms) => ms >= 1000), [], 'rendering scheduled a long timer');
    await new Promise((r) => realSetTimeout(r, 1700));
    const after = document.getElementById('app').innerHTML;
    assert.equal(after, before);
    assert.ok(!/Reference match|auth-result[^"]*show|>Yes</.test(after));
  } finally { globalThis.setTimeout = realSetTimeout; }
});

test('an arbitrary .txt file given to the real document flow cannot produce a result or a match', async () => {
  reset({ ...ROW, role: 'user' });
  const { docHandleFile } = await import('../../frontend/js/features/verifyDocument/flow.js');
  await docHandleFile(txt());
  assert.equal(docState.result, null, 'a result was produced for a .txt file');
  assert.ok(docState.fileError, 'the unsupported file was not reported to the user');
  assert.equal(docState.file, null, 'the unsupported file was accepted');
  assert.equal(fileReads, 0, 'an unsupported file was read');
  assert.deepEqual(fetchUrls.filter((u) => u !== '/api/v1/auth/me'), [], 'the file went somewhere');
});

for (const [label, user] of [['signed-out visitor', null], ['guest', { ...ROW, role: 'guest' }]]) {
  test(`${label}: the notice's button (openVerifyDocument) is still refused with the login dialog and does nothing`, async () => {
    reset(user);
    await ACTIONS.openVerifyDocument();
    await new Promise((r) => setTimeout(r, 30));
    assert.equal(dialogs.length, 1, 'login dialog shown');
    assert.equal(state.view, 'home');
    assert.equal(docState.step, 'landing');
    assert.equal(fileReads, 0);
  });
}

test('registered user: the notice button opens the existing document check without reading any file', async () => {
  reset({ ...ROW, role: 'user' });
  await ACTIONS.openVerifyDocument();
  await new Promise((r) => setTimeout(r, 30));   // nav() resolves the session one tick later
  assert.equal(dialogs.length, 0);
  assert.equal(state.view, 'verify-document');
  assert.equal(docState.result, null);
  assert.equal(fileReads, 0);
});
