# G5.3b checkpoint - shared filter leakage

**Working directory:** `/home/claude/g5/work/kpt` (G5.1, G5.2, G5.3a preserved). Patch base: the G5.3a tree, snapshot `/home/claude/g5/g53a`.

## Problem
`kpt_prefs` is one cookie shared by everyone using the browser. Home filters (area, type, sort) were restored from it for every visitor at startup, and logout left them behind. A guest, a signed-out visitor, or the next account therefore saw the previous account's filters.

## Files changed
- `frontend/js/features/homePrefs.js` - `loadHomeFilters` is now async and restores only for a resolved account session; new `clearHomeFilters()`.
- `frontend/js/features/home.js` - `initHomeFilters()` only returns the promise from `loadHomeFilters` (comment updated). The G5.3a setters (`setArea`, `setTypeFilter`, `setSort`, `setSearch`) are unchanged.
- `frontend/js/main.js` - startup keeps the call, and re-renders when filters were restored (`homeFiltersRestored.then(...)`), the same pattern as the favorites load.
- `frontend/js/features/authNav.js` - Log out and guest Exit call `clearHomeFilters()` next to `clearFavorites()`.
- `tests/frontend/homePrefs.test.js` - 7 new tests (the 9 from G5.1-G5.3a are unchanged).
- `docs/G5_PHASE3B_CHECKPOINT.md` - this file.
`sessionUser.js`, `cookies.js`, favorites and the backend were inspected / left untouched (existing `loadSessionUser`, `isAccountSession` from G5.3a are reused).

## Behavior
- **Restore:** `loadHomeFilters` waits for the one existing `GET /auth/me`. Only a registered user or admin gets the stored area / type / sort. Guest, signed-out, unreachable API, or a session that never resolved: nothing restored, page keeps defaults, cookie not rewritten. While the request is pending nothing is restored (unresolved is not authenticated).
- **Why it is async:** at startup `initHomeFilters()` ran before the session was known, so a synchronous gate would have disabled restore for registered users too. Registered users now see their filters after `/auth/me` answers (one re-render), instead of in the first paint.
- **Race:** a filter the visitor changed while the session was loading is kept; the restore skips that field (values compared with the state at call time).
- **Logout / Exit:** `clearHomeFilters()` removes `area`, `ptype`, `sort` from the shared cookie and this visit's memory copy. Theme, language, `recent`, `compare`, `dismissed` and the consent cookie are untouched. If nothing to remove, nothing is written (no cookie is created). A cookie that is unreadable because Preferences consent is missing/outdated is stripped in place (only the filter fields; the cookie is deleted if nothing else is left, never newly created).
- **Registered users:** unchanged apart from the restore timing above. Filter persistence on change (G5.3a) is as before.
- **Not changed:** theme/language logic, favorites, backend, authentication.

## Tests executed (actual results)
- `node --test tests/frontend/homePrefs.test.js` -> 16 run, 16 pass (9 existing + 7 new). New tests, all with an existing filter cookie: guest / signed-out / unreachable API restore nothing and leave the cookie and theme/language alone; a pending `/auth/me` restores nothing and a guest answer restores nothing; user and admin still restore; a filter changed during the wait is kept; `clearHomeFilters` removes only the three fields (cookie and memory, including filters chosen this visit), is a no-op when empty, handles the no-consent cookie and never creates one; both real logout buttons (Log out, guest Exit) clear the filters, keep theme/language/recent and navigate to `/login`.
- Mutation checks: removing the restore gate fails 2 new tests; removing the logout call fails 1.
- Related suites: `sessionUser` 9/9, `cookies` 13/13, `favoritesServer` 15/15, `favoritesAuthGate` 8/8, `routerGuestGate` 16/16, `guestEntry` 7/7, `favorites` 2 of 3 (the known dark-heart CSS assertion, unchanged and unfixed).
- Not run: the full project suite, backend tests, browser tests.

## Known limitations
- Old filters already in the cookie are not removed when a guest or signed-out visitor merely loads the page (they are only not restored). They are removed by an explicit logout / Exit. If a session simply expires with no logout, the old values stay in the cookie and the next registered user on that browser would restore them. Clearing them when the session resolves as non-account is a small follow-up if wanted.
- Registered users' filters are still stored in the shared cookie, not on the account (account filter sync is a later step).
- No committed browser test covers the startup re-render.
