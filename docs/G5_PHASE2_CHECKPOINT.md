# G5.2 checkpoint - server-side favorites and account isolation

**Working directory:** `/home/claude/g5/work/kpt` (G5.1 tree preserved; the G5.1 snapshot used for this patch: `/home/claude/g5/g51`).

## Files changed
Backend (additive; needed because the existing API could not remove a favorite, see contract):
- `backend/services/prefs.py` - new `apply_update(account, incoming, remove)`.
- `backend/api/account.py` - `PUT /auth/prefs` accepts optional `remove`, refuses a silent eviction with 409 `saved_limit`.
- `tests/backend/test_prefs_saved.py` - NEW, 8 tests.

Frontend:
- `frontend/js/services/favoritesApi.js` - NEW: `fetchSaved`, `addSaved`, `removeSaved` (existing prefs API; never sends a user id).
- `frontend/js/features/favorites.js` - NEW: load, persist, serialize, clear, controls refresh, error notice.
- `frontend/js/state/store.js` - `state.saved` starts empty (no read of browser storage); deletes the legacy key; new `favoritesRuntime`.
- `frontend/js/features/home.js` - `toggleSave` keeps the G5.1 gate, then calls `toggleFavorite`; unused storage imports removed.
- `frontend/js/services/accountApi.js` - login sync never merges a cookie `saved` list into an account or writes the account's list into the shared cookie; deletes the legacy key.
- `frontend/js/features/authNav.js` - Log out / Exit call `clearFavorites()`.
- `frontend/js/main.js` - loads the account's favorites after the session is known.
- `frontend/js/features/property.js` - saved list shows "Loading..." / "could not load" instead of a false empty list.
- `frontend/js/config.js` (comment only), `frontend/css/browse.css` (`.fav-notice`, 1 rule; dark-heart CSS untouched).
- Tests: `tests/frontend/favoritesServer.test.js` (NEW, 15), `tests/frontend/helpers/fakeAccountServer.js` (NEW), `tests/frontend/favorites.test.js` and `favoritesAuthGate.test.js` (setup/expectations moved from the legacy key to the account; guest/signed-out assertions kept).
- `docs/G5_PHASE2_CHECKPOINT.md` - this file.

## API contract discovered (not assumed)
- `GET /api/v1/auth/prefs` (login required, `no-store`) -> `{"prefs": {...}}`, sanitised; `saved` is present only when non-empty.
- `PUT /api/v1/auth/prefs` body `{"prefs": {...}}` -> `{"prefs": <stored result>}`. It MERGES (`prefs.merge`): scalars from the request win, lists (`recent`, `compare`, `saved`, `dismissed`) are UNIONED with the request's items first. So the original PUT could only add: **a favorite could not be removed**, and unrelated fields are preserved automatically.
- Limit: `saved` is clamped to 30 by `sanitize`, silently. With 30 saved, adding one pushed the oldest favorite out without an error (request items come first).
- Malformed / duplicate ids: dropped silently by `sanitize` (`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`, de-duplicated). A dropped id is not an error, so the client verifies the id is in the returned list.
- Concurrency: no version/lock; read-merge-write per request. Because the client sends only the id it changes (union), two devices adding different ids both persist; two writers of the same id are idempotent. A race between an add and a remove of the same id is last-write-wins; the window is one request.
- The account comes only from the session (`current_session()["user_id"]`); the body is never read for a user id (test sends `user_id`/`id`: ignored).

Change made: `PUT` also accepts `"remove": {"saved": ["ID"]}` (removed after the merge) and answers **409 `saved_limit`** instead of silently evicting. Existing callers (login sync) are unaffected; existing prefs tests still pass.

## Behavior
- **Loading:** after the session resolves, an account user's list is fetched once (`GET /auth/prefs`) into `state.saved`. Guests/signed-out: nothing loaded, state emptied. Until the load finishes `state.saved` is empty and the saved list says "Loading..."; a failed load sets status `error` (empty list, message, retry on the next tap), never a successful empty list.
- **Save/remove:** `toggleSave` (gate unchanged) -> `toggleFavorite`: ensure loaded, refuse a 31st locally, send ONLY the changed id (`{prefs:{saved:[id]}}` or `{prefs:{},remove:{saved:[id]}}`), wait for the server, check the id really is (not) in the returned list, then set `state.saved` from the server's list and update the controls. No optimistic update, so nothing needs a rollback. Failures show an alert (`MESSAGES`), 409 shows the limit message, 401 shows the login dialog and clears favorites. Taps are queued one after another.
- **Preserved fields:** only the saved list is touched; theme, lang, filters, recent, compare, dismissed stay as stored (tested on the API and through the UI).
- **Legacy key `kpt_favorite_properties`:** never read; deleted when the app state loads, on login sync, on logout and when favorites reset; never migrated; no new browser key is introduced. A `saved` list in the shared preferences cookie is stripped the same way.
- **Logout / account change:** Log out and Exit clear the in-memory list, status, in-flight loads and the legacy key; server favorites are untouched. A different user id in the same page drops the previous list before loading. Late answers after logout are ignored (generation counter). Theme, language, consent and other cookies are untouched.

## Tests executed (actual results)
- `node --test tests/frontend/favorites.test.js` -> 3 run, 2 pass, 1 fail (known dark-heart CSS assertion, unchanged and unfixed).
- `node --test tests/frontend/favoritesAuthGate.test.js` -> 8 run, 8 pass.
- `node --test tests/frontend/favoritesServer.test.js` -> 15 run, 15 pass (server load; save; remove; unrelated fields kept; HTTP 500 / network / 409 failures leave no false saved state; failed load is an error and retried; loading state; legacy key ignored/deleted/not migrated; logout clears memory; B does not see A; A keeps favorites; account switch in one page; late load after logout ignored; guest/signed-out blocked with no prefs request; expired session; 30 limit; rapid taps queued; cookie `saved` not merged into an account). The cookie test fails against the G5.1 `accountApi.js`.
- `python -W ignore -m unittest tests.backend.test_prefs_saved tests.backend.test_cookies` -> Ran 39, OK. `python -W ignore -m unittest tests.backend.test_api tests.backend.test_auth` -> Ran 65, OK.
- Related frontend suites (`cookies homePrefs handlers strictStyles assetsPresent infrastructure listing routerGuestGate sessionUser guestEntry dataStyle propertyDisplayStatus loginPrompt portablePaths`) -> 119 run, 119 pass.
- Ad-hoc end-to-end run (real backend, headless Chromium, script not committed): legacy key removed; A saves, reload keeps it; logout; B sees none; A logs back in and still has it; A removes it; forced 500 -> not shown as saved + message; guest -> dialog, no prefs request; 9/9 pass, no page or CSP errors.
- Not run: the full project suite, committed browser tests, bandit.

## Known limitations
- Dark-heart CSS/test mismatch remains (separate cleanup phase).
- `frontend/js/features/favorites.js` is not covered by a committed browser test (G5 browser phase).
- The 30-item limit and malformed-id dropping are enforced by the server's `sanitize`; a cross-device race could still hit 409 on an add that looked allowed locally (reported to the user, nothing written).
- Favorites made while signed out never existed (blocked since G5.1), so nothing is lost by dropping the legacy key; any ids left in it are intentionally discarded.
- The saved list page and hearts refresh on load/toggle; other open tabs update on their next load.
- Home-filter persistence, theme and language are untouched (G5.3).
