/* features/homePrefs.js — remember the Home screen's area / type / sort choice, per ACCOUNT.
 * G5.3c: a registered user's or admin's filters live in their own account preferences (GET/PUT /api/v1/auth/prefs; the account is the
 * session's, no user id is sent). They are NOT stored in the shared `kpt_prefs` cookie any more: that cookie belongs to the browser,
 * not to a person. Guests, signed-out visitors and sessions that are not resolved yet use the filters normally on screen (state) but can
 * neither load nor save any: nothing is read from or written to storage or the API for them (G5.3a/b). Free-text search is never stored.
 * Values from the server are untrusted: they are only used to pick one of the options the page really offers (case-insensitive match).
 * Old filters left in the cookie by earlier versions are removed, never migrated (nobody can say which account they belonged to). */
import { readPrefs, writePrefs, getCookie, setCookie, removeCookie, PREFS_COOKIE } from '../core/cookies.js';
import { sanitize } from '../core/prefs.js';
import { isAccountSession, loadSessionUser } from '../services/sessionUser.js';
import { fetchAccountPrefs, putFilterPrefs } from '../services/accountApi.js';

// UI sort values -> cookie codes (core/prefs.js SORTS). "Largest Property" has no code, so it is not remembered.
const SORT_TO_CODE = { newest: 'newest', low: 'price_asc', high: 'price_desc' };
const CODE_TO_SORT = Object.fromEntries(Object.entries(SORT_TO_CODE).map(([ui, code]) => [code, ui]));

const pick = (value, options) => (typeof value === 'string' ? options.find((o) => o.toLowerCase() === value.toLowerCase()) : undefined);

/** Pure: saved prefs + the options the page offers -> the filter state to start with. */
export function restoreFilters(prefs, areas, types) {
  const out = {};
  const area = pick(prefs && prefs.area, areas), type = pick(prefs && prefs.ptype, types);
  if (area) out.areaFilter = area;
  if (type) out.typeFilter = type;
  if (prefs && typeof prefs.sort === 'string' && Object.hasOwn(CODE_TO_SORT, prefs.sort)) out.sort = CODE_TO_SORT[prefs.sort];
  return out;
}

/** Pure: current filter state -> the prefs patch (null clears a key; the sanitiser drops it). */
export function filtersPatch(state) {
  return { area: state.areaFilter ? state.areaFilter.toLowerCase() : null, ptype: state.typeFilter ? state.typeFilter.toLowerCase() : null,
    sort: SORT_TO_CODE[state.sort] || null };
}

const FILTER_KEYS = ['area', 'ptype', 'sort'];

const runtime = { loadSeq: 0, resets: 0, pending: null, running: null, status: 'idle' };
/** 'idle' (nothing sent), 'saving', 'saved' (the server confirmed the stored values) or 'error' (the last save was not confirmed). */
export const homeFiltersStatus = () => runtime.status;
/** Resolves when no save is queued or in flight (used by tests and callers that must wait). */
export const homeFiltersSettled = () => runtime.running || Promise.resolve();

/** Take the filter fields out of the shared cookie and this visit's memory copy; theme, language and every other preference stay.
 *  Nothing is written when there is nothing to remove, and a cookie is never created. @returns {boolean} true when something was removed. */
function stripSharedFilters() {
  let cleared = false;
  const current = readPrefs();
  if (FILTER_KEYS.some((k) => k in current)) { writePrefs({ area: null, ptype: null, sort: null }); cleared = true; }
  // A cookie that readPrefs() does not return (no current Preferences consent) can still hold old filters: strip them in place.
  try {
    const raw = getCookie(PREFS_COOKIE);
    if (raw && raw.length <= 4000) {
      const stored = sanitize(JSON.parse(raw));
      if (FILTER_KEYS.some((k) => k in stored)) {
        for (const k of FILTER_KEYS) delete stored[k];
        if (Object.keys(stored).length) setCookie(PREFS_COOKIE, JSON.stringify(stored), { days: 183 }); else removeCookie(PREFS_COOKIE);
        cleared = true;
      }
    }
  } catch (_) { /* unreadable cookie: nothing to strip */ }
  return cleared;
}

