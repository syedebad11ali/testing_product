/* Client for the privacy / account endpoints (all CSRF protected by services/http.js). */
import { fetchJson } from './http.js';
import { readPrefs, writePrefs, consentAllows } from '../core/cookies.js';
import { merge } from '../core/prefs.js';
import { local } from '../core/storage.js';
import { STORAGE_KEYS } from '../config.js';

const API = '/api/v1/auth';

export async function listDevices() {
  const { ok, data } = await fetchJson(`${API}/devices`);
  return ok && data && Array.isArray(data.devices) ? data.devices : [];
}
export const revokeDevice = (id) => fetchJson(`${API}/devices/revoke`, { method: 'POST', body: { id } });
export const logoutAll = () => fetchJson(`${API}/logout-all`, { method: 'POST', body: {} });
export const forgetDevice = () => fetchJson(`${API}/forget-device`, { method: 'POST', body: {} });
export const deleteAccount = (password) => fetchJson(`${API}/delete-account`, { method: 'POST', body: { password, confirm: 'DELETE' } });

/** After login: merge the account's saved preferences with this browser's and keep both in sync. Never throws.
 *  G5.2: favorites are per account. The browser-wide preferences cookie never contributes its `saved` list to the account and never
 *  receives the account's, and the legacy global favorites key is deleted (its content is not migrated).
 *  G5.3c: the same holds for the home filters (area, ptype, sort): they live on the account only, so an old filter in the shared cookie
 *  is never pushed into the account, and the account's filters are never written into the shared cookie. Theme and language still sync. */
export async function syncPrefsAfterLogin() {
  try {
    local.remove(STORAGE_KEYS.favoriteProperties);
    const got = await fetchJson(`${API}/prefs`);
    const account = got.ok && got.data ? got.data.prefs : {};
    const { saved: _deviceSaved, area: _dArea, ptype: _dType, sort: _dSort, ...devicePrefs } = consentAllows('preferences') ? readPrefs() : {};
    const merged = merge(account, devicePrefs);
    const put = await fetchJson(`${API}/prefs`, { method: 'PUT', body: { prefs: merged } });
    if (put.ok && put.data && put.data.prefs) { const { saved: _accountSaved, area: _aArea, ptype: _aType, sort: _aSort, ...rest } = put.data.prefs; writePrefs({ ...rest, saved: [], area: null, ptype: null, sort: null }); }   // null also removes any old filter already in the cookie
  } catch (_) { /* preferences are a convenience; login must not fail because of them */ }
}

/* G5.3c: the account's home filters (area, ptype, sort) in the existing account preferences. The account is the session's: no user id
 * is sent. Both calls resolve to {ok, prefs} (never throw); `prefs` is the server's stored result, or null on any failure. */
const prefsResult = ({ ok, data }) => ({ ok: Boolean(ok && data && data.prefs && typeof data.prefs === 'object'), prefs: ok && data && data.prefs && typeof data.prefs === 'object' ? data.prefs : null });
export async function fetchAccountPrefs() {
  try { return prefsResult(await fetchJson(`${API}/prefs`)); } catch (_) { return { ok: false, prefs: null }; }
}
/** `set` = {area?, ptype?, sort?} values to store; `clear` = filter keys to unset. PUT merges, so every other field (theme, lang,
 *  saved, recent, ...) is left exactly as stored. */
export async function putFilterPrefs(set, clear) {
  try { return prefsResult(await fetchJson(`${API}/prefs`, { method: 'PUT', body: { prefs: set, remove: { fields: clear } } })); } catch (_) { return { ok: false, prefs: null }; }
}
