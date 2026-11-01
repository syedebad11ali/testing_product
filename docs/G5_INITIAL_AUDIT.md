# G5 Initial Audit — Favorites, Saved Properties, Likes and Preferences

Analysis only. No application code, test, CSS or backend file was changed. Audited tree: `/home/claude/audit/kpt` (extracted from `karachi-property-trust-G4-complete.zip`, 574 entries, single `kpt/` root). Original archives untouched.

Commands actually run: `node --test tests/frontend/favorites.test.js` (2 pass, **1 fail**), `homePrefs.test.js` (4/4 pass), `routerGuestGate.test.js` (16/16 pass). Nothing else was executed (no backend suite, no browser tests, no `npm test`). Backend/browser statements below come from reading code and docs, and are marked "not run".

## 1. Completion matrix

| Area | Requirement | Existing implementation | Status | Tests/evidence | Remaining work |
|---|---|---|---|---|---|
| Favorites | Save property | `frontend/js/features/home.js:122 toggleSave(id)` adds to `state.saved`, writes localStorage `kpt_favorite_properties`. No session check. Any visitor can save. | NOT STARTED (gate); feature itself works | `favorites.test.js` tests 1-2 pass (save works for anyone, by design of the old behavior) | Gate on `loadSessionUser()` + `isAccountUser()`; guest/signed-out → `showLoginRequired`, no state change |
| Favorites | Remove property | Same function (toggle). No separate remove path. | NOT STARTED (gate) | Same | Same gate covers remove |
| Favorites | All save entry points guarded | 3 UI controls, all `data-onclick="toggleSave(...)"` through `ui/actions.js:70`: home card `.fav` (`home.js:108`), detail header `.favbtn` (`property.js:14`), detail "Save Property" button (`property.js:50`). `featured.js`, `listing.js`, `listings-page.js`, widget, `listings.html`: no favorite control. `property.js:84/151 savedmsg` is the report "Saved" note, not a favorite. | NOT STARTED | `grep` evidence only; no browser test of any save control | One gate inside `toggleSave` covers all three. Also add a guard in the store layer (see risks) |
| Saved Properties | Guest access restricted | `router.js` `nav()` / `routeFromHash()` gate `savedlist` via `sessionUser.js:32 GUEST_BLOCKED_VIEWS` (includes `savedlist`) and `FEATURE_NAMES.savedlist`. Direct `#/savedlist` also gated (G3b2a). | COMPLETE AND VERIFIED (view only) | `routerGuestGate.test.js` 16/16 run now (`savedlist` referenced 5x). `g3_integration_test.py` has 0 mentions of `savedlist`; its browser run was reported in G3 docs, not re-run here | Keep. Add one browser check for `#/savedlist` as guest in the G5 browser test |
| Storage | Account-specific isolation | Favorites: single global key `kpt_favorite_properties` (`config.js:21`), read at import time in `state/store.js:19-21`. Not keyed by user. Not cleared on logout (`authNav.js:42` only posts logout and navigates). Account `saved` list exists server-side in prefs but nothing writes it from favorites. | NOT STARTED | `favorites.test.js` asserts the global key | Decide storage model (section 5), key or clear by user, reset on login/logout |
| Preferences | Temporary filters remain public | `setArea`, `setTypeFilter`, `setSort` (`home.js:101,143,144`) change `state` and re-render with no auth. Search `setSearch` same. | COMPLETE AND VERIFIED (works for guests today) | `homePrefs.test.js` 4/4 pass (pure functions). Browser `prefs_test.py` not run | Must stay public. Only the persistence call inside them must be gated |
| Preferences | Persistent saving requires login | Each of the three setters calls `saveHomeFilters(state)` → `writePrefs()` → `kpt_prefs` cookie (`core/cookies.js:74-77`) whenever Preferences consent exists, **for guests too**. Without consent: in-memory only. | NOT STARTED | `tests/browser/prefs_test.py:26-45` runs as a **guest** (`enter_as_guest`) and asserts the cookie contains `price_desc`/`house` and restores after reload. This test encodes the old behavior and conflicts with the G5 target | Gate `saveHomeFilters` on account user; update `prefs_test.py` to use `enter_as_user()` and add a guest "no cookie written, filter still works" case |
| Preferences | Account-specific persistence | `GET/PUT /api/v1/auth/prefs` (`backend/api/account.py:71,80`, `PrefsService` keyed by session `user_id`, table `user_prefs`). Frontend only calls it in `accountApi.js:18 syncPrefsAfterLogin()` (after login). Home filters are never PUT on change; they live in the browser cookie. | PARTIALLY COMPLETE | `test_cookies.py:196` round-trip and `:204` (anon 401, CSRF); not run | Decide whether filters persist via cookie (after login gate) or via PUT to the account. Cookie is device-wide, not account-specific |
| Backend | Authorization and privacy | Both prefs routes `@login_required()`; `_check_account()` refuses guests (G2). Server uses `current_session()["user_id"]` only, no user id parameter. Legacy `/api/auth/prefs` alias gets the same guard. Admin CSV export (`admin.py:181`) selects user/login columns only, no prefs. `user_prefs` deleted on account delete (`auth_service.py:189`). No favorites API exists. | IMPLEMENTED, NOT VERIFIED (not run here) | `test_guest_browse_only.py RoutePermissionMatrix` (all non-public routes: anon 401, guest 403) and `test_cookies.py:204`, per the files. Not executed in this audit | Run the two files before and after G5. Add an explicit guest-403 / cross-user case for `/auth/prefs` |
| Tests | Frontend regression | `favorites.test.js` (3), `homePrefs.test.js` (4), `routerGuestGate.test.js` (16), `loginPrompt.test.js`, `sessionUser.test.js`, `cookies.test.js`. None tests a guest being refused on save or on pref persist. | PARTIALLY COMPLETE | Run now: 22 tests, 21 pass, 1 fail (stroke) | New `tests/frontend/favoritesGuard.test.js` and `homePrefsGuard.test.js` |
| Tests | Backend authorization | See Backend row. | IMPLEMENTED, NOT VERIFIED | Not run | Run existing; add focused prefs authorization tests only if the matrix proves insufficient |
| Tests | Browser regression | No browser test touches favorites. `prefs_test.py` and `cookies_test.py` use `kpt_prefs` as guest. `ci.yml:44` runs `prefs_test` (and others). | NOT STARTED | `grep` of `tests/browser` finds no `toggleSave`/`data-favorite-id` | NEW `tests/browser/g5_favorites_test.py` (guest/user/switch), register in `ci.yml` |
| G5 | Documentation and packaging | Plan lists G5 as `[ ]` items 9-10; matrix row "UI only (client-only feature)". `docs/COOKIES.md` says `kpt_prefs` holds `saved` and filters. | NOT STARTED | n/a | Update plan, work.md, HANDOFF.md, CHANGELOG.md, COOKIES.md; package after review |

