/* The signed-in user as the server reports it (GET /auth/me), fetched once per page. Used only to decide what to SHOW:
 * the server enforces what a guest or user may actually do. */
import { fetchJson } from './http.js';

let cached = null;       // the one in-flight/finished GET /auth/me
let loaded = false;      // true once that same request has finished (the resolved value below belongs to it)
let current = null;      // its resolved user; meaningful only while `loaded`

/** @returns {Promise<{id:any,name:string,role:string}|null>} null = signed out or the API is unreachable */
export function loadSessionUser() {
  if (!cached) {
    const request = fetchJson('/api/v1/auth/me').then(({ ok, data }) => (ok && data && data.user) || null).catch(() => null)
      .then((user) => {
        if (cached === request) { current = user; loaded = true; }   // ignore an answer that arrived after resetSessionUser()
        return user;
      });
    cached = request;
  }
  return cached;
}

export const isGuestUser = (user) => Boolean(user && user.role === 'guest');
/** A regular signed-in account (user or admin): guests and signed-out visitors are not accounts. */
export const isAccountUser = (user) => Boolean(user && user.role !== 'guest');
export const GUEST_NEEDS_ACCOUNT = 'This needs a free account. Log in or sign up to use it.';
/** True once the session has been loaded (after `await loadSessionUser()`); false before the answer arrives. */
export const isSessionLoaded = () => loaded;
/** Synchronous guest check on the already-loaded session. True ONLY for a loaded session whose role is "guest": signed-out,
 *  registered user, admin and "not loaded yet" are all false, so false never means "registered user" (use isSessionLoaded()). */
export const isGuestSession = () => loaded && isGuestUser(current);
/** Synchronous account check on the already-loaded session. True ONLY for a loaded session whose user is a registered user or admin:
 *  guest, signed-out, API unreachable and "not loaded yet" are all false (unresolved = not authorised). Use it to decide whether
 *  something may be PERSISTED; it never blocks the action itself. */
export const isAccountSession = () => loaded && isAccountUser(current);
/** The loaded session's account id (user or admin), else null (guest, signed-out, unreachable, not loaded yet). Used only to BIND browser-held
 *  data to the account that created it; never displayed and never sent anywhere. */
export const sessionUserId = () => (loaded && isAccountUser(current) && (typeof current.id === 'string' || typeof current.id === 'number') ? String(current.id) : null);
/** SPA views that need an account (display only; the server still refuses). */
export const GUEST_BLOCKED_VIEWS = Object.freeze(['verify', 'report', 'verlist', 'savedlist', 'reportslist', 'ownerverify', 'verify-document']);
export const guestBlockedView = (view) => typeof view === 'string' && GUEST_BLOCKED_VIEWS.includes(view);
export function resetSessionUser() { cached = null; loaded = false; current = null; }
