# G3 Emergency Checkpoint (A8b fix)

**Superseded: G3 is now marked `[x]` in `docs/GUEST_BROWSE_ONLY_PLAN.md` after the final regression run (see that file).**

## Files modified (this task, relative to `G3-current-work.patch`)
- `frontend/js/features/loginPrompt.js` (focus restoration)
- `tests/frontend/loginPrompt.test.js` (+6 tests)
- `tests/browser/g3_integration_test.py` (A8b assertion tightened: focus must be on `.topnav-menu`)
- `docs/G3_EMERGENCY_CHECKPOINT.md` (this file)
No backend/G2, router, Google, CSS or other test change.

## The fix
Drawer facts (inspected): container `#drawer.drawer`; open state = class `open`; `closeDrawer()` removes `open` immediately while the 250 ms slide is CSS only; toggle = `button.topnav-menu`; the dialog is opened by a `.drawer-item` button inside `#drawerNav`.
`close()` now calls `focusTarget(opener)`:
1. If the opener is inside a `.drawer` that lacks `.open` (closing or closed) it is NOT used (drawer state, no timeout, no geometry during the transition).
2. Otherwise the opener is used only if `usable()`: connected, not `disabled`, not inside `[hidden]`/`[inert]`/`[aria-hidden="true"]`, and on screen (non-zero, inside the viewport).
3. Otherwise fallback to `.topnav-menu` if usable; otherwise nothing is focused.
Openers outside the drawer (or in a still-open drawer) keep normal restoration. No inline script/style (CSP unaffected).

## Tests actually run (this task)
- `node --test tests/frontend/loginPrompt.test.js`: 20 run, 20 pass (covers: drawer + Escape, drawer + "Not now", focus to menu toggle not the item, outside-drawer restoration, open-drawer opener, disabled/hidden opener, no usable target, 4x repeated open/close with no duplicate dialog and no leaked keydown listener).
- `python tests/browser/g3_integration_test.py` (full file, run twice: before and after tightening A8b): first run 71 PASS / 0 FAIL; second run (tightened A8b) also 71 PASS / 0 FAIL.
## A8b: PASSED (fast Escape from the drawer-opened dialog lands on the menu button).

## Not re-run (by instruction)
Full frontend/backend suites and other browser tests. Previously reported, unchanged: frontend 289/290 (known `favorites.test.js` dark-theme heart stroke), backend 346/347 (missing `pyotp`), baseline browser failures `smoke`, `camera_upload`, `creators`.

## Remaining G3 blockers
- Docs not yet updated: `docs/GUEST_BROWSE_ONLY_PLAN.md`, `work.md`, `HANDOFF.md`, `CHANGELOG.md`.
- Final regression run of full frontend + backend suites after this fix.
- Final ZIP `karachi-property-trust-G3-complete.zip`.
- Live Google OAuth unverified (stub GIS + fake verifier only).