## 2. Required report

### A. What already works (preserve)
- Saved Properties view is blocked for guests and signed-out visitors, via menu and direct hash (`router.js`, `routerGuestGate.test.js` 16/16 run now).
- Shared dialog `showLoginRequired({feature, next})` and return path (`loginPrompt.js`, `auth-page.js`), reusable as is.
- `sessionUser.js`: `loadSessionUser()`, `isAccountUser()`, `isGuestSession()`, `resetSessionUser()`.
- Browsing, search, area/type/sort changes are public and work in-session.
- Backend: prefs routes already require an account; server-side per-user storage; sanitiser mirrored front/back (`core/prefs.js` ↔ `services/prefs.py`, shared cases).
- The G3 guest-to-account transition discards the guest row (`_start_session`).

### B. Implemented but unverified
- Backend authorization of `/auth/prefs` (matrix and `test_cookies.py`): code read, not executed.
- `prefs_test.py`, `cookies_test.py`, `g3_integration_test.py`: not run.
- `syncPrefsAfterLogin` merge behavior in a real browser.

### C. What genuinely needs implementation
1. `toggleSave` has no auth check. A guest or signed-out visitor can add and remove favorites (confirmed in code and by the passing tests that assert it).
2. `saveHomeFilters` persists to `kpt_prefs` for guests with consent.
3. Favorites live in a global localStorage key with no account binding, no cleanup on logout/login.
4. Logout does not clear `kpt_favorite_properties` or the `kpt_prefs` cookie.
5. No browser test for favorites; `prefs_test.py` asserts guest persistence (must change).
6. Docs/plan updates.

