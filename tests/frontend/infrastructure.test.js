import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

installDom();
const { local, session } = await import('../../frontend/js/core/storage.js');
const { fetchJson } = await import('../../frontend/js/services/http.js');
const { requestChatReply } = await import('../../frontend/js/services/chatApi.js');
const { reportError, AppError } = await import('../../frontend/js/core/errors.js');
const { escapeHtml } = await import('../../frontend/js/core/html.js');

test('storage wrappers never throw when the browser blocks or fills storage', () => {
  const real = globalThis.localStorage;
  globalThis.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('quota'); }, removeItem() { throw new Error('x'); } };
  try {
    assert.equal(local.getRaw('k', 'fallback'), 'fallback');
    assert.deepEqual(local.getJSON('k', [1]), [1]);
    assert.equal(local.setJSON('k', { a: 1 }), false);
    local.remove('k');
  } finally { globalThis.localStorage = real; }
});

test('storage getJSON falls back on corrupt JSON', () => {
  session.setRaw('bad', '{not json');
  assert.deepEqual(session.getJSON('bad', { ok: true }), { ok: true });
});

const withFetch = async (impl, fn) => { const real = globalThis.fetch; globalThis.fetch = impl; try { return await fn(); } finally { globalThis.fetch = real; } };
const reply = (status, body) => async () => ({ ok: status < 400, status, text: async () => body });

test('chat api: success returns the parsed payload', async () => {
  await withFetch(reply(200, JSON.stringify({ reply: 'hi', source: 'offline', from_data: true })), async () => {
    assert.equal((await requestChatReply('s', 'hello')).reply, 'hi');
  });
});

test('chat api: HTML/non-JSON response gives an actionable message', async () => {
  await withFetch(reply(502, '<html>bad gateway</html>'), async () => {
    await assert.rejects(() => requestChatReply('s', 'x'), /non-JSON response \(HTTP 502\)/);
  });
});

test('chat api: server error text is surfaced', async () => {
  await withFetch(reply(429, JSON.stringify({ error: 'Too many messages. Please wait a moment.', code: 'rate_limited' })), async () => {
    await assert.rejects(() => requestChatReply('s', 'x'), (e) => e instanceof AppError && e.code === 'rate_limited' && /Too many/.test(e.message));
  });
});

test('chat api: empty reply is rejected', async () => {
  await withFetch(reply(200, JSON.stringify({ reply: '  ' })), async () => {
    await assert.rejects(() => requestChatReply('s', 'x'), /empty response/);
  });
});

test('chat api: network failure becomes a friendly AppError', async () => {
  await withFetch(async () => { throw new TypeError('Failed to fetch'); }, async () => {
    await assert.rejects(() => requestChatReply('s', 'x'), /Could not reach Property Assistance/);
  });
});

test('http: a hung request is aborted and reported as a timeout', async () => {
  const hang = (url, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => { const e = new Error('aborted'); e.name = 'AbortError'; reject(e); }));
  await withFetch(hang, async () => {
    await assert.rejects(() => fetchJson('/x', { timeoutMs: 20 }), (e) => e.code === 'timeout');
  });
});

test('reportError logs and never throws', () => {
  const real = console.error; console.error = () => {};
  try { assert.doesNotThrow(() => reportError(new Error('x'), 'test')); } finally { console.error = real; }
});

test('escapeHtml neutralises markup and quotes', () => {
  assert.equal(escapeHtml(`<img src=x onerror="a('b')">&`), '&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;&amp;');
  assert.equal(escapeHtml(null), '');
});
