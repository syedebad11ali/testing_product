import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { installDom } from './helpers/domStub.js';

installDom();
const { decideSellerChat } = await import('../../frontend/js/features/sellerChat.js');
const api = (over = {}) => ({
  listingByRef: async () => ({ ok: true, status: 200, data: { listing: { id: 'L'.repeat(32), contactable: true, own: false } } }),
  me: async () => ({ ok: true, data: { user: { name: 'Sara' } } }),
  openConversation: async () => ({ ok: true, data: { conversation: { id: 'c'.repeat(32) } } }),
  ...over,
});

test('signed-in buyer is sent to the conversation for that listing', async () => {
  const r = await decideSellerChat('p1', api());
  assert.deepEqual(r, { action: 'open', url: `/messages?c=${'c'.repeat(32)}` });
});

test('signed-out visitor goes through login and comes back with the listing context', async () => {
  const r = await decideSellerChat('p1', api({ me: async () => ({ ok: true, data: { user: null } }) }));
  assert.equal(r.action, 'login');
  assert.equal(r.url, `/login?next=${encodeURIComponent('/messages?listing=p1')}`);
});

test('own listing, unknown listing, unavailable seller and API errors never navigate to a chat', async () => {
  const own = await decideSellerChat('p1', api({ listingByRef: async () => ({ ok: true, status: 200, data: { listing: { own: true, contactable: true } } }) }));
  assert.equal(own.action, 'own');
  const missing = await decideSellerChat('p9', api({ listingByRef: async () => ({ ok: false, status: 404, data: {}, error: 'x' }) }));
  assert.equal(missing.action, 'unavailable');
  const closed = await decideSellerChat('p1', api({ listingByRef: async () => ({ ok: true, status: 200, data: { listing: { contactable: false, own: false } } }) }));
  assert.equal(closed.action, 'unavailable');
  const broken = await decideSellerChat('p1', api({ openConversation: async () => ({ ok: false, status: 500, data: {}, error: 'Try later' }) }));
  assert.deepEqual([broken.action, broken.note], ['error', 'Try later']);
  const offline = await decideSellerChat('p1', api({ me: async () => { throw new Error('net'); } }));
  assert.equal(offline.action, 'error');
});

test('messages page and script render message text only through textContent', () => {
  const src = readFileSync(new URL('../../frontend/js/messages-page.js', import.meta.url), 'utf8');
  assert.doesNotMatch(src, /innerHTML|insertAdjacentHTML|outerHTML|document\.write|eval\(/);
  const admin = readFileSync(new URL('../../frontend/js/admin/admin.js', import.meta.url), 'utf8');
  assert.doesNotMatch(admin, /innerHTML|insertAdjacentHTML|outerHTML|eval\(/);
});

test('messages and admin pages ship no inline handlers, inline scripts or inline styles', () => {
  for (const f of ['messages.html', 'admin.html']) {
    const html = readFileSync(new URL(`../../frontend/${f}`, import.meta.url), 'utf8');
    assert.doesNotMatch(html, /\son\w+=|<script(?![^>]*\ssrc=)|\sstyle=/i, f);
  }
});

test('ban summary lines are built from data only', async () => {
  const src = readFileSync(new URL('../../frontend/js/admin/admin.js', import.meta.url), 'utf8');
  assert.match(src, /export function banSummary/);
  assert.match(src, /\/users\/\$\{u\.id\}\/ban/);
  assert.match(src, /\/users\/\$\{u\.id\}\/unban/);
});
