/* features/favorites.js — account-specific favorites (G5.2). The saved list belongs to the signed-in account and lives on the server
 * (account preferences). Nothing about favorites is kept in a browser-wide place: the old `kpt_favorite_properties` key is only ever
 * deleted, never read, and is never copied into an account. state.saved is a cache of the CURRENT account's server list: it is filled
 * after the session is known, emptied on logout / account change, and changed only after the server confirmed the change. */
import { STORAGE_KEYS } from '../config.js';
import { local } from '../core/storage.js';
import { readPrefs, writePrefs } from '../core/cookies.js';
import { state, favoritesRuntime } from '../state/store.js';
import { isAccountUser, loadSessionUser, resetSessionUser } from '../services/sessionUser.js';
import { addSaved, fetchSaved, removeSaved } from '../services/favoritesApi.js';
import { showLoginRequired } from './loginPrompt.js';

export const SAVED_LIMIT = 30;   // the server enforces the same limit (backend/services/prefs.py LIST_LIMITS)
export const MESSAGES = Object.freeze({
  load: 'We could not load your saved properties. Please try again.',
  save: 'We could not save this property. Please try again.',
  remove: 'We could not remove this property. Please try again.',
  limit: `You can save up to ${SAVED_LIMIT} properties. Remove one to save another.`,
});

/** Removes the pre-G5.2 browser-wide favorites and any `saved` list that reached the (browser-wide) preferences cookie. Safe to repeat. */
export function clearLegacyFavorites() {
  local.remove(STORAGE_KEYS.favoriteProperties);
  try { if ((readPrefs().saved || []).length) writePrefs({ saved: [] }); } catch (_) { /* cookies unavailable */ }
}

/** Forget the current account's favorites (logout or a different account): in-memory list, loading state, in-flight loads/writes. */
export function clearFavorites() {
  state.saved.clear();
  favoritesRuntime.generation += 1;
  favoritesRuntime.status = 'idle'; favoritesRuntime.userId = null; favoritesRuntime.loading = null;
  clearLegacyFavorites();
}

/** Updates the heart / Save Property controls on screen from state.saved (all of them, or only those of `id`). */
export function refreshFavoriteControls(id) {
  document.querySelectorAll('[data-favorite-id]').forEach((button) => {
    const buttonId = button.dataset.favoriteId;
    if (id !== undefined && buttonId !== id) return;
    const saved = state.saved.has(buttonId);
    button.classList.toggle('saved', saved);
    button.setAttribute('aria-pressed', String(saved));
    if (button.hasAttribute('data-favorite-label')) {
      button.querySelector('[data-favorite-label]').textContent = saved ? 'Saved' : 'Save Property';
    } else {
      button.setAttribute('aria-label', saved ? 'Remove from saved properties' : 'Save property');
      button.querySelector('[data-favorite-heart]').textContent = saved ? '♥' : '♡';
    }
  });
}

/** Short alert for a failed favorites action (the existing error style, announced to screen readers). */
export function notify(message) {
  try {
    let box = document.getElementById('favNotice');
    if (!box) { box = document.createElement('div'); box.id = 'favNotice'; box.className = 'fav-notice'; box.setAttribute('role', 'alert'); document.body.appendChild(box); }
    box.textContent = message;
    clearTimeout(favoritesRuntime.noticeTimer);
    favoritesRuntime.noticeTimer = setTimeout(() => { box.textContent = ''; if (box.remove) box.remove(); }, 6000);
    if (favoritesRuntime.noticeTimer && favoritesRuntime.noticeTimer.unref) favoritesRuntime.noticeTimer.unref();
  } catch (_) { /* no DOM: nothing to show */ }
}

function applyList(ids) { state.saved.clear(); ids.forEach((id) => state.saved.add(id)); }

/** Loads the signed-in account's favorites once per account. true = state.saved now holds that account's server list.
 *  false = signed out / guest / the list could not be loaded (state.saved is then empty and status is 'error', never a fake empty success). */
export async function ensureFavoritesLoaded() {
  let user = null;
  try { user = await loadSessionUser(); } catch (_) { user = null; }
  if (!isAccountUser(user)) { clearFavorites(); return false; }
  if (favoritesRuntime.userId !== null && favoritesRuntime.userId !== String(user.id)) clearFavorites();   // a different account: drop the old list first
  if (favoritesRuntime.status === 'ready') return true;
  if (favoritesRuntime.loading) return favoritesRuntime.loading;
  const generation = favoritesRuntime.generation;
  favoritesRuntime.status = 'loading'; favoritesRuntime.userId = String(user.id);
  const load = fetchSaved().then((res) => {
    if (generation !== favoritesRuntime.generation) return false;        // logout / account change while loading: ignore the answer
    favoritesRuntime.loading = null;
    if (!res.ok) { state.saved.clear(); favoritesRuntime.status = 'error'; return false; }
    applyList(res.saved); favoritesRuntime.status = 'ready';
    return true;
  });
  favoritesRuntime.loading = load;
  return load;
}

async function persist(id) {
  if (!(await ensureFavoritesLoaded())) { if (isAccountUser(await loadSessionUser().catch(() => null))) notify(MESSAGES.load); return false; }
  const adding = !state.saved.has(id);
  if (adding && state.saved.size >= SAVED_LIMIT) { notify(MESSAGES.limit); return false; }
  const generation = favoritesRuntime.generation;
  const res = adding ? await addSaved(id) : await removeSaved(id);
  if (generation !== favoritesRuntime.generation) return false;           // signed out / switched account meanwhile: do not touch the UI
  if (res.status === 401) {                                              // the session ended: back to the login flow, nothing is shown as saved
    resetSessionUser(); clearFavorites(); refreshFavoriteControls(); showLoginRequired({ feature: 'Saved properties' }); return false;
  }
  const persisted = res.ok && res.saved.includes(id) === adding;
  if (!persisted) { notify(res.code === 'saved_limit' ? MESSAGES.limit : adding ? MESSAGES.save : MESSAGES.remove); return false; }
  applyList(res.saved);                                                  // the server's list is the truth (also keeps other devices' changes)
  refreshFavoriteControls(id);
  return true;
}

/** Adds or removes `id` for the signed-in account. Calls run one after another, so quick repeated taps cannot interleave.
 *  Resolves true only when the server confirmed the change. */
export function toggleFavorite(id) {
  const next = favoritesRuntime.queue.then(() => persist(id), () => persist(id));
  favoritesRuntime.queue = next.catch(() => {});
  return next;
}
