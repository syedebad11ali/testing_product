/* core/prefs.js — browser twin of backend/services/prefs.py. Cookie content is untrusted input: keep only known
 * keys, clamp, accept short codes / ids only (no names, emails, tokens or free text). Both implementations
 * run the same cases (tests/shared/prefs_cases.json). */

const THEMES = ['light', 'dark'];
const LANGS = ['en', 'ur', 'ro'];
const SORTS = ['relevance', 'price_asc', 'price_desc', 'newest', 'area'];
const HINTS = ['intro', 'promo', 'chat_nudge', 'verify_tip', 'demo_notice'];
const TOKEN = /^[a-z0-9][a-z0-9 _.-]{0,39}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/;
export const LIST_LIMITS = { recent: 20, compare: 4, saved: 30, dismissed: 10 };
const MAX_PRICE = 10_000_000_000;
const MAX_JSON_BYTES = 3000;

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

function ids(value, limit) {
  const out = [];
  for (const item of Array.isArray(value) ? value : []) {
    if (typeof item === 'string' && ID.test(item) && !out.includes(item)) out.push(item);
    if (out.length >= limit) break;
  }
  return out;
}

function money(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  return Math.trunc(Math.min(Math.max(value, 0), MAX_PRICE));
}

/** @param {unknown} raw @returns {Record<string, any>} only valid, clamped values */
export function sanitize(raw) {
  if (!isObject(raw)) return {};
  const out = {};
  if (THEMES.includes(raw.theme)) out.theme = raw.theme;
  if (LANGS.includes(raw.lang)) out.lang = raw.lang;
  if (SORTS.includes(raw.sort)) out.sort = raw.sort;
  for (const key of ['area', 'ptype']) {
    const v = raw[key];
    if (typeof v === 'string' && TOKEN.test(v.trim().toLowerCase())) out[key] = v.trim().toLowerCase();
  }
  for (const key of ['min_price', 'max_price']) {
    const n = money(raw[key]);
    if (n !== null) out[key] = n;
  }
  for (const [key, limit] of Object.entries(LIST_LIMITS)) {
    let items = ids(raw[key], limit);
    if (key === 'dismissed') items = items.filter((i) => HINTS.includes(i));
    if (items.length) out[key] = items;
  }
  while (JSON.stringify(out).length > MAX_JSON_BYTES && out.saved && out.saved.length) out.saved.pop();
  return out;
}

/** Account + cookie values on login: cookie scalars win, lists are unioned (cookie items first). */
export function merge(account, cookie) {
  const a = sanitize(account), c = sanitize(cookie);
  const merged = { ...a, ...c };
  for (const key of Object.keys(LIST_LIMITS)) {
    const list = [...new Set([...(c[key] || []), ...(a[key] || [])])];
    if (list.length) merged[key] = list;
  }
  return sanitize(merged);
}
