# G6.1a checkpoint — document verification authentication gates

Baseline: `karachi-property-trust-G5-merged-project-v2.zip`. Scope: frontend only. Not started: G6.1b (document history), OCR, backend.

## Problem (from `docs/G6_PHASE1_AUDIT.md`, 4.1)
Only the router (`nav`, `routeFromHash`) checked the session. `openReportEvidenceUpload()` and `openReportEvidenceCamera()` set the view directly, and the wizard, camera and file actions had no check, so a guest calling them directly (devtools, an injected `data-onclick`) reached the upload and camera screens without the login dialog.

## Change
New `frontend/js/features/verifyDocument/access.js` with `gateThen(retry)`. Each action below now starts with
`if(!isAccountSession()) return gateThen(()=>sameAction(sameArgs));`

* **Loaded registered user or admin:** the check is synchronous and passes straight through; behaviour is unchanged.
* **Guest, signed-out, `/auth/me` unreachable, or session not yet loaded:** the action waits for the one existing session answer (`loadSessionUser`). Only an account re-runs it; every other outcome shows the existing shared "Login required" dialog (`showLoginRequired`, an open dialog is reused) and the action never runs. It fails closed.
* Nothing runs first: no `getUserMedia`, no `FileReader`, no sample download, no state change, no view change.

Gated actions:

| File | Functions |
|---|---|
| `flow.js` | `openVerifyDocument`, `openReportEvidenceUpload`, `openReportEvidenceCamera`, `docGoStep`, `docPickMethod`, `docPickAutoType`, `docPickType`, `docHandleFile`, `docStartSample`, `docStartManualCheck`, `startAutomaticVerification` |
| `camera.js` | `startDocumentCamera`, `switchDocumentCamera`, `captureDocumentFrame`, `docHandleCameraCapture`, `useCapturedDocument` |

`docGoStep` is gated because it is what renders the screens that contain the file inputs and the camera controls. Mapping to the request: (1) `openReportEvidenceUpload`; (2) `openReportEvidenceCamera`; (3) `startDocumentCamera`, `switchDocumentCamera`, `captureDocumentFrame`; (4) `docHandleFile`, `docHandleCameraCapture` and `docGoStep` (the file-input screens); (5) `docPickMethod('manual')`, `docPickType`, `docStartManualCheck`; (6) `startAutomaticVerification`, `useCapturedDocument`, `docStartSample`.

Deliberately not gated: `stopDocumentCamera` and `closeDocumentCamera` (they only release the camera), `retakeDocumentCapture` (it calls the gated `startDocumentCamera`), `docSetField`, `docRemoveFile` (local form state only), `finishOcr*` (internal, only reachable after a gated start), and `docViewHistory` / `docDeleteHistory` / history storage (G6.1b by instruction).

`frontend/js/features/ownerVerification.js` was inspected and left unchanged: its view is router-gated, its only protected operation is the server call to `POST /api/v1/verification/check`, which already returns 401/403 to anonymous callers and guests (backend untouched), and a direct call by a guest only produces the existing error message. No private data is involved on the client.

## Tests
New `tests/frontend/documentAccessGuard.test.js` (10 tests). `fetch`, `navigator.mediaDevices.getUserMedia` and `FileReader` are spies.
* Signed-out, guest and "session request fails": all 19 action calls made directly are refused with exactly one login dialog, zero camera requests, zero file reads, no request other than `/auth/me`, no view or wizard change.
* The same actions through the registered `ACTIONS` table (an injected `data-onclick`) are refused for a guest.
* An unresolved session authorizes nothing: no dialog, camera request or file read before the answer; a guest answer then gives the dialog.
* User and admin: evidence screens, camera request, file read, manual check all work; with an unloaded session the action waits, then runs once.
* Source guard: each listed function begins with the check.
* Mutation check (scratch copy with the guard lines removed): 8 of 10 fail, so the tests do detect a missing guard.

### Actual results (run in this phase)
| Command | Result |
|---|---|
| `node --test tests/frontend/documentAccessGuard.test.js` | 10 run, **10 pass** |
| Relevant suites: `documentAccessGuard`, `routerGuestGate`, `ownerVerification`, `extraction`, `verificationB1Review`, `verificationRules`, `loginPrompt`, `sessionUser`, `chatLaunchGuard` | 144 run, **144 pass**, 0 fail |

Not run (by instruction): the full suites, backend tests, browser tests. `tests/browser/camera_upload_test.py` still fails for the unrelated reason recorded in the G6.1 audit (its guest entry) and was not touched; the real-browser behaviour of the new guards was therefore not re-checked in this phase.

## Files changed
* `frontend/js/features/verifyDocument/access.js` (new)
* `frontend/js/features/verifyDocument/flow.js` (guards + 2 imports)
* `frontend/js/features/verifyDocument/camera.js` (guards + 2 imports)
* `tests/frontend/documentAccessGuard.test.js` (new)
* `docs/G6_PHASE1A_CHECKPOINT.md` (new)

No backend, CSS, localStorage, document history, OCR/extraction, owner API or dependency change.

## Known limitations
* The dialog has no return path (`next`) for these actions; after login the user starts again.
* The check relies on the session cached for the page; if it expires mid-flow, the next gated action re-checks only after `resetSessionUser()` (as for the chat). Server data is not involved in document verification, so nothing private is exposed.

## Next (not started)
G6.1b: document history isolation (`kpt_doc_history`).
