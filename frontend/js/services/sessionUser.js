/* The signed-in user as the server reports it (GET /auth/me), fetched once per page. Used only to decide what to SHOW:
 * the server enforces what a guest or user may actually do. */
import { fetchJson } from './http.js';

let cached = null;

/** @returns {Promise<{id:any,name:string,role:string}|null>} null = signed out or the API is unreachable */
export function loadSessionUser() {
  if (!cached) {
    cached = fetchJson('/api/v1/auth/me').then(({ ok, data }) => (ok && data && data.user) || null).catch(() => null);
  }
  return cached;
}

export const isGuestUser = (user) => Boolean(user && user.role === 'guest');
/** A regular signed-in account (user or admin): guests and signed-out visitors are not accounts. */
export const isAccountUser = (user) => Boolean(user && user.role !== 'guest');
export const GUEST_NEEDS_ACCOUNT = 'This needs a free account. Log in or sign up to use it.';
export function resetSessionUser() { cached = null; }
