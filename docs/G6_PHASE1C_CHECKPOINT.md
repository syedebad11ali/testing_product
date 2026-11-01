# G6.1c checkpoint - document verification browser test fixed

Baseline: `karachi-property-trust-G5-merged-project-v2.zip` + `g6-phase1a.patch` + `g6-phase1b.patch` (applied in that order, no rejects). Working copy: `/home/claude/g6/work/kpt`; G6.1b snapshot used for the patch: `/home/claude/g6/b1b`. Not started: G6.2.

## Problem
`tests/browser/camera_upload_test.py` entered as a guest. Document / evidence views are account-only (G3b2a, G6.1a), so the guest gets the "Login required" dialog, the evidence buttons never render and the test timed out. Its upload half was also silently skipped (`if files.count():` with `file inputs present: 0`), because the file input only appears after a document type is chosen.

## Change (one file: `tests/browser/camera_upload_test.py`; application and every restriction untouched)
- Registered user via the existing helper `enter_as_user` (real sign-up form, `tests/browser/support/session_entry.py`, unchanged).
- Guest check kept and made explicit: a guest clicking Report A Scam gets the login dialog and no `openReportEvidenceCamera` / `openReportEvidenceUpload` button (proves nothing was weakened).
- Camera, real capture: Report A Scam -> Open Camera -> Open Live Camera -> fake camera delivers frames -> capture -> use photo -> the app says "The OCR engine could not be loaded".
- Upload, real file input, no silent skip: Report A Scam -> Upload Evidence -> choose a document type -> `input#docfile` must exist (exactly one, asserted) ->
  - `evidence.txt` -> "Unsupported file. Please upload a PDF, JPG or PNG.";
  - 1x1 PNG -> the clear "too dark, too bright, blank, or too low-resolution" refusal;
  - readable 240x160 PNG (built with the standard library) -> "The OCR engine could not be loaded";
  - `evidence.pdf` -> "PDF reader could not be loaded".
- Graceful OCR failure is deterministic: requests to `https://cdn.jsdelivr.net/**` (Tesseract.js, PDF.js) are aborted, so the result is the same offline or online. Every expected message is waited for with `wait_for_text`; a missing control or message fails the test.
- Unchanged checks: no `securitypolicyviolation`, no uncaught page errors.

## Result (actual)
- `python tests/browser/camera_upload_test.py` -> exit 0:
```
guest refused: login dialog, no evidence buttons
camera: frame captured and used -> The OCR engine could not be loaded
upload: unsupported file refused
upload: unreadable image refused with a clear message
upload: readable PNG accepted -> The OCR engine could not be loaded
upload: PDF accepted -> PDF reader could not be loaded
camera_upload_test OK
```
  Run 4 times on the final content: OK each time.
- The G6.1b version of the test on the same tree still fails (timeout waiting for `openReportEvidenceCamera`), so the failure was the test, not the application.
- Not run (by instruction): the full suite, other browser tests, backend tests. `tests.backend.test_ci_config` (Ran 6, OK): `camera_upload_test` is already in the CI browser loop, so no CI change was needed.

## Limitations
- It does not prove OCR or PDF reading work (needs the libraries; vendoring is still open, see the G6 audit section 6).
- Chromium with a fake camera only; no real phone camera.
- The wording assertions follow `services/ocr.js` and `views.js`; changing that text requires updating the test.
- `docs/KNOWN_ISSUES.md` item 7 (the skipped upload half) is now obsolete; it was not edited here to keep the patch to one file.
