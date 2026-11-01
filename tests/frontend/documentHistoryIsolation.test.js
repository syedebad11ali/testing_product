import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { installDom } from './helpers/domStub.js';

/* G6.1b: the document-verification history (`kpt_doc_history`) belongs to the signed-in account. It is shown, kept and deleted only for an
 * account session (checked inside docViewHistory / docDeleteHistory, not only by the router), is bound to the account that made it without
 * storing the account id, is wiped on logout / Exit / account change / expiry, and a history load that finishes late can never bring it back.
 * fetch (/auth/me) and localStorage are in-memory fakes; the real store, flow and session modules run. */
const { document } = installDom();
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.requestAnimationFrame = (fn) => fn();
let dialogs = [];
document.activeElement = null; document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
const origCreate = document.createElement;
document.createElement = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); }; return e; };

const KEY = 'kpt_doc_history';
const store = new Map(); let writes = [];
globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => { writes.push(k); store.set(k, String(v)); }, removeItem: (k) => { store.delete(k); } };
let sessionUser = null, held = [], meCalls = 0;
globalThis.fetch = (url) => {
  if (String(url) !== '/api/v1/auth/me') return Promise.resolve({ ok: true, status: 200, text: async () => '' });
  meCalls += 1;
  if (sessionUser === 'offline') return Promise.reject(new TypeError('offline'));
  const reply = { ok: true, status: 200, text: async () => JSON.stringify({ user: sessionUser }) };
  if (sessionUser && sessionUser.hold) { const u = { ...sessionUser }; return new Promise((resolve) => { held.push(() => resolve({ ok: true, status: 200, text: async () => JSON.stringify({ user: u }) })); }); }
  return Promise.resolve(reply);
};

const S = await import('../../frontend/js/state/store.js');
const { docViewHistory, docDeleteHistory } = await import('../../frontend/js/features/verifyDocument/flow.js');
const { resetSessionUser, loadSessionUser } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');
const { sanitizeResultForStorage } = await import('../../frontend/js/domain/resultPrivacy.js');
const { docHistory, docState, state, loadDocHistory, clearDocHistory, addDocHistory } = S;

const A = { id: 'a1b2c3d4e5f60718293a4b5c6d7e8f90', name: 'Alice Aziz', email: 'alice@example.com', role: 'user', must_change_password: false };
const B = { id: '0f9e8d7c6b5a49382716f5e4d3c2b1a0', name: 'Bob Baig', email: 'bob@example.com', role: 'user', must_change_password: false };
const ADMIN = { id: 'ad000000000000000000000000000001', name: 'Root', role: 'admin', must_change_password: false };
const GUEST = { id: 'ge000000000000000000000000000001', name: 'Guest', role: 'guest', must_change_password: false };
const result = (tag) => ({ method: 'manual', status: 'verified', docType: 'CNIC', title: `Result ${tag}`, fields: { name: tag }, checks: [], reasons: [], limitations: [] });

function reset() {
  clearDocHistory(); resetSessionUser(); store.clear(); writes = []; held = []; meCalls = 0; sessionUser = null;
  S.resetDocState(); state.view = 'home';
  for (const d of [...dialogs]) d.remove(); dialogs = []; showLoginRequired().close(); dialogs = [];
}
async function signInAs(user) { resetSessionUser(); sessionUser = user; await loadSessionUser(); }
/** what a page load does for this account: session answer, then the history load */
async function pageLoadAs(user) { resetSessionUser(); sessionUser = user; return loadDocHistory(); }
const seedRecord = async (user, ...tags) => { await signInAs(user); await loadDocHistory(); for (const t of tags) addDocHistory(result(t)); };

test('guest cannot view history (action called directly): login dialog, nothing opens', async () => {
  reset(); await seedRecord(A, 'A-secret');
  await signInAs(GUEST);
  docHistory.push(result('stale-in-memory'));
  await docViewHistory(0);
  assert.equal(dialogs.length, 1); assert.equal(docState.result, null); assert.equal(state.view, 'home'); assert.equal(docState.historyIndex ?? null, null);
});

test('signed-out visitor cannot view history', async () => {
  reset(); await seedRecord(A, 'A-secret'); await signInAs(null);
  await docViewHistory(0);
  assert.equal(dialogs.length, 1); assert.equal(docState.result, null);
});

