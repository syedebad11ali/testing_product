# G5.3a checkpoint - guest filters are not persisted

**Working directory:** `/home/claude/g5/work/kpt` (G5.1 + G5.2 preserved; G5.2 snapshot used for this patch: `/home/claude/g5/g52`).
The working directory was missing at the start of this step, so it was restored by extracting `karachi-property-trust-G5_2.zip` (it contains the G5.2 files, e.g. `features/favorites.js`, `favoritesServer.test.js`, `docs/G5_PHASE2_CHECKPOINT.md`).

## Files changed
- `frontend/js/services/sessionUser.js` - new `isAccountSession()`: synchronous, true only for a LOADED session whose user is a registered user or admin. Guest, signed-out, API unreachable and not-yet-loaded are all false.
- `frontend/js/features/homePrefs.js` - `saveHomeFilters(state)` returns without writing unless `isAccountSession()`; returns `true`/`false` (persisted or not). Header comment updated.
- `tests/frontend/homePrefs.test.js` - 5 new tests (the 4 existing ones are unchanged).
- `docs/G5_PHASE3A_CHECKPOINT.md` - this file.

`frontend/js/features/home.js` and `frontend/js/core/cookies.js` were inspected and needed no change: the setters already funnel through `saveHomeFilters`, and `setSearch` never persisted.

## Behavior
- Guests, signed-out visitors, unresolved sessions: `setArea`, `setTypeFilter`, `setSort`, `setSearch` update `state` and re-render the list exactly as before. `writePrefs` is not called, so nothing reaches `kpt_prefs` and nothing is kept in the in-memory prefs either.
- Registered users and admins: unchanged (area, type, sort go to `kpt_prefs` as before, subject to Preferences consent; search is never stored).
- No login dialog is involved: the gate is a silent check inside `saveHomeFilters`, not `toggleSave`'s dialog path.
- No account preferences API call is made for filter changes (guest or user; filters were never sent to the API in this code path).
- Unresolved = unauthorised for persistence only. The gate does not await or trigger `GET /auth/me`; it uses the session already loaded at startup.
- Theme/language, favorites, backend: untouched.

## Tests executed (actual results)
- `node --test tests/frontend/homePrefs.test.js` -> 9 run, 9 pass (4 existing + 5 new). The new tests use the real `home.js` setters, a cookie jar with Preferences consent given, and the fake account server. They cover: guest; signed-out; session not loaded; `/auth/me` unreachable; registered user and admin still persist (search text not stored); theme and language cookies untouched; no `/auth/prefs` request; no dialog; `saveHomeFilters` return value.
- Run against the G5.2 `homePrefs.js` (fix reverted): 9 run, 5 pass, 4 fail (guest, signed-out, unresolved, return value). The registered-user test passes both ways, as intended.
- `node --test tests/frontend/homePrefs.test.js tests/frontend/sessionUser.test.js` (sessionUser.js was edited) -> 18 run, 18 pass.
- Not run: the full project suite, backend tests, browser tests.

## Known limitations (not changed, out of scope)
- A registered user who changes a filter before `GET /auth/me` has answered is not persisted for that change (by design: unresolved = unauthorised). The window is the startup request.
- Restoring filters on load (`loadHomeFilters`) still reads `kpt_prefs` for everyone. A guest on a browser where an account holder earlier stored filters will see those on load, and a guest's own filter change will not overwrite or clear them. Whether to stop restoring for guests, or clear the stored filter keys on logout, is a separate decision (G5.3b/c).
- Filters are still stored in the shared cookie, not on the account (account filter synchronization is a later step).
- No browser test covers this yet.
