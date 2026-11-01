/* T4: Continue as Guest + the restricted guest interface. Pure logic only; the server enforces every restriction, these helpers
 * only decide what to show. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { guestDestination, guestErrorMessage } from '../../frontend/js/auth-page.js';
import { decideSellerChat } from '../../frontend/js/features/sellerChat.js';
import { isGuestUser, isAccountUser } from '../../frontend/js/services/sessionUser.js';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'frontend');
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');

test('guestDestination: guests land on the home page or the public listings, never anywhere else', () => {
  assert.equal(guestDestination(null), '/');
  assert.equal(guestDestination('/listings'), '/listings');
  assert.equal(guestDestination('/listings?page=2'), '/listings?page=2');
  for (const target of ['/messages', '/messages?c=1', '/admin', '/developer-login', '//evil.example', 'https://evil.example', 'javascript:alert(1)', '/\\evil.example', '/listingsx'])
    assert.equal(guestDestination(target), '/', target);
});

test('guestErrorMessage uses the server wording and never claims success', () => {
  assert.match(guestErrorMessage(429, { code: 'guest_limit', error: 'Too many guest sessions from this network. Please try again later or create an account.' }), /Too many guest sessions/);
  assert.match(guestErrorMessage(429, { code: 'rate_limited' }), /Too many attempts/);
  assert.match(guestErrorMessage(500, null), /Could not start a guest session/);
  assert.equal(guestErrorMessage(403, { error: 'Request blocked.', code: 'csrf_failed' }), 'Request blocked.');
  assert.match(guestErrorMessage(429, { code: 'guest_limit' }), /create an account/);
});

test('role helpers: a guest is not an account', () => {
  assert.equal(isGuestUser({ role: 'guest' }), true);
  assert.equal(isAccountUser({ role: 'guest' }), false);
  for (const role of ['user', 'admin']) { assert.equal(isGuestUser({ role }), false); assert.equal(isAccountUser({ role }), true); }
  for (const none of [null, undefined]) { assert.equal(isGuestUser(none), false); assert.equal(isAccountUser(none), false); }
});

test('seller chat: a guest is asked to log in or sign up and never reaches the messaging API', async () => {
  let opened = 0;
  const api = {
    listingByRef: async () => ({ ok: true, status: 200, data: { listing: { id: 7, own: false, contactable: true } } }),
    openConversation: async () => { opened += 1; return { ok: true, data: { conversation: { id: 1 } } }; },
    me: async () => ({ ok: true, data: { user: { role: 'guest', name: 'Guest' } } }),
  };
  const r = await decideSellerChat('KPT-1', api);
  assert.equal(r.action, 'guest');
  assert.match(r.note, /free account/);
  assert.match(r.url, /^\/login\?next=/);
  assert.equal(opened, 0);
  // a regular user still opens the conversation, and a signed-out visitor still goes to login
  assert.equal((await decideSellerChat('KPT-1', { ...api, me: async () => ({ ok: true, data: { user: { role: 'user' } } }) })).action, 'open');
  assert.equal((await decideSellerChat('KPT-1', { ...api, me: async () => ({ ok: true, data: { user: null } }) })).action, 'login');
});

test('owner-name API client turns the guest refusal into a clear message', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => String(url).includes('/auth/csrf')
    ? new Response(JSON.stringify({ csrf_token: 't' }), { status: 200, headers: { 'content-type': 'application/json' } })
    : new Response(JSON.stringify({ error: 'Guests cannot use this.', code: 'guest_not_allowed' }), { status: 403, headers: { 'content-type': 'application/json' } });
  try {
    const { checkOwnerName } = await import('../../frontend/js/services/verificationApi.js');
    await assert.rejects(() => checkOwnerName('DEMO-KPT-001', 'Someone'), (e) => e.code === 'guest_not_allowed' && /free account/.test(e.message));
  } finally { globalThis.fetch = realFetch; }
});

test('login page: Continue as Guest is a separate button that needs no credentials; Developer stays a link', () => {
  const html = read('login.html');
  assert.match(html, /<button type="button" class="btn ghost" id="guest-btn">[\s\S]*?Continue as Guest/);
  assert.match(html, /<a class="btn ghost" id="developer-link" href="\/developer-login">Developer<\/a>/);
  const form = html.match(/<form class="form" id="form-login"[\s\S]*?<\/form>/)[0];
  assert.ok(form.includes('id="guest-btn"'), 'the guest button belongs to the login form area');
  assert.doesNotMatch(html.match(/<button type="button" class="btn ghost" id="guest-btn">[\s\S]*?<\/button>/)[0], /<input/);
});

test('guest pages never offer a create-listing form, messaging link or account panel to guests (source check)', () => {
  assert.match(read('js/listings-page.js'), /const user = sessionUser && !guest;/);
  assert.match(read('js/listings-page.js'), /\$\('#messages-link'\)\.hidden = guest/);
  assert.match(read('js/privacy-page.js'), /data\.user\.role !== 'guest'/);
  assert.match(read('js/features/authNav.js'), /user\.role === 'guest'/);
  assert.match(read('js/auth-page.js'), /data\.user\.role === 'guest'\) \{ banner\(/);   // a guest still sees the login forms
});
