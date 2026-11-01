# G6.2a-3 Part B checkpoint - owner card hidden from guests (S4, T2, T3)

**RECONSTRUCTED, not recovered** (see `G6_PHASE2A3A_CHECKPOINT.md` for the parent state and provenance).

## Behaviour
On the property DETAIL page the owner card (initials, name, `ownerRole`) is shown only when `isAccountSession()` is exactly `true` (loaded registered user or admin). Guest, signed-out, session still loading and failed lookup (fail closed) get a neutral card with the same `owner-card` classes: "Listed by <seller type>", "Log in or sign up to see the owner details." and a `Log in / Sign up` button (`showOwnerLogin`, registered in the delegated `ACTIONS` table) that opens the shared "Login required" dialog (no navigation, no request, never stacked). Title, price, area, plot, size, seller type, status and "Verify This Property" are unchanged. `main.js` re-renders the detail view once the cached session answer arrives, so an account never stays on the neutral card. No CSS, backend, extractor or API change. **This is display-only protection: `properties.js` is still a public file (now holding synthetic values only).**

## Files
`frontend/js/features/property.js` (`ownerCardHtml`, `showOwnerLogin`, `renderDetail`), `frontend/js/ui/actions.js` (+1 import, +1 entry), `frontend/js/main.js` (one hook, one import), `tests/frontend/propertyOwnerVisibility.test.js` (new, 7 tests), `tests/browser/guest_owner_privacy_test.py` (new, 22 checks), `.github/workflows/ci.yml` (registered), `tests/browser/camera_upload_test.py` (one token: `write_text(..., encoding="utf-8")`, see below).

## Tests of this part
* `propertyOwnerVisibility` 7/7: all 8 properties x signed-out / guest / failed lookup / still loading show no name, initials, role line, other owner or CNIC-shaped value; public details intact; user and admin see the card; loading -> loaded flips the card; `ownerCardHtml` fails closed for 13 non-`true` values; the button uses the shared dialog.
* Browser (real backend) 22/22: the served `properties.js` holds only `00000-` CNICs and `Demo ...` owners; guest p1-p8 neutral cards and no CNIC in the DOM; button opens the dialog and the guest session survives; registered user sees `Demo Person Alpha` / initials `DP`, also after a reload; no console or CSP error.
* Mutation (scratch copies): owner always shown -> 5 fail; truthy instead of `=== true` -> 1 fail; detail passes `true` -> 4 fail; action not registered -> 1 fail; neutral card leaks the name -> 3 fail; button navigates -> 1 fail. **6/6 caught.** Negative control: the browser test against the pre-S4 tree fails (served data, all 8 guest pages).

## Baseline defect fixed along the way
`tests.backend.test_text_encoding` was failing in the G6.1 baseline itself: `tests/browser/camera_upload_test.py:120` called `write_text` without an encoding. One-token fix; the browser test still passes.

## Final results
| Check | Result (this environment, run for this archive) |
|---|---|
| `npm test` | **413 run, 413 pass, 0 fail, 0 skipped** (baseline G6.1: 397; +9 `syntheticOwnerData`, +7 `propertyOwnerVisibility`) |
| `node --test tests/frontend/syntheticOwnerData.test.js` | 9 run, 9 pass |
| `node --test tests/frontend/propertyOwnerVisibility.test.js` | 7 run, 7 pass |
| `node --test tests/frontend/extraction.test.js tests/frontend/verificationB1Review.test.js` | 49 run (34 + 15), 49 pass; per-test names, order and status identical to the G6.1 + 2a-1 tree |
| `python tests/browser/guest_owner_privacy_test.py` (real local backend) | 22 passed, 0 failed |
| `python tests/browser/csp_test.py` | exit 0, OK |
| `python tests/browser/a11y_basics_test.py` | exit 0, OK |
| `python tests/browser/camera_upload_test.py` | exit 0, OK |
| `node scripts/manifest-report.mjs` | output byte-identical to the baseline: OCR lane 18/29 anchored, PDF lane 28/28, "verified although the manifest expects otherwise = 0" |
| `python -m unittest tests.backend.test_ci_config` | Ran 6, OK |
| full backend `python -m unittest discover -s tests/backend -t .` | **Ran 365, 0 failures, 1 error**: `tests.backend.test_admin_totp` cannot import `pyotp` (not installed here; environment, not an application defect; the TOTP tests did not run) |

**Not run / not verified:** the other browser tests (messaging, cookies, login, smoke, listings, prefs, admin_totp, google_button, property_images, ...); live OCR and PDF.js reading (the libraries are not vendored and there is no network, so only the offline "could not be loaded" path was exercised); PostgreSQL; live Google sign-in; a real WinRAR open of the ZIP (standard ZIP integrity only).
