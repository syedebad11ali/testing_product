/* fetch() with a timeout and typed failures. Never throws a raw TypeError at callers. */
import { AppError } from '../core/errors.js';

/* CSRF (double submit): state-changing calls to auth/admin/verification routes carry the token that
 * GET /api/v1/auth/csrf put in the (JS-readable) csrf cookie. Cached in memory only. */
const CSRF_PATHS = /^\/api(?:\/v1)?\/(?:auth|admin|verification|messages|listings)\//;
let csrfToken = null;

function needsCsrf(url, method) {
  if (method === 'GET' || method === 'HEAD') return false;
  try { return CSRF_PATHS.test(new URL(url, 'http://local').pathname); } catch (_) { return false; }
}

export async function loadCsrf(force = false) {
  if (csrfToken && !force) return csrfToken;
  try {
    const r = await fetch('/api/v1/auth/csrf', { credentials: 'same-origin' });
    csrfToken = (await r.json()).csrf_token || null;
  } catch (_) { csrfToken = null; }
  return csrfToken;
}

export async function fetchJson(url, options = {}) {
  const first = await fetchOnce(url, options);
  if (first.status === 403 && first.data && first.data.code === 'csrf_failed' && needsCsrf(url, options.method || 'GET')) {
    await loadCsrf(true);
    return fetchOnce(url, options);
  }
  return first;
}

async function fetchOnce(url, { method = 'GET', body, timeoutMs = 30000 } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (needsCsrf(url, method)) { const t = await loadCsrf(); if (t) headers['X-CSRF-Token'] = t; }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (error && error.name === 'AbortError') throw new AppError('The request timed out. Please try again.', { code: 'timeout', cause: error });
    throw new AppError('Could not reach the server. Check your connection and try again.', { code: 'network', cause: error });
  } finally {
    clearTimeout(timer);
  }
  const text = await response.text();
  let data = null;
  try { data = JSON.parse(text); } catch (_) { /* handled below */ }
  return { ok: response.ok, status: response.status, data };
}
