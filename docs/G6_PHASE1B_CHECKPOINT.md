# G6.1b checkpoint — document history account isolation

Baseline: the G6.1a working tree (`karachi-property-trust-G5-merged-project-v2.zip` + `g6-phase1a.patch`). Scope: frontend only. Not started: G6.2.

## Problem (G6 audit 4.2)
`kpt_doc_history` was one plain `localStorage` array shared by every visitor of the browser: loaded for everyone at start-up, written without any account, never cleared at logout. On a shared browser, account B could open "View past document checks" and see account A's results.

## Behaviour now
* **Only an account session sees or keeps history.** `docViewHistory(i)` and `docDeleteHistory(i)` begin with the G6.1a check (`if(!isAccountSession()) return gateThen(...)`): guest, signed-out, unreachable and not-yet-loaded sessions get the shared "Login required" dialog and nothing is viewed or deleted. Behind that, `docHistoryAllowed()` refuses an entry that is not in the current account's list. An unknown / non-integer index does nothing (it used to throw).
* **Stored only while signed in.** New results go through `addDocHistory()` and deletions through `removeDocHistory()` (both in `state/store.js`); without an account session they keep and store nothing.
* **Bound to the account without storing who it is.** The record is `{v:1, s:<random salt>, b:<digest of salt + account id>, items:[...]}`. `b` only lets the page tell "mine" from "someone else's"; the account id, e-mail and name are not stored, and `items` are exactly the already-masked results written before (`sanitizeResultForStorage`), nothing added. The digest is a 53-bit synchronous equality tag (not secrecy; it works without a secure context), computed over a high-entropy random account id.
* **Loaded only after the session is known.** `loadDocHistory()` (called from `main.js`) waits for the one `/auth/me` answer and returns a promise. Guest, signed-out or unreachable session -> nothing restored and the record is deleted. A record in any other format (the old unowned plain array, malformed JSON, a forged or other account's `b`) is **deleted, never read, never migrated**.
* **Reload in the same session keeps it:** the same account's record validates and is restored (user and admin).
* **Cleared on:** logout and guest Exit (`authNav.js` calls `clearDocHistory()` next to `clearFavorites()` / `clearHomeFilters()`); an account change (the first history action or save after the page learns a different account empties the old list first); an expired / guest / unreachable session at the next load.
* **Late responses cannot revive history.** `docHistoryRuntime.generation` is bumped by every load and every clear; a load whose session answer arrives after a logout, Exit, account switch or newer load is discarded, also when the browser refuses to delete the stored record (tested).

## Files changed (relative to the G6.1a tree)
| File | Change |
|---|---|
| `frontend/js/state/store.js` | history section rewritten: `docHistoryRuntime`, `clearDocHistory`, async `loadDocHistory`, `docHistoryAllowed`, `addDocHistory`, `removeDocHistory`; `saveDocHistory` removed (private persist helper) |
| `frontend/js/services/sessionUser.js` | `sessionUserId()` helper (loaded account id or null; used only to bind/compare, never displayed or sent) |
| `frontend/js/features/verifyDocument/flow.js` | `docViewHistory` / `docDeleteHistory` gated and owner-checked; the two result saves use `addDocHistory` |
| `frontend/js/features/authNav.js` | `clearDocHistory()` in both logout and Exit handlers (+ import) |
| `frontend/js/main.js` | `loadDocHistory()` promise; re-render the verify-document view once history loaded |
| `tests/frontend/documentHistoryIsolation.test.js` | new, 19 tests |
| `docs/G6_PHASE1B_CHECKPOINT.md` | new |

Not touched: backend, OCR / extraction, owner verification, CSS, `views.js` (the history page and its "saved on this device" note are unchanged), document data stored, dependencies.

## Tests (actual results)
`fetch` (`/auth/me`) and `localStorage` are in-memory fakes; the real store, flow and session modules run.
| Command | Result |
|---|---|
| `node --test tests/frontend/documentHistoryIsolation.test.js` | 19 run, **19 pass** |
| `node --test` on the 10 relevant suites (isolation, `documentAccessGuard`, `routerGuestGate`, `ownerVerification`, `extraction`, `verificationB1Review`, `verificationRules`, `loginPrompt`, `sessionUser`, `chatLaunchGuard`) | 163 run, **163 pass** |
| `node --test` on all 18 test files that import `state/store`, `authNav`, `sessionUser`, `verifyDocument`, `features/favorites` or `homePrefs` | 209 run, **209 pass** |

Covered: guest / signed-out cannot view; guest / signed-out cannot delete (record and list untouched, nothing written); account A views and deletes its own entries; B cannot see A's (record deleted, not handed over; B's own saves never contain A's data); account change on a live page; logout / Exit clear (function + both handlers checked in source); reload keeps history (user, admin); expired / guest / offline session restores nothing and removes the record; unresolved session shows nothing and the action waits for the answer; late response after logout, after an account switch, and with storage deletion blocked cannot revive history; legacy plain-array, tampered and malformed records deleted; nothing stored without an account; the stored record has exactly the keys `v, s, b, items` and no id / e-mail / name.

Mutation check (scratch copies with one protection removed, each must fail the new tests): no owner binding check -> 3 fail; no generation guard -> 1 fail; `docViewHistory` ungated -> 3 fail; `docDeleteHistory` ungated -> 1 fail; logout does not clear -> 1 fail; stored record gains an owner field -> 1 fail. One redundant inner guard in the private `persistDocHistory` (account check before writing) is not individually detectable because `addDocHistory` already refuses non-account sessions first; it is defence in depth.

## Not run / not verified
Full frontend and backend suites, browser tests (the existing `camera_upload_test.py` still has its unrelated known failure), and a real-browser pass of logout / Exit clearing: only the source and unit level was checked here.

## Known limitations
* The history stays **device-only** (no server history; none was requested). It is wiped at logout, so a user who logs out and in again starts with an empty history.
* An unreachable `/auth/me` is indistinguishable from signed-out, so a flaky network at page load deletes the stored record (fails closed).
* Account changes made in another tab are noticed at the next page load or history action of this tab, not instantly (same page-level session cache as the other account features).
* `views.js` still says results are "saved on this device"; wording was not changed (no UI redesign requested).

## Next (not started)
G6.2 (per the G6 plan); G6.3 stale browser test fix.