### D. Privacy and account-isolation risks
- **Account mixing on a shared browser (High for G5):** user A saves properties; logs out; user B (or a guest) on the same browser sees A's hearts, and B's Saved page lists A's items. `state.saved` is loaded at module import from the global key.
- **Guest persistence:** a guest can write `kpt_favorite_properties` (always, no consent check) and `kpt_prefs` (with consent). Note favorites localStorage does not go through the consent mechanism at all.
- **Guest data flows into accounts:** `syncPrefsAfterLogin` merges the cookie into the account via `PUT /auth/prefs`, so whatever a guest chose (filters, theme) is silently adopted by the next account to log in on that browser. The merge also unions the `saved` list from the cookie.
- **Frontend gating is not a security boundary:** favorites have no server API, so only UI/store guards are possible. A guest can still call `localStorage.setItem` from the console; that is unavoidable client-side and harmless once nothing reads it for a guest. Mitigation: ignore/clear the key unless the session is an account user.
- **Backend:** no leak found by reading: user id comes from the session, admin export excludes prefs, deletion removes `user_prefs`. Not run.
- **Cookie consent:** declining Preferences already stops cookie writes (`writePrefs`) but not the localStorage favorites key. G5 should keep that distinction explicit.

### E. Existing test failures
- **Known baseline failure, unchanged:** `tests/frontend/favorites.test.js` test 3 "favorite gradients use blue in light theme, green in dark theme, and pink-red hearts". Run now: 3 tests, 2 pass, 1 fail.
  - Test expects (line 76): `:root[data-theme="dark"] .favorite-heart{-webkit-text-stroke:1px #000}`.
  - Current CSS (`frontend/css/base.css:35`): `:root[data-theme="dark"] .favorite-heart{-webkit-text-stroke:0.5px #011425;}`.
  - The saved-heart rule matches (`stroke:0`). Light/dark gradient and heart colors in the test match the CSS.
  - Intent: not documented. No design doc mentions the stroke; only the plan ("decision needed on which stroke is intended"). Needs an owner decision (CSS change vs test change). Not related to guest gating; keep it a separate item.
- No new failures found in the three suites run. All other suites were not run.

### F. Smallest safe implementation plan
1. **Owner decisions first** (section 4).
2. Add one small helper (e.g. in `sessionUser.js` or a new `features/accountGate.js`): `async requireAccount(feature)` → loads session, returns true for registered/admin, else `showLoginRequired({feature, next})` and returns false. No new auth system.
3. Gate `toggleSave` (`home.js`) with it: guest → dialog and return before touching `state.saved`/storage. This covers all three buttons. Keep `data-onclick` handlers unchanged.
4. Make favorites storage account-aware with the smallest change: read `kpt_favorite_properties` only for an account user, and clear it (and `state.saved`) on logout and when the session is not an account user. Defer a server-side favorites API unless the owner wants cross-device favorites (the `saved` list in `/auth/prefs` already exists, 30-item cap).
5. Gate `saveHomeFilters` (`homePrefs.js`): guests keep changing `state` and re-rendering, but no `writePrefs`. Do not touch theme/lang writes unless the owner decides.
6. On logout, clear `kpt_prefs` filter keys; on login keep `syncPrefsAfterLogin` but stop it from adopting guest-written filters/saved lists (or clear guest cookie values before merge).
7. Tests: new frontend guard tests; update `favorites.test.js` only for the gate (leave the stroke assertion alone until decided); update `prefs_test.py` to use `enter_as_user()` plus a guest case; new `g5_favorites_test.py`; register in `ci.yml`; run the two backend files.
8. Docs and packaging after owner review. Do not start G6.

