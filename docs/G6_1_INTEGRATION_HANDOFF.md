# G6.1 integration handoff

This tree = `karachi-property-trust-G5-merged-project-v2.zip` (SHA-256 `6027ee343cc151fa56d71430dd4715dc97bf20f7e558c1e432587b3d3c01c210`, untouched) + the four G6.1 patches from `KPT-G6-WORK-TO-DATE-v2.zip`, applied once each in this order, no rejects:

| Order | Patch | Origin |
|---|---|---|
| 1 | `g6-phase1a.patch` - document-verification authentication gates | original |
| 2 | `g6-phase1b.patch` - account-isolated document history | original |
| 3 | `g6-phase1c-reconstructed.patch` - registered-user camera/upload browser test | **RECONSTRUCTED** |
| 4 | `g6-phase1d.patch` - known-issues / audit documentation | original |

## G6.1c is a reconstruction, not the original patch
The original `g6-phase1c.patch` was lost and has not been recovered. `tests/browser/camera_upload_test.py` in this tree was rewritten from `docs/G6_PHASE1C_CHECKPOINT.md` (the original description) and the approved behaviour list. It may differ from the lost original in selectors, helper names, the readable test image and printed lines. Details: `docs/G6_PHASE1C_RECONSTRUCTION_CHECKPOINT.md`. Do not describe it as the original. If the original turns up, diff it against this file. Only the test file is affected: no application code depends on it.

## What changed versus G5 v2 (15 files from the patches, plus the documentation additions listed below; nothing else)
- New: `frontend/js/features/verifyDocument/access.js`, `tests/frontend/documentAccessGuard.test.js`, `tests/frontend/documentHistoryIsolation.test.js`, `docs/G6_PHASE1A_CHECKPOINT.md`, `docs/G6_PHASE1B_CHECKPOINT.md`, `docs/G6_PHASE1D_CHECKPOINT.md`, `docs/G6_PHASE1_AUDIT.md`.
- Changed: `frontend/js/features/verifyDocument/flow.js`, `.../camera.js`, `frontend/js/features/authNav.js`, `frontend/js/main.js`, `frontend/js/services/sessionUser.js`, `frontend/js/state/store.js`, `tests/browser/camera_upload_test.py`, `docs/KNOWN_ISSUES.md`.
- Added in the integration step (documentation only): this file, `docs/G6_PHASE1C_CHECKPOINT.md`, `docs/G6_PHASE1C_RECONSTRUCTION_CHECKPOINT.md`, pointers in `HANDOFF.md` and `CHANGELOG.md`.
- No backend, CSS, dependency, CI or configuration change.

## Integration-time test results (actually run on this tree, offline sandbox)
| Command | Result |
|---|---|
| `node --test tests/frontend/documentAccessGuard.test.js tests/frontend/documentHistoryIsolation.test.js` | 29 run, 29 pass |
| `node --test` on 8 regression suites (`routerGuestGate`, `ownerVerification`, `extraction`, `verificationB1Review`, `verificationRules`, `loginPrompt`, `sessionUser`, `chatLaunchGuard`) | 134 run, 134 pass |
| all 10 files together | 163 run, 163 pass |
| `python -m unittest tests.backend.test_ci_config` | Ran 6, OK |
| `python tests/browser/camera_upload_test.py` (Chromium, fake camera) | OK (`camera_upload_test OK`) |

NOT run: the full frontend suite (`npm test`), the backend suite, the other browser tests. Earlier G5 / G6 checkpoint figures are historical and were not rerun.

## Limitations (unchanged from the G6.1 checkpoints)
- OCR (Tesseract.js) and PDF.js reading remain unverified; the libraries are not vendored. The browser test blocks the CDN and proves only the graceful-failure messages.
- Fake camera in Chromium only; no real phone camera.
- Document history is device-only, wiped at logout; an unreachable `/auth/me` deletes the stored record.
- Not started: G6.2 and later (see `docs/G6_PHASE1_AUDIT.md` section 7; its G6.2/G6.3 labels predate the 1a-1d split).
