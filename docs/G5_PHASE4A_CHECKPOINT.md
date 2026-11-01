# G5.4a checkpoint - account data browser regression test

**Source:** `karachi-property-trust-G5_3c.zip` (original preserved), extracted to a separate working directory; a second pristine extraction was kept as the patch baseline.
**Scope:** one new browser test, nothing else. No application code was changed.

## Files changed

| File | Change |
| --- | --- |
| `tests/browser/g5_account_data_test.py` | New. The 8-step account-data sequence in one real browser. |
| `.github/workflows/ci.yml` | One word added to the browser loop (`g5_account_data_test`). |

CI registration **was necessary**: `tests/backend/test_ci_config.py` fails with "browser test exists but CI never runs it" for any test in `tests/browser/` that the workflow does not list. Before the edit that test failed (1 failure); after it, 6/6 pass.

## What the test does

Real backend (`python -m backend.app`, throwaway SQLite database, offline engine, no AI keys), Playwright Chromium, **one browser context for the whole run**, real sign-up form, real logout button, real login form, real `/api/v1/auth/prefs` traffic. No route stubbing, no mocked responses. Filters are driven through the actual controls (area chip, type `<select>`, sort `<select>`), favorites through the actual heart button.

| Step | Checks |
| --- | --- |
| 1 Guest changes filters | Filters apply on screen; **zero** `/auth/prefs` requests; nothing in the `kpt_prefs` cookie; back to defaults after reload |
| 2 Guest tries to save | Login dialog appears, heart stays off, zero preferences requests |
| 3 Account A | Fresh account starts empty; saves one property and sets area/type/sort; the server copy holds exactly that (polled through the real API) |
| 4 Reload | A's area, type and sort restored; A's property still hearted |
| 5 Log out | Session cookie gone; A's filters not in the shared cookie. Account B is then created in the same browser |
| 6 B sees nothing of A | No hearts, default filters, server copy for B is `{}`, still empty after reload |
| 7 B saves other data | Different property and different filters; B's server copy holds only B's property |
| 8 Back to A (real login form) | A's filters restored; A's property hearted, B's absent; server copy equals A's original values; neither account's filters ever appeared in the shared cookie |

23 PASS checks in the final version.

## Actual results

| Command (from the project root) | Result |
| --- | --- |
| `python tests/browser/g5_account_data_test.py` (final version, run 1) | `g5_account_data_test: OK`, 23 PASS, 0 FAIL |
| same (final version, run 2, stability) | `g5_account_data_test: OK`, 23 PASS, 0 FAIL |
| `python -W ignore -m unittest tests.backend.test_ci_config` | Ran 6, OK (after registration) |
| Mutation: guest gate removed from `toggleSave` (temporary, reverted) | Test fails at step 2 (login dialog never appears) |
| Mutation: `restoreFilters` returns nothing (temporary, reverted) | Test fails at step 4 ("filters are restored") |

After both mutations the `frontend/` tree was compared with the baseline: identical.

### Failures seen while developing the test (all in the test, none in the app)
1. First run: after a reload, A's restored area+type combination matched no listing, so the test's wait for a property card timed out. Fixed by waiting for the grid.
2. Second run: two `.auth-logout` buttons exist (header and drawer); the first is hidden at desktop width. Fixed by clicking the visible one.
3. Third run: step 8 cleared A's filters in the UI (only to look at every card's heart) and then compared the server copy, so it failed on the test's own change. Fixed by checking the server copy first.

No application defect was found, so no application file was touched.

## Not run (as instructed)
The full frontend and backend suites, the other browser tests, bandit. Only the new test, two mutation runs and `test_ci_config` were executed.

## Environment
Python 3.12, Node 22, Playwright Chromium works in this sandbox (no blocker). The test needs no network and no credentials.

## Observations (not defects, not changed)
* "Largest Property" sort has no stored code, so it is not remembered (documented in G5.3c); the test uses "Price: Low to High" and "Price: High to Low".
* A saved area + type pair can match zero listings; the page then shows the empty-state message after a reload. This is the expected consequence of the combined filter, not a restore failure.
* The test uses sign-up to create B and the real login form to return to A; it does not exercise log-in as B.

## Patch
`g5-phase4a.patch` (2 files, `-p1`, relative to the project root). Verified: applies cleanly to a fresh extraction of `karachi-property-trust-G5_3c.zip` and reproduces the working tree byte for byte.

STOP after G5.4a.
