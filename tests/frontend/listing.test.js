import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { installDom } from './helpers/domStub.js';

installDom();
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const { routeFromHash } = await import('../../frontend/js/app/router.js');
const { renderListing } = await import('../../frontend/js/features/listing.js');
const { safeUrl } = await import('../../frontend/js/features/chat.js');
const { resetSessionUser } = await import('../../frontend/js/services/sessionUser.js');
const OwnerVerification = (await import('../../frontend/js/domain/ownerVerification.js')).default;
const { ownerState, state } = await import('../../frontend/js/state/store.js');

const files = OwnerVerification.CSV_FILES.map(name => ({ name, text: fs.readFileSync(path.join(root, 'public', name), 'utf8') }));
ownerState.store = OwnerVerification.createStore(OwnerVerification.parseFiles(files));

test('deep links map to the listing view and survive a refresh (pure hash parsing)', async () => {
  assert.equal(await routeFromHash('#/plot/demo-kpt-1648'), true);
  assert.deepEqual([state.view, state.propId], ['listing', 'DEMO-KPT-1648']);
  assert.equal(await routeFromHash('#/house/DEMO-KPT-8103'), true);
  // G3b2a: routeFromHash is async and #owner-verification is account-only, so it is applied for a registered user (guests: routerGuestGate.test.js)
  resetSessionUser();   // importing the owner screen already looked the session up (no network here -> signed out)
  globalThis.fetch = async () => ({ ok: true, status: 200, text: async () => JSON.stringify({ user: { id: 'u1', name: 'Sara', role: 'user', must_change_password: false } }) });
  assert.equal(await routeFromHash('#owner-verification'), true);
  assert.equal(state.view, 'ownerverify');
});

test('hostile or malformed hashes are ignored', async () => {
  for (const bad of ['#/plot/<script>alert(1)</script>', '#/plot/', '#/evil/DEMO-KPT-1', '#/plot/' + 'A'.repeat(60), '#/plot/a b', '']) assert.equal(await routeFromHash(bad), false, bad);
});

test('listing screen shows dataset facts and never owner fields', () => {
  const html = renderListing('DEMO-KPT-8103');
  assert.match(html, /Apartment in/);
  assert.match(html, /PKR 10,000,000/);
  assert.doesNotMatch(html, /<dt>Owner (name|ID)|Previous owner|Rahim/i);
});

test('unknown listing id is escaped, not injected', () => {
  const html = renderListing('<img src=x onerror=alert(1)>');
  assert.match(html, /Listing not found/);
  assert.doesNotMatch(html, /<img/);
});

test('chat links only accept known safe shapes', () => {
  assert.ok(safeUrl('/#/plot/DEMO-KPT-1648'));
  assert.ok(safeUrl('https://wa.me/923001234567?text=Hello%20there'));
  for (const bad of ['javascript:alert(1)', '//evil.example/x', 'https://evil.example', '/#/plot/<x>', '/admin', null, 5]) assert.equal(safeUrl(bad), null, String(bad));
});
