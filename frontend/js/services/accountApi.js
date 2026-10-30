/* Client for the privacy / account endpoints (all CSRF protected by services/http.js). */
import { fetchJson } from './http.js';
import { readPrefs, writePrefs, consentAllows } from '../core/cookies.js';
import { merge } from '../core/prefs.js';

const API = '/api/v1/auth';

export async function listDevices() {
  const { ok, data } = await fetchJson(`${API}/devices`);
  return ok && data && Array.isArray(data.devices) ? data.devices : [];
}
export const revokeDevice = (id) => fetchJson(`${API}/devices/revoke`, { method: 'POST', body: { id } });
export const logoutAll = () => fetchJson(`${API}/logout-all`, { method: 'POST', body: {} });
export const forgetDevice = () => fetchJson(`${API}/forget-device`, { method: 'POST', body: {} });
export const deleteAccount = (password) => fetchJson(`${API}/delete-account`, { method: 'POST', body: { password, confirm: 'DELETE' } });

/** After login: merge the account's saved preferences with this browser's and keep both in sync. Never throws. */
export async function syncPrefsAfterLogin() {
  try {
    const got = await fetchJson(`${API}/prefs`);
    const account = got.ok && got.data ? got.data.prefs : {};
    const merged = merge(account, consentAllows('preferences') ? readPrefs() : {});
    const put = await fetchJson(`${API}/prefs`, { method: 'PUT', body: { prefs: merged } });
    if (put.ok && put.data && put.data.prefs) writePrefs(put.data.prefs);
  } catch (_) { /* preferences are a convenience; login must not fail because of them */ }
}
