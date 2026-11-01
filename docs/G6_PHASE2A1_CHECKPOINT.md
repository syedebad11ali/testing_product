# G6.2a-1 checkpoint - the fake property-page document upload is removed

Baseline: `karachi-property-trust-G6_1-integrated.zip` (SHA-256 `ef8f7052bcdb1af350827db6082cbfcb9d38a224e0799a179716f74911291a59`), unmodified. Findings source: `docs/G6_PHASE2A_AUDIT.md` (defect D1), unmodified. Patch: `g6-phase2a-1.patch` (apply from `kpt/` with `patch -p1`, once). Not started: any OCR fix, G6.2b.

## Defect
On the property "Verify This Property" page, "Upload document to check" (`handleDocUpload`) read only the file name, waited 1.5 s and revealed a pre-rendered panel whose "Reference match" was a constant per property (`Yes` unless the property's static status was `issue`). The audit showed `definitely-not-a-property-document.txt` receiving "Reference match: Yes".

## Decision: honest unavailable message, not reuse of the wizard
The existing document wizard cannot do the comparison this control claimed. It has no property context: `verifyAgainstRecords` free-searches all records for the best match, and checking one chosen property would mean changing the comparison rules, which this task excludes. So nothing is faked and nothing is duplicated. The panel now says that checking a document against this specific property is not available on this page, that no file is read or checked here, and offers a button to the existing, login-gated document check (`openVerifyDocument()`), with the "indicative only, not official ownership authentication" wording. No file is read on this page.

## Changes (3 files)
| File | Change |
|---|---|
| `frontend/js/features/property.js` | The file input, label, filename line, "Extracting & checking" spinner and the fixed result panel are replaced by the notice and the "Open document check" button (`id="docnotice-<id>"`). `handleDocUpload` is deleted. |
| `frontend/js/ui/actions.js` | `handleDocUpload` removed from the import and from the action table, so a `data-onchange="handleDocUpload(...)"` injected into the page reaches nothing. |
| `tests/frontend/propertyUploadHonesty.test.js` | New, 7 tests (picked up automatically by `npm test`'s glob). |

No change to: the hard-coded "Verified" badge, owner/CNIC data, the owner-name API or limiter, OCR comparison rules, the database, other pages, CSS or dependencies. `saveManualInfo` (the "✓ Saved" that saves nothing, audit D7) is untouched. The now-unused CSS rules `.auth-result` and `.processing` were left alone on purpose (no styling change).

## Implementation provenance
When verification began, the three files above were already changed in the working tree (modification times 00:16-00:17 UTC, between two of my commands). I did not write them in a command I can see, so I reviewed them line by line against the baseline diff, mutation-checked the test, and validated the patch built from them. Treat the review, not authorship, as the basis for the results below.

## Tests (actual results)
| Check | Result |
|---|---|
| `node --test tests/frontend/propertyUploadHonesty.test.js` | 7 run, **7 pass** |
| 15 relevant frontend suites together (new test, `handlers`, `render`, `reportTargets`, `propertyDisplayStatus`, `routerGuestGate`, `documentAccessGuard`, `documentHistoryIsolation`, `loginPrompt`, `sessionUser`, `strictStyles`, `dataStyle`, `infrastructure`, `assetsPresent`, `portablePaths`, `ownerVerification`) | 145 run, **145 pass** |
| Mutation: new test against the ORIGINAL `property.js` + `actions.js` | tests 1-3 (no file input / no fixed delayed result / no "Reference match") **fail**; 4-7 (access and robustness guards) pass on both, as intended |
| Mutation: fix kept, only a `handleDocUpload` export/timer re-added | test 2 fails |
| `tests/browser/camera_upload_test.py` | exit 0, "camera_upload_test OK" |
| `tests/browser/csp_test.py` | exit 0, OK (no CSP violations; guest "Verify This Property" still shows the login dialog) |
| `tests/browser/a11y_basics_test.py` | exit 0, OK (includes the verify views) |
| `tests.backend.test_ci_config` | Ran 6, OK |
| Throwaway real-browser probe (`g6_2a1_browser_probe.py`, outside the project) as a registered user: detail → Verify This Property | 0 file inputs; no "Reference match" or "Extracting"; notice and indicative-only wording present; 0 network requests and no result panel after 1.8 s; the button opens the document check; 0 CSP violations, 0 page errors. On the original baseline the notice does not exist (probe times out waiting for it). |
| Patch packaging | dry-run and apply clean on a fresh baseline extraction; second application refused; no `.orig`/`.rej`; resulting tree equals the project tree; new test 7/7 there |

## Failure not caused by this change
`tests/browser/g3_integration_test.py` fails at **A22 "verify-document keeps its own destination"** (sign-up from the login dialog does not land on `#verify-document`). The **same failure, same step, occurs on a fresh untouched baseline extraction**, so it is pre-existing and was not investigated or fixed (outside this task; it matches the known "no return path after login" limitation).

## Limitations
- The new tests use the repository's DOM stub, not a browser; the browser evidence is the existing tests plus the one probe, which is not added to the project.
- Not run: the full `npm test`, the full backend suite, the other browser tests. The new test logs a harmless `initFeatured` stub message from the DOM stub.
- Live OCR / PDF reading remain unverified (libraries not vendored), as before.
- A user who wanted a per-property file check no longer has one on this page. The general document check compares against all available records and does not tell the user whether it matched *this* property.
- The "Enter property & owner details" form still shows "✓ Saved" without saving, still pre-fills the owner name, and the hard-coded "Verified" badge is unchanged (separate decisions).

## Files that should remain untouched (unchanged)
`verifyDocument/access.js`, `flow.js`, `camera.js`, `router.js`, `sessionUser.js`, `domain/extraction.js`, `backend/**`, datasets, `docs/G6_PHASE2A_AUDIT.md`.