test('guest and signed-out visitors cannot delete history (record and list untouched)', async () => {
  for (const who of [GUEST, null]) {
    reset(); await seedRecord(A, 'A-one', 'A-two');
    const before = store.get(KEY); writes = [];
    await signInAs(who);
    await docDeleteHistory(0);
    assert.equal(dialogs.length, 1, 'login dialog'); assert.equal(store.get(KEY), before, 'stored record untouched'); assert.deepEqual(writes, [], 'nothing written'); assert.equal(docHistory.length, 2);
  }
});

test('account A can view its history; a view of an unknown entry does nothing', async () => {
  reset(); await seedRecord(A, 'A-one', 'A-two');
  await docViewHistory(1);
  assert.equal(dialogs.length, 0); assert.equal(docState.result.title, 'Result A-one'); assert.equal(docState.historyIndex, 1);
  const before = docState.result;
  await docViewHistory(9); await docViewHistory(-1); await docViewHistory('0'); await docViewHistory(undefined);
  assert.equal(docState.result, before); assert.equal(dialogs.length, 0);
});

test('A can delete its own entries', async () => {
  reset(); await seedRecord(A, 'A-one', 'A-two');
  await docDeleteHistory(0);
  assert.deepEqual(docHistory.map((r) => r.title), ['Result A-one']);
  assert.equal(JSON.parse(store.get(KEY)).items.length, 1);
});

test('reload during the same authenticated session keeps the history (user and admin)', async () => {
  for (const who of [A, ADMIN]) {
    reset(); await seedRecord(who, 'one', 'two');
    docHistory.splice(0, docHistory.length);                 // a reload: memory is gone, storage stays
    assert.equal(await pageLoadAs(who), true);
    assert.deepEqual(docHistory.map((r) => r.title), ['Result two', 'Result one']);
  }
});

test('account B (same browser) cannot see A\'s history; A\'s record is deleted, not handed over', async () => {
  reset(); await seedRecord(A, 'A-secret');
  assert.equal(await pageLoadAs(B), false);
  assert.equal(docHistory.length, 0); assert.equal(store.has(KEY), false);
  await docViewHistory(0);
  assert.equal(docState.result, null);
  await signInAs(B); await loadDocHistory(); addDocHistory(result('B-own'));
  assert.deepEqual(docHistory.map((r) => r.title), ['Result B-own']);
  assert.doesNotMatch(store.get(KEY), /A-secret/);
});

test('account changes on a live page (no reload): the first action empties A\'s list; B never sees or stores it', async () => {
  reset(); await seedRecord(A, 'A-secret');
  await signInAs(B);                                       // the page re-learns the session; the in-memory list is still A's
  await docViewHistory(0);                                 // refused: the entry is not B's
  assert.equal(docState.result, null); assert.equal(docHistory.length, 0);
  await signInAs(A); await loadDocHistory(); addDocHistory(result('A2'));
  await signInAs(B); addDocHistory(result('B1'));
  assert.deepEqual(docHistory.map((r) => r.title), ['Result B1']);
  assert.doesNotMatch(store.get(KEY), /A2|A-secret/);
});

test('logout and guest Exit clear memory and storage (both handlers call clearDocHistory)', async () => {
  reset(); await seedRecord(A, 'one');
  clearDocHistory();
  assert.equal(docHistory.length, 0); assert.equal(store.has(KEY), false);
  const src = fs.readFileSync(new URL('../../frontend/js/features/authNav.js', import.meta.url), 'utf8');
  const handlers = src.split('\n').filter((l) => l.includes("'/api/v1/auth/logout'"));
  assert.equal(handlers.length, 2, 'Exit (guest) and Log out');
  for (const h of handlers) assert.match(h, /clearDocHistory\(\)/);
  assert.match(src, /import \{ clearDocHistory \} from '\.\.\/state\/store\.js'/);
});

test('expired session: signed-out, guest or unreachable /auth/me restores nothing and removes the record', async () => {
  for (const who of [null, GUEST, 'offline']) {
    reset(); await seedRecord(A, 'A-secret'); const record = store.get(KEY); assert.ok(record);
    assert.equal(await pageLoadAs(who), false);
    assert.equal(docHistory.length, 0); assert.equal(store.has(KEY), false, String(who && who.role || who));
  }
});

test('unresolved session: nothing is shown or restored until the answer; a guest answer then deletes the record', async () => {
  reset(); await seedRecord(A, 'A-secret');
  docHistory.splice(0, docHistory.length);
  resetSessionUser(); sessionUser = { ...GUEST, hold: true };
  const loading = loadDocHistory();
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(docHistory.length, 0); assert.equal(store.has(KEY), true, 'not decided yet');
  const viewing = docViewHistory(0);                        // the action itself waits for the same single session answer
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(docState.result, null); assert.equal(dialogs.length, 0, 'no dialog before the answer either');
  held.forEach((r) => r()); assert.equal(await loading, false); await viewing;
  assert.equal(docState.result, null); assert.equal(dialogs.length, 1, 'a guest answer then gives the login dialog');
  assert.equal(docHistory.length, 0); assert.equal(store.has(KEY), false);
});

