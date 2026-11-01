# G5.1 checkpoint - favorites authentication gate

**Working directory:** `/home/claude/g5/work/kpt` (copy of `karachi-property-trust-G4-complete.zip`; untouched baseline: `/home/claude/g5/base/kpt`; the original archive was not modified).

## Files modified
- `frontend/js/features/home.js` - `toggleSave(id)` gated (imports `isAccountUser`, `loadSessionUser`, `showLoginRequired`).
- `tests/frontend/favorites.test.js` - setup only: the existing test now runs as a registered user (stubbed `GET /auth/me`) and awaits `toggleSave`. Assertions unchanged; the dark-heart CSS assertion and the CSS were NOT touched.
- `tests/frontend/favoritesAuthGate.test.js` - NEW, 8 focused tests.
- `docs/G5_PHASE1_CHECKPOINT.md` - this file.

Verified paths: `home.js`, `sessionUser.js`, `loginPrompt.js`, `ui/actions.js`, `tests/frontend/favorites.test.js`. `sessionUser.js`, `loginPrompt.js`, `actions.js`, `property.js`, the backend and the preference API were not changed.

## Functionality
`toggleSave(id)` is the one function behind the home-card heart, the detail heart and the detail "Save Property" button (`data-onclick="toggleSave('...')"` unchanged). It is now `async`: it awaits the existing `loadSessionUser()`; only `isAccountUser()` (registered user or admin) continues to the old logic. Signed-out, guest and an unresolved session (API unreachable) get the existing `showLoginRequired({ feature: 'Saved properties' })` (return path = current page via the existing default), return `false`, and leave `state.saved`, `localStorage` and the button states untouched. An open dialog is reused (no duplicate). Authorised calls behave as before and return `true`. Favorites are still stored in this browser only (display-level gate; no server persistence, account switching, logout cleanup or filter changes).

## Tests executed
- `node --test tests/frontend/favorites.test.js` -> 3 run, 2 pass, 1 fail. The failure is the known unrelated dark-heart assertion (`-webkit-text-stroke:1px #000` expected; CSS has `0.5px #011425`), identical to the baseline result (baseline before any change: 2 pass, 1 fail).
- `node --test tests/frontend/favoritesAuthGate.test.js` -> 8 run, 8 pass (guest save; signed-out save; guest remove; unresolved session; tap while loading; repeated taps give one dialog and one session request; registered user save and remove; admin save). Unauthorised cases assert `state.saved` unchanged and zero favorites writes to storage. Against the ungated G4 `home.js` the file gives 0 pass / 8 fail.
- The full project suite was not run (by instruction); no browser test.

## Remaining issues
- The dark-heart CSS/test mismatch stays until the test-cleanup phase.
- Favorites already in a visitor's browser storage are still displayed (e.g. on the saved list); clearing/ownership belongs to later phases (account switching, logout cleanup).
- Not covered by a browser test; the saved-list view (`savedlist`) gating is unchanged (already in `GUEST_BLOCKED_VIEWS`).
