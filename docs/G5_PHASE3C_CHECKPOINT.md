# G5.3c checkpoint - account-based home filters

**Working directory:** `/home/claude/g5/work/kpt` (G5.1, G5.2, G5.3a, G5.3b preserved; patch base = the G5.3b tree, snapshot `/home/claude/g5/g53b`).

## Sanitizer inspection (before any backend change)
`backend/services/prefs.py::sanitize` (and its browser twin `core/prefs.js`) already accepts `area`, `ptype` (lower-cased tokens `[a-z0-9][a-z0-9 _.-]{0,39}`) and `sort` (`relevance|price_asc|price_desc|newest|area`). `GET|PUT /auth/prefs` are login-required, session-scoped, and `PUT` merges: scalars from the request overwrite, lists are unioned.
**Genuine gap:** a scalar can be overwritten but never unset (the sanitiser drops `null`, so the merge keeps the old value). "All areas" / "All types" could therefore never be stored. Everything else needed no change.

## Backend change (additive, existing endpoint)
- `backend/services/prefs.py` - `apply_update`: `remove["fields"]` may list `area`, `ptype`, `sort`; those keys are removed after the merge (new constant `CLEARABLE_FIELDS`). Any other name (theme, lang, lists, unknown, wrong type) is ignored, so it cannot be used to wipe other preferences. `remove.saved` and the 409 `saved_limit` rule are untouched.
- `backend/api/account.py` - docstring only. No new route, table, migration or auth change.

## Frontend changes
- `frontend/js/services/accountApi.js` - `fetchAccountPrefs()` and `putFilterPrefs(set, clear)` (existing endpoint, no user id sent, never throw). `syncPrefsAfterLogin` no longer copies filters either way: cookie filters are not merged into the account, and the account's filters are not written to the cookie (null also removes old cookie values). Theme/language sync unchanged.
- `frontend/js/features/homePrefs.js` - filters now live on the account:
  - `loadHomeFilters`: removes old filters from the shared cookie, waits for `/auth/me`, and only for a registered user or admin reads `GET /auth/prefs` and applies area/type/sort (values still matched against the options the page offers). Guest, signed out, unreachable or unresolved: nothing read, nothing restored, no cookie fallback.
  - `saveHomeFilters` (setters unchanged, same signature): account sessions only; queues a save and returns at once. One request in flight at a time; each sends the full area/type/sort selection (`prefs:{...set}`, `remove:{fields:[cleared]}`), a queued save is replaced by a newer one, so the newest selection wins on the server. A save is confirmed only if the server's answer contains what was sent (the sanitiser drops invalid values silently). Status via `homeFiltersStatus()` (`idle|saving|saved|error`), `homeFiltersSettled()`.
  - `clearHomeFilters` (logout): strips old cookie filters, drops a queued save, invalidates loads in flight. Account data on the server is not touched.
- `frontend/js/features/home.js` - comment only. `main.js`, `authNav.js`, setters: no change in this step.

## Behavior against the 10 requirements
1-2. Registered users and admins load and save through their session's account preferences.
3. Guests, signed-out and unresolved sessions: no load, no save, no preferences request (tested: 0 requests).
4. Their filters still change the screen (memory `state` only).
5. The shared `kpt_prefs` cookie never receives area/ptype/sort (tested for save, load and login sync); old values are removed, not migrated.
6. Theme and language cookie behavior unchanged (login sync merge rule unchanged: device choice wins).
7. `saved` and `remove.saved` preserved (backend + frontend tests).
8. Updates send only the three filter fields (+ clear list); other fields untouched (tests on theme, lang, saved, recent, compare, dismissed, min_price).
9. A and B isolated: the account is the session's; a queued save is tied to the session it was made in and is dropped if the session changed; a late load answer from another session is ignored.
10. Stale answers: PUT answers never touch `state`; a load answer skips any filter changed meanwhile and is ignored after logout / another load / a session change; saves are serialized.
Failure: a failed or unconfirmed save leaves the screen's choice, reports `error`, writes nothing to the cookie or memory prefs, and the account stays as it was; the next change sends the full current selection. A failed load restores nothing.

## Tests executed (actual results)
- `node --test tests/frontend/homePrefs.test.js` -> 23 run, 23 pass (4 pure-function tests kept; the G5.3a/b tests were rewritten for the account design; new: account save/load, A vs B, favorites/other fields survive, API failure, failed load, rapid changes, stale load, late answers after account switch / logout, login sync, legacy cookie cleanup, both logout buttons).
- `python -W ignore -m unittest tests.backend.test_prefs_filters tests.backend.test_prefs_saved tests.backend.test_cookies` -> Ran 49, OK (10 new in `test_prefs_filters.py`).
- Related frontend suites: `sessionUser` 9/9, `cookies` 13/13, `favoritesServer` 15/15, `favoritesAuthGate` 8/8, `routerGuestGate` 16/16, `guestEntry` 7/7, `authPage` 8/8, `authReturnPath` 17/17, `favorites` 2 of 3 (the known dark-heart CSS assertion, unchanged and unfixed).
- Mutation checks: no `remove.fields` handling -> 6 backend tests fail; no session-ticket check -> 1 frontend test fails; no load-sequence check -> 1 fails; no account gate on save -> 2 fail.
- Test helper `tests/frontend/helpers/fakeAccountServer.js` mirrors `remove.fields` (same rule as the backend).
- Not run: the full project suite, `test_api` / `test_auth`, browser tests, bandit.

## Known limitations
- Registered users now see their saved filters after `/auth/me` and `GET /auth/prefs` answer (one re-render), not in the first paint.
- Filters saved before this step in the shared cookie are discarded, not migrated (nobody can tell which account they belonged to).
- A failed save is silent in the UI (status is exposed via `homeFiltersStatus()`; no notice or CSS was added).
- Two devices of the same account: last write wins per save (each save carries the whole selection); there is no cross-device live refresh.
- A request already sent when the user logs out cannot be cancelled; it still lands on the account it was sent for.
- Whether `/auth/prefs` should refuse guest sessions server-side was not changed (guests simply never call it).
- No committed browser test covers the startup re-render.
