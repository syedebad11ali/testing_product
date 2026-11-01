/* Client for the account's saved properties (G5.2). They live in the existing account preferences (`saved` list of GET/PUT
 * /api/v1/auth/prefs). The server decides the account from the session cookie: no user id is ever sent. Every call resolves to
 * {ok, status, code, saved}; `saved` is the server's list after the call. Never throws. */
import { fetchJson } from './http.js';

const PREFS = '/api/v1/auth/prefs';

function result({ ok, status, data }) {
  const prefs = ok && data && data.prefs && typeof data.prefs === 'object' ? data.prefs : null;
  const saved = prefs ? (Array.isArray(prefs.saved) ? prefs.saved.filter((id) => typeof id === 'string') : []) : null;
  return { ok: Boolean(prefs), status: status || 0, code: data && typeof data.code === 'string' ? data.code : '', saved };
}
async function call(url, options) {
  try { return result(await fetchJson(url, options)); } catch (_) { return { ok: false, status: 0, code: '', saved: null }; }
}

export const fetchSaved = () => call(PREFS);
/** PUT merges: only the new id is sent, so every other preference field and every other saved id is left alone. */
export const addSaved = (id) => call(PREFS, { method: 'PUT', body: { prefs: { saved: [id] } } });
/** Takes one id out of the saved list (the server's `remove` field); nothing else changes. */
export const removeSaved = (id) => call(PREFS, { method: 'PUT', body: { prefs: {}, remove: { saved: [id] } } });
