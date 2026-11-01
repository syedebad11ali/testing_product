/* core/cookies.js — the only two cookies the browser sets itself: kpt_consent and kpt_prefs.
 * Everything security related (session, CSRF, remember-me, chat id) is set by the server.
 * Never throws; honours consent; falls back to in-memory preferences when cookies are blocked or declined. */
import { sanitize } from './prefs.js';

/** Must equal COOKIE_POLICY_VERSION in backend/security/consent.py (a test checks this). */
export const COOKIE_POLICY_VERSION = 1;
export const CONSENT_COOKIE = 'kpt_consent';
export const PREFS_COOKIE = 'kpt_prefs';
const MAX_COOKIE_CHARS = 3800;
const CONSENT_RECORD = /^v=(\d{1,4})&p=([01])&a=([01])$/;

let memoryPrefs = {}; // this visit only: used when there is no Preferences consent

const doc = () => (typeof document !== 'undefined' && typeof document.cookie === 'string' ? document : null);

function decode(value) { try { return decodeURIComponent(value); } catch (_) { return ''; } }

export function getCookie(name) {
  try {
    const d = doc(); if (!d) return '';
    for (const part of d.cookie.split('; ')) {
      const i = part.indexOf('=');
      if (i > 0 && part.slice(0, i) === name) return decode(part.slice(i + 1));
    }
  } catch (_) { /* cookies blocked */ }
  return '';
}

export function setCookie(name, value, { days = 180 } = {}) {
  try {
    const d = doc(); if (!d) return false;
    const encoded = encodeURIComponent(String(value));
    if (encoded.length > MAX_COOKIE_CHARS) return false;
    const secure = typeof location !== 'undefined' && location.protocol === 'https:' ? '; Secure' : '';
    d.cookie = `${name}=${encoded}; Max-Age=${Math.round(days * 86400)}; Path=/; SameSite=Lax${secure}`;
    return getCookie(name) === String(value);
  } catch (_) { return false; }
}

export function removeCookie(name) {
  try { const d = doc(); if (d) d.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`; } catch (_) { /* ignore */ }
}

/** @returns {{preferences:boolean, analytics:boolean}|null} null = no valid, current choice yet */
export function readConsent() {
  const m = CONSENT_RECORD.exec(getCookie(CONSENT_COOKIE));
  if (!m || Number(m[1]) !== COOKIE_POLICY_VERSION) return null;
  return { preferences: m[2] === '1', analytics: m[3] === '1' };
}

export function consentAllows(category) {
  const c = readConsent();
  return Boolean(c && c[category]);
}

/** Records the visitor's choice. Declining Preferences deletes kpt_prefs immediately. */
export function writeConsent({ preferences = false, analytics = false } = {}) {
  const ok = setCookie(CONSENT_COOKIE, `v=${COOKIE_POLICY_VERSION}&p=${preferences ? 1 : 0}&a=${analytics ? 1 : 0}`, { days: 365 });
  if (!preferences) removeCookie(PREFS_COOKIE);
  else writePrefs({}); // persist anything chosen before consent (e.g. the theme)
  return ok;
}

/** Current preferences, validated. Cookie values (if consent) overlaid by this visit's choices. */
export function readPrefs() {
  let fromCookie = {};
  if (consentAllows('preferences')) {
    try { const raw = getCookie(PREFS_COOKIE); fromCookie = raw && raw.length <= 4000 ? sanitize(JSON.parse(raw)) : {}; } catch (_) { fromCookie = {}; }
  }
  return { ...fromCookie, ...memoryPrefs };
}

export function writePrefs(patch) {
  const merged = sanitize({ ...readPrefs(), ...patch });
  memoryPrefs = merged;
  if (consentAllows('preferences')) setCookie(PREFS_COOKIE, JSON.stringify(merged), { days: 183 });
  return merged;
}

/** Records a viewed listing id (newest first, de-duplicated, max 20). Only valid ids survive sanitising. */
export function addRecent(id) {
  const current = readPrefs().recent || [];
  return writePrefs({ recent: [String(id), ...current.filter((x) => x !== String(id))] }).recent || [];
}

/** "Forget me on this device": every cookie this script owns, plus the in-memory copy. */
export function clearBrowserState() {
  removeCookie(PREFS_COOKIE); removeCookie(CONSENT_COOKIE); memoryPrefs = {};
}

export const _resetForTests = () => { memoryPrefs = {}; };
