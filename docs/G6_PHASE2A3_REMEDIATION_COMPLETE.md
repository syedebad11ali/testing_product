# G6.2a-3 owner-data privacy remediation - completion record (2026-11-01)

**Provenance.** The previous AI session's tree was lost (`/home/claude/work/kpt` absent). Everything here is **reconstructed** from the G6.1 integrated ZIP, `g6-phase2a-1.patch` and the approved plan `G6_PHASE2A3_REMEDIATION_PLAN.md`, and re-tested. Test counts differ from the previous session's report (it reported 12 / 18 / 67 / 427 for the three new tests and the total; this reconstruction has 9 / 7 / 22 / 413) because the tests were rewritten, not recovered; they cover the plan's list, but nobody should assume they are identical.

## Implemented (S1-S4, T1-T3)
1. Synthetic owners and CNICs for p1-p8 (`Demo Person ...` / `Demo Company ...`, `00000-0000101-0` ...). 2. Placeholders in `documentTypes.js` and `property.js`. 3. Test literals in `extraction.test.js` and `verificationB1Review.test.js` replaced without changing any assertion; old/new verification outcomes proven identical (see Part A checkpoint). 4. Owner card hidden from guests / signed-out / unresolved sessions (fail closed). 5. Regression tests: `syntheticOwnerData.test.js`, `propertyOwnerVisibility.test.js`, `guest_owner_privacy_test.py` (in CI).
Details: `G6_PHASE2A3A_CHECKPOINT.md`, `G6_PHASE2A3B_CHECKPOINT.md`.

## Results
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

## What this does NOT solve
* **`frontend/js/data/properties.js` is publicly served.** Hiding the owner card from guests is display-only; the values are now synthetic, so nothing real is exposed there, but a real owner dataset must never be added to that file.
* **Private dataset unchanged:** `backend/datasets/*.csv` (16,000 rows with owner columns), `data-source/*.xlsx` and `notebooks/*.ipynb` are untouched and still travel inside the project archive; their provenance and distribution are a separate owner decision.
* **Older archives** (G4, G5 v2, G6.1 ZIPs) still contain the previous p1-p8 values and the old test literals. If any of those values turn out to be real, those archives need a separate withdrawal decision.
* Documents carrying the old p1-p8 names/CNICs no longer match those records (intended).
* Live OCR / PDF.js reading remain unverified.

## Still open (separate tasks, not part of this work)
D2 hard-coded "Verified" badge; D3/D4 OCR area digit-drop and uncertainty behaviour; D6 owner-name API rate-limiter scope and name-matching weaknesses; D7 the "Saved" message in the property details form that saves nothing. G6.2b, G6.3, G6.4 not started. `docs/G6_PHASE2A_AUDIT.md` (cited by the 2a-1 checkpoint) was not among the supplied files and is not in this archive.
