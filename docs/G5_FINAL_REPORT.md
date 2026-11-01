# G5 final report - account-owned favorites and preferences (merged project)

**Deliverable (v2):** `karachi-property-trust-G5-merged-project-v2.zip` (v1 `karachi-property-trust-G5-merged-project.zip` had one stale browser test, corrected below; see `docs/G5_FINAL_CORRECTION_CHECKPOINT.md`).
**Previous deliverable:** `karachi-property-trust-G5-merged-project.zip` (single `kpt/` root, complete runnable application).
**Baseline:** `karachi-property-trust-G5_3c.zip` (it already contained G5.1, G5.2, G5.3a, G5.3b, G5.3c; checked: the `g5-phase3c.patch` reverse-applies cleanly to it and its three phase-3 checkpoints are byte-identical to the uploaded ones, so nothing was applied twice).
**Merged on top of it:** G5.4a (browser regression test + CI registration), G5.4b (stale favorites test expectation), the G5 initial audit and phase 4a/4b checkpoints in `docs/`, and corrected `HANDOFF.md` / `work.md` / `CHANGELOG.md` (they still said "G5 not started"). The unfinished G4 working directory and anything experimental were NOT included. Nothing was pushed or deployed.

## 1. What is in the project

| Phase | Change | Main files |
| --- | --- | --- |
| G5.1 | Saving a favorite needs a registered account; guests and signed-out visitors get the login dialog | `frontend/js/features/home.js` (`toggleSave`), `tests/frontend/favoritesAuthGate.test.js` |
| G5.2 | Favorites stored on the account via `GET|PUT /auth/prefs`; optional `remove.saved`; 409 `saved_limit` instead of silent eviction; loaded after the session resolves, cleared on logout / account change; legacy browser key deleted, never migrated | `backend/services/prefs.py` (`apply_update`), `backend/api/account.py`, `frontend/js/features/favorites.js`, `frontend/js/services/favoritesApi.js`, `frontend/js/services/accountApi.js`, `frontend/js/features/authNav.js`, `frontend/js/main.js`, `frontend/js/state/store.js`, `tests/frontend/favoritesServer.test.js`, `tests/backend/test_prefs_saved.py` |
| G5.3a | Guests never persist home filters | `frontend/js/features/homePrefs.js`, `frontend/js/services/sessionUser.js` (`isAccountSession`) |
| G5.3b | Filters are not restored for guests / signed-out visitors; cleared on logout | `homePrefs.js` (`loadHomeFilters`, `clearHomeFilters`), `authNav.js`, `main.js` |
| G5.3c | Filters (area / type / sort) live on the ACCOUNT, no longer in the shared `kpt_prefs` cookie; `remove.fields` can clear them | `backend/services/prefs.py` (`CLEARABLE_FIELDS`), `homePrefs.js`, `accountApi.js`, `tests/backend/test_prefs_filters.py`, `tests/frontend/homePrefs.test.js` |
| G5.4a | Browser regression: guest, A, reload, B in the same browser, back to A (23 checks); registered in CI (required by `test_ci_config`) | `tests/browser/g5_account_data_test.py`, `.github/workflows/ci.yml` |
| G5.4b | Dark-heart expectation corrected to the existing CSS (`0.5px #011425`) | `tests/frontend/favorites.test.js` (line 87) |

Docs: `docs/G5_INITIAL_AUDIT.md`, `docs/G5_PHASE1_CHECKPOINT.md` ... `G5_PHASE4B_CHECKPOINT.md`, this report (`G5_FINAL_REPORT.md` and `docs/G5_FINAL_REPORT.md`), `HANDOFF.md`, `work.md`, `CHANGELOG.md`. Database migrations, assets, data, configuration and the rest of the architecture are unchanged from the baseline (no new migration in G5).

## 2. Actual test results (run 2026-10-31 in a scratch copy of the merged tree; Node 22, Python 3.12, Playwright Chromium, no AI credentials)

| Suite | Result |
| --- | --- |
| Frontend: `node --test "tests/frontend/*.test.js"` | 361 run, **361 pass**, 0 fail (includes `favorites` 3/3, `favoritesAuthGate` 8/8, `favoritesServer` 15/15, `homePrefs`) |
| Backend: `python -m unittest discover -s tests/backend -t .` | 365 run, 364 pass, **1 error**: `test_admin_totp` cannot be imported (`pyotp` not installed) |
| Browser: the 25 tests CI registers (v1 run, history) | 21 pass, 4 fail (details below). **v2 correction:** `prefs_test` now passes (see section 2a); the other 3 failures are unchanged and were NOT re-run in v2 |
| In the fresh extraction of the ZIP | frontend 361/361; `test_ci_config` + `test_prefs_saved` + `test_prefs_filters` + `test_cookies` 55/55; `g5_account_data_test` OK |

