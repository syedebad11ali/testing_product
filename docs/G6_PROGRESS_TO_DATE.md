# KPT G6 work to date (G6.1a - G6.1d, G6.2a audit, G6.2a-1) - report v3

Baseline: `karachi-property-trust-G5-merged-project-v2.zip`, SHA-256 `6027ee343cc151fa56d71430dd4715dc97bf20f7e558c1e432587b3d3c01c210`. Unmodified and not included. This bundle holds patches and documents only; there is no merged G5+G6 ZIP. G6.2b has not been started.

## Status of the four patches
| Phase | File | Status |
|---|---|---|
| G6.1a | `g6-phase1a.patch` | Original |
| G6.1b | `g6-phase1b.patch` | Original |
| G6.1c | `g6-phase1c-reconstructed.patch` | **RECONSTRUCTED, not the original** (original lost; see `G6_PHASE1C_RECONSTRUCTION_CHECKPOINT.md`) |
| G6.1d | `g6-phase1d.patch` | Original |

## Patch order and parent states (dependent; do not claim independence)
| Step | Patch | Parent state |
|---|---|---|
| 1 | `g6-phase1a.patch` | G5 v2 |
| 2 | `g6-phase1b.patch` | G5 v2 + 1a |
| 3 | `g6-phase1c-reconstructed.patch` | G5 v2 + 1a + 1b |
| 4 | `g6-phase1d.patch` | G5 v2 + 1a + 1b + 1c |

Apply from the `kpt/` directory with `patch -p1 < <patch>`, in this order, each once. Packaging check: all four dry-ran and applied cleanly in this order starting from a fresh G5 v2 extraction (no rejects or .orig files), and a second application of each was refused. Files changed in total: 15 `docs/G6_PHASE1A_CHECKPOINT.md`, `docs/G6_PHASE1B_CHECKPOINT.md`, `docs/G6_PHASE1D_CHECKPOINT.md`, `docs/G6_PHASE1_AUDIT.md`, `docs/KNOWN_ISSUES.md`, `frontend/js/features/authNav.js`, `frontend/js/features/verifyDocument/access.js` (new), `.../camera.js`, `.../flow.js`, `frontend/js/main.js`, `frontend/js/services/sessionUser.js`, `frontend/js/state/store.js`, `tests/browser/camera_upload_test.py`, `tests/frontend/documentAccessGuard.test.js` (new), `tests/frontend/documentHistoryIsolation.test.js` (new).

## Update: G6.2a audit and G6.2a-1 (after the G6.1 integrated archive)
New baseline: `karachi-property-trust-G6_1-integrated.zip`, SHA-256 `ef8f7052bcdb1af350827db6082cbfcb9d38a224e0799a179716f74911291a59`. Unmodified.

| Step | File | Status |
|---|---|---|
| G6.2a | `docs/G6_PHASE2A_AUDIT.md` | Audit only, read-only; unchanged. Found defects D1-D7. |
| G6.2a-1 | `g6-phase2a-1.patch`, `G6_PHASE2A1_CHECKPOINT.md` | **Done**: fixes audit D1 only. Applies to the G6.1 integrated tree (3 files: `property.js`, `actions.js`, new `tests/frontend/propertyUploadHonesty.test.js`). |

**Actual change (G6.2a-1):** the property page's "Upload document to check" no longer exists. It read no file and showed a fixed "Reference match: Yes" after 1.5 s. It is replaced by an honest notice (per-property file checking is not available there; no file is read or checked) with a button to the existing login-gated document check. `handleDocUpload` is deleted and removed from the action table. The wizard was not reused for the comparison because it has no property context and changing that would alter OCR comparison rules.

**Test results (actual):** new test 7/7; 15 relevant frontend suites 145/145; the new test fails 3 of 7 against the original code (the 4 access/robustness tests pass on both); `camera_upload_test.py`, `csp_test.py`, `a11y_basics_test.py` all OK; `test_ci_config` 6 OK; a throwaway real-browser probe confirmed the page. `g3_integration_test.py` **fails at A22 on the untouched baseline too** (pre-existing, not investigated). Full suites were not run. Details: `G6_PHASE2A1_CHECKPOINT.md`.

**Provenance note:** the three changed files were already in the working tree when verification began; they were reviewed, mutation-checked and packaged, not authored in a visible command.