/** Load the stored area / type / sort of the signed-in ACCOUNT (registered user or admin) into `state`.
 *  Waits for the one existing GET /auth/me, then reads that account's own preferences. A guest, a signed-out visitor, an unreachable
 *  API, an unresolved session or a failed/invalid answer restores nothing (defaults stay; there is no cookie fallback). A filter the
 *  visitor changed while this was loading is kept, and an answer that arrives after logout, another load or a session change is
 *  ignored. Old filters in the shared cookie are removed first. Never rejects.
 *  @returns {Promise<boolean>} true when at least one stored filter was applied to `state` (the caller re-renders). */
export async function loadHomeFilters(state, areas, types) {
  stripSharedFilters();
  const seq = ++runtime.loadSeq;
  const before = { areaFilter: state.areaFilter, typeFilter: state.typeFilter, sort: state.sort };
  try { await loadSessionUser(); } catch (_) { /* loadSessionUser resolves null on failure; stay unauthorised */ }
  if (seq !== runtime.loadSeq || !isAccountSession()) return false;
  const ticket = loadSessionUser();             // the cached request of THIS session (no new request: the session is loaded)
  const got = await fetchAccountPrefs();
  if (seq !== runtime.loadSeq || !got.ok || !isAccountSession() || loadSessionUser() !== ticket) return false;
  const restored = restoreFilters(got.prefs, areas, types);
  let applied = false;
  for (const key of Object.keys(restored)) if (state[key] === before[key]) { state[key] = restored[key]; applied = true; }
  return applied;
}

/** Logout / exit: drop old filters from shared storage, forget a queued save and ignore any load still in flight.
 *  The account's stored filters on the server are not touched. @returns {boolean} true when something was removed from the cookie. */
export function clearHomeFilters() {
  runtime.loadSeq += 1; runtime.resets += 1; runtime.pending = null; runtime.status = 'idle';
  return stripSharedFilters();
}

/** Save the current filters on the signed-in account (registered user or admin only). The setters call this and do not wait: the screen
 *  is already updated and a server answer never changes it. One save is in flight at a time and each sends the full area/type/sort
 *  triple, so the server applies the user's changes in order and the newest selection wins (a queued save is replaced by a newer one).
 *  A save queued for a session that has since ended or changed is dropped, never sent to another account.
 *  @returns {boolean} true when a save was queued, false when it was (deliberately) not: guest, signed out or unresolved session. */
export function saveHomeFilters(state) {
  if (!isAccountSession()) return false;
  const patch = filtersPatch(state);
  const set = {}, clear = [];
  for (const key of FILTER_KEYS) { if (patch[key]) set[key] = patch[key]; else clear.push(key); }
  runtime.pending = { ticket: loadSessionUser(), gen: runtime.resets, set, clear };
  runtime.status = 'saving';
  if (!runtime.running) runtime.running = drain().finally(() => { runtime.running = null; });
  return true;
}

async function drain() {
  while (runtime.pending) {
    const job = runtime.pending; runtime.pending = null;
    const current = () => job.gen === runtime.resets && !runtime.pending;    // no logout and no newer save since this job was queued
    if (!isAccountSession() || loadSessionUser() !== job.ticket) { if (current()) runtime.status = 'idle'; continue; }   // session ended or changed
    const sent = await putFilterPrefs(job.set, job.clear);
    // Confirmed only if the server really stored what was sent (it drops values the sanitiser does not accept, without an error).
    const stored = sent.ok && Object.entries(job.set).every(([k, v]) => sent.prefs[k] === v) && job.clear.every((k) => !(k in sent.prefs));
    if (current()) runtime.status = stored ? 'saved' : 'error';
  }
}