Browser tests were run in parallel batches of 5 to 8; four tests (`login_test`, `smoke`, `guest_entry_failures_test`, `g4_widget_test`) timed out under that load and **passed when re-run alone** (9 s, 11 s, 3 s, 17 s). Passed on first run: csp, messaging, cookies, listings, listing_lifecycle, a11y_basics, login_busy, google_button_responsive, property_images, featured, signup_single_click, developer_login, guest_entry, g3_integration, g4_chatbot, widget_auth, g5_account_data.

### The 4 failing browser tests (as found in v1; `prefs_test` fixed in v2, see 2a)

| Test | Cause | New in G5? |
| --- | --- | --- |
| `prefs_test` | **FIXED IN v2.** Was a stale test. It enters as a GUEST, picks type/sort, reloads and expects them to be restored from the cookie when Preferences consent is given (`('House','high')`, got `('', 'newest')`). G5.3a-c deliberately made guests never persist or restore filters and moved registered users' filters to the account. The test still asserts the old consent-gated cookie behavior. It also fails on the untouched G5.3c archive. | Yes: caused by approved G5.3 design, not by G5.4a/4b |
| `admin_totp_test` | `ModuleNotFoundError: pyotp` (environment) | No |
| `camera_upload_test` | Timeout in an account-only verification step | No (fails identically on the G5.3c archive; recorded since G3/G4) |
| `creators_test` | "names and initial avatars are shown" | No (same; recorded since G3/G4) |

### 2a. v2 correction (actual results, run in a fresh extraction of the v1 ZIP plus the one test change)

| Test | Result |
| --- | --- |
| `python tests/browser/prefs_test.py` | **prefs_test OK** |
| `python tests/browser/g5_account_data_test.py` | **OK** (all PASS lines, Account A / B isolation) |
| `python -m unittest tests.backend.test_ci_config` | 6 run, **OK** |

`prefs_test.py` now asserts the approved behavior, for both Preferences choices ("all" and "reject"): a guest's type/sort change filters the visible cards immediately; after reload the filters are NOT restored (`("", "newest")`); `kpt_prefs` never contains `price_desc`, `house`, `ptype`, `sort` or `area`; with "reject" no `kpt_prefs` cookie exists. The tampered-cookie check (script-tag `ptype`, bogus `sort`) is unchanged. No application code, CSS, favorites, authentication or API file was modified. Other suites were not re-run in v2; the v1 figures above still describe them (frontend 361/361; backend 364 pass + 1 `pyotp` error; browser `admin_totp_test`, `camera_upload_test`, `creators_test` failing as before; some browser tests time out under parallel load and pass alone). Because `prefs_test` was the 8th test of the CI browser loop, CI should now get past it; GitHub CI itself was not run.

## 3. Not run / not verified
Live Google OAuth, PostgreSQL, real OCR/PDF extraction, live AI, TOTP (pyotp missing), bandit, GitHub CI itself. No deployment.

## 4. Known limitations of the G5 design (from the checkpoints)
* Registered users see their favorites and saved filters after `/auth/me` and `GET /auth/prefs` answer (one re-render), not in the first paint.
* Favorites and filters saved before G5 in browser storage or the shared cookie are discarded, not migrated (ownership cannot be determined).
* A failed filter save is silent in the UI (status exposed via `homeFiltersStatus()`).
* Two devices on one account: last write wins per save; no live cross-device refresh.
* A request already sent at logout cannot be cancelled; it lands on the account it was sent for.
* "Largest Property" sort has no stored code and is not remembered.
* `/auth/prefs` was not changed to refuse guest sessions server-side (guests never call it).
* Saved limit is 30 (409 `saved_limit`).

## 5. Recommended next steps
1. (Done in v2) `prefs_test.py` updated to the G5 design.
2. Decide on `camera_upload_test`, `creators_test` (pre-existing) and install `pyotp` in CI/dev.
3. Then continue with the next roadmap item (not started).

## 6. Files delivered
`karachi-property-trust-G5-merged-project-v2.zip`, `G5_FINAL_REPORT.md`, `G5_FINAL_CORRECTION_CHECKPOINT.md`, `g5-final-correction.patch` (v1 merged tree -> v2). `g5-consolidated.patch` (G5.3c baseline -> v1) is unchanged.