**Still open from the audit (not started, separate decisions):** D2 hard-coded "Verified" badge; D3/D4 OCR comparison rules (false `verified` on a dropped area digit; OCR doubt shown as `not_verified`); D5 owner/CNIC data in public JavaScript; D6 owner-name rate-limit scope, fail-open store and honorific stripping; D7 "✓ Saved" that saves nothing and missing disclaimers on early-exit results. G6.2b not started.

## Completed work
- **G6.1a** - Authentication gates on every document-verification action (new `verifyDocument/access.js`; guards in `flow.js`, `camera.js`). Fails closed. Frontend only.
- **G6.1b** - Document-history account isolation (`state/store.js`, `sessionUser.js`, `flow.js`, `authNav.js`, `main.js`): history only for account sessions, bound to the account without storing its id, cleared on logout/Exit/account change, legacy records deleted.
- **G6.1c (reconstructed)** - `tests/browser/camera_upload_test.py`: registered user, guest refusal, real camera capture, one real file input, four upload cases, CDN blocked, CSP and page-error checks. Application untouched.
- **G6.1d** - Documentation only: `KNOWN_ISSUES.md` entry marked resolved, `G6_PHASE1_AUDIT.md` status updated (added to `docs/`), checkpoint added.

## Test results
Historical (from the original checkpoints; NOT rerun during packaging):
- G6.1a: `documentAccessGuard.test.js` 10/10; 9 relevant suites 144/144; mutation check 8 of 10 fail with guards removed.
- G6.1b: `documentHistoryIsolation.test.js` 19/19; 10 relevant suites 163/163; 18 store-related files 209/209; mutation checks detected except one documented redundant inner guard.
- G6.1c original: `camera_upload_test.py` exit 0, reported OK on 4 runs; `test_ci_config` 6 OK.
- G6.1d: no tests (documentation only).

Run during the G6.1c reconstruction (this session, actual):
- Reconstructed `camera_upload_test.py`: exit 0, 4 runs OK (3 on the 1a+1b tree, 1 on the full a+b+c+d tree).
- `tests.backend.test_ci_config`: Ran 6, OK.
- Full frontend and backend suites were not run in any G6.1 phase or during packaging (nor in G6.2a-1; see the update section for what was run).

## Limitations
- The G6.1c patch is a reconstruction; it may differ from the lost original in details (see its checkpoint). No mutation check was done on it.
- Live OCR (Tesseract.js) and PDF.js reading remain unverified; libraries are not vendored. The browser test proves only graceful failure messages.
- Chromium with a fake camera only; no real phone camera.
- Document history is device-only and wiped at logout; an unreachable `/auth/me` deletes the stored record.
- The login dialog has no return path after login for these actions.
- Account changes in another tab are noticed at the next load or history action.
- `views.js` still says results are "saved on this device".
- A real-browser check of logout/Exit history clearing was not done.

## Remaining G6 tasks (from `G6_PHASE1_AUDIT.md` section 7; not started)
- Honest wizard wording; new `docs/VERIFICATION.md`; corrections to `privacy.html`, `COOKIES.md`, `API.md`, `HANDOFF.md`, `CHANGELOG.md`; optional injected-control browser case and CI registration.
- Live OCR: vendor and pin Tesseract.js, PDF.js and language data, update the CSP, run manual tests on real documents (separate, blocked).
- Open decisions: manual entry behind login, who vendors OCR libraries, optional per-account rate limit on the owner check.
- The audit's G6.2/G6.3 labels predate the 1a-1d split, so confirm the plan before starting G6.2.


---
## Update 2026-11-01: G6.2a-1 applied, G6.2a-3 RECONSTRUCTED and integrated (report v4)
Baseline `karachi-property-trust-G6_1-integrated.zip` (`ef8f7052...1a59`) + `g6-phase2a-1.patch` (once) + `g6-phase2a-3.patch` (G6.2a-3 only, reconstructed from the approved plan; the previous working tree was lost). Complete integrated archive: `karachi-property-trust-G6-integrated-to-date.zip`.
Status: G6.1a-d done; G6.2a-1 done; G6.2a-3 (S1-S4, T1-T3) done and tested; G6.2b, G6.3, G6.4 not started. Results: `npm test` 413/413; backend 365 run, 0 failures, 1 error (`pyotp` missing); `csp_test`, `a11y_basics_test`, `camera_upload_test` OK; guest owner browser test 22/22; manifest identical. Open: D2, D3/D4, D6, D7, private dataset provenance, live OCR/PDF unverified. See `docs/G6_PHASE2A3_REMEDIATION_COMPLETE.md`.
