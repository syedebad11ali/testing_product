# G6.1d checkpoint - document upload known issue updated (documentation only)

Baseline: the G6.1c working tree (`/home/claude/g6/work/kpt` before this step; snapshot `/home/claude/g6/b1c`). No application code and no test was changed. No test suite was run. Not started: G6.2.

## Changes
| File | Change |
|---|---|
| `docs/KNOWN_ISSUES.md` | The obsolete item "`camera_upload_test.py` does not cover file upload" (in the "0. Consolidation notes" list) is replaced by a **RESOLVED (G6.1c)** entry. |
| `docs/G6_PHASE1_AUDIT.md` | Status row in the summary table changed to "RESOLVED in G6.1c"; a "Status update (G6.1c)" paragraph added at the end of section 5. The original diagnosis text is kept as history. **This file was not in the G6.1c working tree** (it came with the uploaded G6.1 documents), so it is added to `docs/` with these two edits; everything else in it is the uploaded text unchanged. |
| `docs/G6_PHASE1D_CHECKPOINT.md` | New. |

## What the updated entries record
- The browser test now enters as a registered account (`enter_as_user`) and still checks that a guest gets the login dialog and no evidence buttons.
- It tests camera capture (live fake camera, capture, use photo).
- It runs four actual upload cases through the real `input#docfile` after choosing a document type: unsupported `.txt`, 1x1 PNG refused as unreadable, readable PNG, PDF.
- A missing upload control or an expected message makes the test fail (the silent `if files.count():` skip is gone).
- **OCR and PDF text reading remain unverified**: the Tesseract.js / PDF.js CDN requests are blocked in the test, so it only proves the graceful failure messages ("The OCR engine could not be loaded", "PDF reader could not be loaded"). Nothing claims real OCR works.

## Verification
Documentation only: the patch contains `docs/KNOWN_ISSUES.md`, `docs/G6_PHASE1_AUDIT.md` (new file) and this checkpoint; it was dry-run applied to the G6.1c tree without errors. No other file differs from the G6.1c tree.