### G. Working baseline
- Archive: `karachi-property-trust-G4-complete.zip` (as uploaded, 109,629,041 bytes, 574 entries, root `kpt/`), extracted to `/home/claude/audit/kpt`.
- The `.patch` (81,595 bytes) touches only CI, docs, `frontend/widget/chatbot.{js,css}` and three browser tests. It contains nothing about favorites or preferences and was not applied. The separately uploaded `karachi-property-trust-G4-HANDOFF.md` (40,979 bytes) was not read or compared; the ZIP's own `HANDOFF.md` (117 lines) was used. The ZIP is the source of truth.
- Provenance caveat: `docs/G4_PROGRESS.md` and the HANDOFF mention `karachi-property-trust-G4a2.zip` as G4's base, and an earlier "no Git repository, working directory not available" situation. The ZIP has no git history, so the 3-way provenance cannot be checked.

## 3. Direct answers to the audit questions

**Favorites**
1. Save/remove points: 3 buttons (home card, detail heart, detail "Save Property"), all the one function `toggleSave`.
2. Shared function: yes, `home.js:122`, registered in `ui/actions.js:70`.
3. Stored in: `state.saved` (a `Set`) and localStorage `kpt_favorite_properties`.
4. Persisted across reloads: yes (loaded in `store.js:19-21`).
5. Isolated between accounts: no.
6. Guest state after login: it stays; nothing clears or reassigns it.
7. Guest can alter state via another UI action: not through another control found; they can write storage from devtools.
8. Guest direct entry to Saved view: blocked (router gate).
9. Hash route bypass: no, `routeFromHash()` gates it (tests pass).
10. Legacy/hidden controls: none found. `featured.js` has no favorite control.

**Preferences**
1. Temporary: area, type, sort, search (`state.areaFilter`, `typeFilter`, `sort`, `search`). Price range is not in the home setters; `min_price`/`max_price` exist only in the sanitiser.
2. Persisting: `saveHomeFilters` (cookie), `syncPrefsAfterLogin` (PUT), theme/lang `writePrefs`, `addRecent`.
3. Does a guest write `kpt_prefs`: yes, with Preferences consent.
4. API or storage: browser cookie for filters; the account API is used only after login for sync.
5. Isolated between accounts: server side yes (per `user_id`); browser side no (device-wide cookie).
6. Restored incorrectly after switching: yes, possible for the shared cookie and favorites key.
7. Failed authentication and UI state: not tested here; the gate must not leave a half-toggled heart. Plan: decide before mutating.
8. Cookie consent: unchanged by the plan; it must still decide cookie writes for accounts.

## 4. Decisions needed from the owner
1. Favorites storage: keep device localStorage (keyed/cleared per account), or add a server-side favorites store (cross-device)? The smallest plan assumes localStorage keyed per account; the existing `/auth/prefs` `saved` list could be reused later.
2. Theme and language for guests: they also go through `writePrefs`. Are they in scope for "persist preferences requires login", or treated as functional UI settings?
3. The dark-heart stroke: which is intended, `1px #000` (test) or `0.5px #011425` (CSS)?
4. Should logout wipe `kpt_prefs` filter keys and favorites on the device?
5. "Likes": no separate like feature exists. Confirm it means favorites.

## 5. Not verified in this audit
Backend suite, browser tests, full `npm test`, PostgreSQL, TOTP (`pyotp`), real Google sign-in, live behavior of `syncPrefsAfterLogin`. The sandbox ran Node 22.22.2.

**Stopped. No application code written. Waiting for review.**
