/* fetch() with a timeout and typed failures. Never throws a raw TypeError at callers. */
import { AppError } from '../core/errors.js';

export async function fetchJson(url, { method = 'GET', body, timeoutMs = 30000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
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