test('late response after logout cannot revive cleared history', async () => {
  reset(); await seedRecord(A, 'A-secret');
  docHistory.splice(0, docHistory.length);
  resetSessionUser(); sessionUser = { ...A, hold: true };
  const loading = loadDocHistory();
  clearDocHistory();                                        // logout / Exit while /auth/me is still pending
  held.forEach((r) => r());
  assert.equal(await loading, false);
  assert.equal(docHistory.length, 0); assert.equal(store.has(KEY), false);
});

test('late response cannot revive history even when the browser refuses to delete the stored record', async () => {
  reset(); await seedRecord(A, 'A-secret'); docHistory.splice(0, docHistory.length);
  const realRemove = globalThis.localStorage.removeItem;
  globalThis.localStorage.removeItem = () => { throw new Error('storage blocked'); };   // e.g. a locked-down browser: the record survives logout
  try {
    resetSessionUser(); sessionUser = { ...A, hold: true };
    const loading = loadDocHistory();
    clearDocHistory();                                      // logout while the session answer is pending
    assert.equal(store.has(KEY), true, 'precondition: the record is still stored');
    held.forEach((r) => r());
    assert.equal(await loading, false);
    assert.equal(docHistory.length, 0, 'the late answer did not restore the list');
  } finally { globalThis.localStorage.removeItem = realRemove; }
});

test('late response for A cannot overwrite B after an account switch', async () => {
  reset(); await seedRecord(A, 'A-secret'); docHistory.splice(0, docHistory.length);
  resetSessionUser(); sessionUser = { ...A, hold: true };
  const first = loadDocHistory();
  const second = pageLoadAs(B);                             // a newer load for another account supersedes the first
  held.forEach((r) => r());
  assert.equal(await first, false); await second;
  assert.equal(docHistory.length, 0); assert.doesNotMatch(String(store.get(KEY)), /A-secret/);
});

test('old unowned plain-array records are never read or migrated', async () => {
  reset(); store.set(KEY, JSON.stringify([result('legacy-1'), result('legacy-2')]));
  assert.equal(await pageLoadAs(A), false);
  assert.equal(docHistory.length, 0); assert.equal(store.has(KEY), false, 'deleted, not converted');
  addDocHistory(result('new')); assert.doesNotMatch(store.get(KEY), /legacy/);
});

test('a tampered or foreign-bound record is deleted', async () => {
  reset(); await seedRecord(A, 'A-secret');
  const rec = JSON.parse(store.get(KEY)); rec.b = 'forged'; store.set(KEY, JSON.stringify(rec));
  assert.equal(await pageLoadAs(A), false); assert.equal(store.has(KEY), false);
  store.set(KEY, '{not json'); assert.equal(await pageLoadAs(A), false); assert.equal(store.has(KEY), false);
});

test('nothing is stored without an account session', async () => {
  for (const who of [GUEST, null]) {
    reset(); await signInAs(who); writes = [];
    assert.equal(addDocHistory(result('x')), false);
    assert.deepEqual(writes, []); assert.equal(store.has(KEY), false); assert.equal(docHistory.length, 0);
  }
});

test('the stored record carries no owner information and no extra document data', async () => {
  reset(); await seedRecord(A, 'one');
  const raw = store.get(KEY), rec = JSON.parse(raw);
  assert.deepEqual(Object.keys(rec).sort(), ['b', 's', 'items', 'v'].sort());
  assert.equal(rec.v, 1);
  for (const secret of [A.id, A.email, A.name, 'Alice', 'alice']) assert.equal(raw.includes(secret), false, secret);
  assert.equal(JSON.stringify(rec.items), JSON.stringify(docHistory.map(sanitizeResultForStorage)));   // exactly the already-masked results, nothing more
  assert.equal(rec.items.length, 1);
});

test('the G6.1a guards still hold: guest document actions are still refused', async () => {
  reset(); await signInAs(GUEST);
  const { docGoStep } = await import('../../frontend/js/features/verifyDocument/flow.js');
  await docGoStep('history');
  assert.equal(dialogs.length, 1); assert.equal(docState.step, 'landing');
});
