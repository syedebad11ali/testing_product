# G6.1c RECONSTRUCTION checkpoint

**`g6-phase1c-reconstructed.patch` is a RECONSTRUCTION. It is NOT the original G6.1c patch, which was lost and has not been recovered.**
It was rewritten from `G6_PHASE1C_CHECKPOINT.md` (the original, unchanged, in this bundle) and the approved behaviour list. It is expected to behave the same, but it is not byte-identical to the original and nothing here proves it matches the original code line by line. If the original `g6-phase1c.patch` turns up, prefer it and diff the two.

## What it changes
One file: `tests/browser/camera_upload_test.py` (patch: +101 / -27 lines). No application code, CSS, backend or other test changed.
Parent state: G5 v2 + `g6-phase1a.patch` + `g6-phase1b.patch`. Child state is the parent of `g6-phase1d.patch`.

## Behaviour (as approved)
1. Registered user via the existing `enter_as_user()` (`tests/browser/support/session_entry.py`, unchanged).
2. A guest clicking Report A Scam gets the "Login required" dialog and no `openReportEvidenceCamera` / `openReportEvidenceUpload` button.
3. Camera: Chromium fake camera, frames confirmed, capture, use photo, expected message "The OCR engine could not be loaded".
4. Upload: choose a document type, assert exactly one `input#docfile`.
5. Four uploads through it, each with its exact message: `.txt` -> "Unsupported file. Please upload a PDF, JPG or PNG."; 1x1 PNG -> "too dark, too bright, blank, or too low-resolution"; readable 240x160 PNG (standard-library generated) -> "The OCR engine could not be loaded"; PDF -> "PDF reader could not be loaded".
6. `https://cdn.jsdelivr.net/**` aborted so the library-unavailable messages are deterministic.
7. `securitypolicyviolation` events (guest and user pages) and uncaught page errors still fail the test.
8. No silent skip: every message is waited for by `wait_for_text` (defined in the test file) and a missing control or message raises.

## Differences from the original that may exist
Selector choices, the exact readable-PNG pattern, helper names, printed progress lines and comments were reconstructed and may differ. The expected message wording was taken from the checkpoint and checked against `services/ocr.js` and `features/verifyDocument/flow.js`.

## Results (actually run during this reconstruction, Chromium + Playwright 1.56, offline)
- `python tests/browser/camera_upload_test.py`: exit 0, **4 runs, OK each time** (3 on the G6.1b tree with the new file, 1 on the fully patched a+b+c+d tree). Output ended with `camera_upload_test OK`.
- `python -m unittest tests.backend.test_ci_config`: Ran 6, OK.
- Not done: no mutation check of the new test, no full suite, no other browser tests.

## Limitations
Same as the original checkpoint: it does not prove OCR or PDF reading work; Chromium with a fake camera only; the wording assertions must be updated if the application text changes.
