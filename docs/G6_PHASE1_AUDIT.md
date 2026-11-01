# G6.1 — Document and Owner Verification Audit

Analysis only. Baseline: `karachi-property-trust-G5-merged-project-v2.zip`, extracted to a scratch directory (`/home/claude/g6/kpt`, 538 files). No application source, test, CSS, dependency or database was changed. Probe scripts lived in `/tmp` and are not part of the project. Nothing was packaged or deployed. G5 was not re-audited.

Status labels: **COMPLETE**, **PARTIAL**, **MISSING**, **BLOCKED**.

## 1. Summary

| # | Requirement | Status | Short finding |
|---|---|---|---|
| 1 | Guests / signed-out cannot begin document verification | **PARTIAL** | Menu and deep-link routes are gated. Two entry functions (`openReportEvidenceUpload`, `openReportEvidenceCamera`) skip the gate; a guest reached the upload and camera screens through them in a real browser (section 4.1). |
| 2 | Login required before camera or file access | **PARTIAL** | Same gap. `startDocumentCamera`, `docHandleFile` and the other wizard actions have no check of their own. |
| 3 | Registered users and admins keep access | **COMPLETE** | A registered user ran the whole camera flow (probe). Admin passes the same `isAccountUser` test (`role !== 'guest'`, by code reading; admin was not exercised separately in a browser). |
| 4 | Owner-verification API enforces server-side authentication | **COMPLETE** | `POST /api/v1/verification/check` has `@login_required()`: anonymous 401, guest 403, CSRF, rate limit. 95 relevant backend tests pass. |
| 5 | No private document/owner data exposed to unauthorized users | **PARTIAL** | Server side is sound (4.3). Browser side: document-verification history sits in one shared `localStorage` key, unbound to any account (4.2). |
| 6 | Uncertain OCR is not shown as verified | **COMPLETE (offline fixtures only)** / live OCR **BLOCKED** | Decision code and tests are conservative; live OCR could not be run here (section 6). |
| 7 | Results explain limitations honestly | **COMPLETE** (one wording gap, 4.5) | Every result carries limitations text. |
| — | `camera_upload_test.py` failure | **Existing test issue; RESOLVED in G6.1c** | Section 5 (status note at its end). Not an application defect. |

## 2. What already works (preserve)

- **Route gating:** `nav()` and `routeFromHash()` in `frontend/js/app/router.js` gate `verify-document`, `ownerverify`, `verify`, `report`, `verlist`, `reportslist`, `savedlist` through `GUEST_BLOCKED_VIEWS` (`services/sessionUser.js`). Browser probe as a real guest: `#verify-document` opened the "Login required" dialog and no document view.
- **Everything runs in the browser.** Document OCR (Tesseract.js), PDF text (PDF.js), extraction and the verdict (`domain/extraction.js`, `domain/documentVerification.js`, `services/ocr.js`). No file, image or OCR text is sent to the server (no `fetch` in those modules). The only server call is the owner-name check.
- **Upload validation (`features/verifyDocument/flow.js` ~L74-80):** PDF/JPEG/PNG allow-list, 15 MB limit, image quality gate before OCR (`assessImageQualityFromDataUrl`), friendly failures for unreadable PDFs and a missing OCR engine.
- **Camera:** starts only after an explicit click on "Open Live Camera" (`startDocumentCamera`), with an unavailable/denied fallback to file capture.
- **Honest verdicts:** statuses `verified / not_verified / unable_to_verify / suspicious / ocr_failed`; manual entry can never be "Original" (`documentVerification.js` L80-81); OCR text is reported as "unable to verify, not mismatch" when uncertain (L153); every result lists limitations including "Official authentication was not performed" and that "Verified" does not prove genuineness or legal validity (L92, L150-153); the attorney of a power of attorney is not treated as checked.
- **Owner check design:** returns only `match / mismatch / unable_to_verify` plus `indicative: true` and a note "not proof of ownership" (`backend/services/verification_service.py`). Owner names live only in `backend/datasets/*.csv`, loaded by `backend/records/ownership.py`; the claimed name is not logged (only property id, verdict and a hashed actor). The UI says "The answer is indicative, not proof" (`features/ownerVerification.js` L117).
- **Storage privacy (partial, 4.2):** `sanitizeResultForStorage` masks 13-digit CNICs; stored records hold no OCR text and no image.
- **Previous improvements intact:** false-positive fixes from Phase B / B.1 (KNOWN_ISSUES item 1). `node scripts/manifest-report.mjs`: "Application path: verified although the manifest expects otherwise = 0".

## 3. Test results (actually run in this audit)

| Test | Result |
|---|---|
| Frontend: `extraction`, `ownerVerification`, `verificationB1Review`, `verificationRules`, `routerGuestGate` | 95 run, **95 pass** |
| Backend: `test_auth`, `test_guest`, `test_guest_browse_only` | 68 run, OK |
| Backend: `test_api` (includes owner check, rate limit) | 27 run, OK |
| `node scripts/manifest-report.mjs` (recorded fixture text, no live OCR) | OCR lane 17/29, PDF lane 28/28 on the application path; 0 "verified" where the manifest expects otherwise |
| `tests/browser/camera_upload_test.py` (unchanged) | **FAIL**: `TimeoutError ... waiting for locator([data-onclick*="openReportEvidenceCamera"])` after 30 s |
| Scratch copy of that test entering as a registered user (`/tmp`, not in the project) | **OK in 5 s** |
| Browser probe: guest + deep link and injected control (`/tmp/probe_guest.py`) | see 4.1 |
| Flask test client: `/backend/datasets/houses.csv`, `/datasets/houses.csv`, path traversal | 404 each; `/assets/Dataset/houses.csv` serves the sanitised public file |

Not run: full frontend/backend/browser suites, `admin_totp_test` and `test_admin_totp` (`pyotp` missing, known), real OCR/PDF on real scans.

## 4. Authentication and privacy findings

### 4.1 Document flow entry gate — PARTIAL (defect, low-moderate)
The only gate is in `nav()`/`routeFromHash()`. These functions set the view directly and never call it (`frontend/js/features/verifyDocument/flow.js` L12-22 and L24-34):
`openReportEvidenceUpload()` and `openReportEvidenceCamera()` do `state.view = 'verify-document'; render();`.
Their only visible buttons are in the `reportslist` view (`features/property.js` ~L236-247), which a guest cannot open, so ordinary users cannot hit the gap.

Demonstrated: a real guest session in Chromium, with a button injected (devtools-style) carrying `data-onclick="openReportEvidenceUpload()"` reached "Select Document Type"; with `openReportEvidenceCamera()` it reached "Scan / Capture Document" with "Open Live Camera" available. No login dialog appeared. I did not click "Open Live Camera" as a guest, but `startDocumentCamera` (`camera.js` ~L300) has no check, so it would call `getUserMedia`.
Impact: client-side only (no server data exposed; the browser's own camera prompt still applies), but it contradicts "login before camera or file access". The same absence of checks applies to `docPickMethod`, `docHandleFile`, `docHandleCameraCapture`, `useCapturedDocument`, `docStartSample`, `docStartManualCheck`.
Also: `router.render()` renders `verify-document` for whatever `state.view` holds, with no session test.

### 4.2 Document history is shared, unbound browser data — PARTIAL (privacy risk, same class as G5 favorites)
- `state/store.js` `loadDocHistory()` / `saveDocHistory()` use the global key `kpt_doc_history` (`config.js` L20). It is loaded for every visitor at start-up (`main.js` L20) and is not tied to an account.
- A stored record contains (verified with a fixture): owner name ("Ahmed Raza"), plot ("34-C"), full address, file name, verdict and reasons. CNICs are masked; no raw OCR text or image is stored.
- It is not cleared on logout. G5's `clearAccountBrowserState()` removes only favorites and filter leftovers, and `authNav.signOut()` does not touch this key.
- Result: on a shared browser, account B can open "My verifications"/history and see account A's previous document results. Guests cannot see it only because the view is gated (finding 4.1 weakens even that).
- The wizard says "N results saved on this device" (`views.js` L71) but nothing says they survive logout or are visible to the next account.

### 4.3 Owner-verification API — COMPLETE, with notes
- `backend/api/verification.py`: `@login_required()` (guests 403 `guest_not_allowed`, anonymous 401 `auth_required`), CSRF on `/verification/*` (`docs/AUTH.md`), `verify_limiter`, input length limits, fixed three-value result. Covered by `test_auth.py` L245-248, `test_guest.py` L111, the G2 route matrix, `test_api.py` L150-170 (including the rate limit).
- Private data: owner names never leave `ownership.py`; previous owners are not loaded; backend CSVs are not served (404 above); the public CSVs in `public/assets/Dataset/` have no owner columns.
- Notes (not defects of authentication): (a) any registered user can test names against property ids, which is an oracle limited only by the per-IP limiter (`request.remote_addr`; behaviour behind a proxy not verified) and not per account; (b) `unable_to_verify` vs `mismatch` reveals whether a property id exists; (c) comparison is exact after normalisation, so a middle name or spelling variant gives `mismatch`, which the note ("indicative") partly covers.
- `docs/API.md` lists only `401 auth_required` for this route; it omits the guest 403 and the 429 limit.

### 4.4 Uncertain OCR — COMPLETE offline, live BLOCKED
Offline: low-confidence extraction ends as `unable_to_verify`, a failed read as `ocr_failed`, and a mismatch only when a field was read and disagrees. Live OCR cannot be exercised here: the app loads `tesseract.js@5` (unpinned, no integrity hash) and `pdfjs-dist@3.11.174` from `cdn.jsdelivr.net` (`frontend/index.html` L100-101), the PDF worker from the same CDN (`ocr.js` L74), and Tesseract language data from `tessdata.projectnaptha.com` (CSP `connect-src`, `backend/security/headers.py`). The sandbox has no network and `public/assets/vendor/` does not exist (KNOWN_ISSUES: vendoring helper `scripts/vendor_assets.py` never run). The scratch run showed the intended fallback: "The OCR engine could not be loaded ... UNABLE TO VERIFY".
The 17/29 and 28/28 figures use recorded text fixtures (`tests/fixtures/ocr_text`, `pdf_text`), not live engine output. "OCR works on real photos" is therefore UNVERIFIED.

### 4.5 Honesty of results — COMPLETE, small gaps
- Present: limitations text on every result; owner check labelled indicative.
- Gaps: no user-facing sentence that documents are read in the browser and not uploaded, nor that history stays on the device after logout (MISSING); `frontend/privacy.html` and `docs/COOKIES.md` still describe `kpt_prefs` as holding filters and saved ids (stale after G5); there is no dedicated verification document (only scattered notes in `KNOWN_ISSUES.md`, `HANDOFF.md`).

### 4.6 Other
- File type check uses the browser-reported `file.type`, not file contents (PARTIAL; low risk since parsing is client-side and the allow-list is narrow).
- Scanned PDFs without a text layer are refused with a clear message (by design).

## 5. The `camera_upload_test.py` failure

**Verdict: an existing, stale test issue. Not a defect in the application and not an environment limitation.**

Evidence:
1. The test calls `enter_as_guest`, then clicks the `reportslist` menu item, then expects `openReportEvidenceCamera`. Since G3b2a, `reportslist` is an account-only view: the guest gets the "Login required" dialog, the evidence buttons never render, and the locator times out after 30 s. That is the application behaving as designed.
2. A throwaway copy entering with `enter_as_user` (G4a3 helper) and a single sign-up passed in 5 s: live fake camera, frame capture, "use photo", the honest OCR-unavailable message, no CSP violation, no page errors.
3. A second weakness already recorded in `docs/KNOWN_ISSUES.md` (item 7 of the first list): even when it passes, the upload half prints `file inputs present: 0` because the file inputs only appear after choosing a document type, and an `if files.count():` guard silently skips the upload.
4. CI consequence: the test is in the CI browser loop, so CI stays red until fixed.
5. Environment note: the network-less sandbox is why OCR reports "could not be loaded"; the test's docstring already says it does not prove OCR works.

**Status update (G6.1c, 2026-10-31): resolved.** The browser test now uses a registered account (`enter_as_user`) and keeps a check that a guest is still refused. It tests camera capture and four actual upload cases through the real file input (unsupported `.txt`, 1x1 PNG refused as unreadable, readable PNG, PDF); a missing upload control or expected message fails the test, so the silent `if files.count():` skip described in point 3 no longer exists. The test blocks the Tesseract.js / PDF.js CDN requests, so what it verifies is the graceful failure messages only. **OCR and PDF text reading remain unverified** (section 6); nothing here shows that they work. The evidence above is kept as the historical diagnosis.

## 6. Missing dependencies / external requirements

| Item | Status |
|---|---|
| Tesseract.js, PDF.js and Tesseract language data from public CDNs at run time | **BLOCKED** here (no network); unpinned/unhashed in production |
| Self-hosted copies (`public/assets/vendor/`, `scripts/vendor_assets.py` + config) | **MISSING**; needs a machine with network and a licence/deployment check |
| `pyotp` (admin TOTP tests) | **BLOCKED** (known; unrelated to G6) |
| Chromium + Playwright | available; used |
| No new dependency is needed for the plan below | — |

## 7. Smallest implementation plan (not started)

Order is by risk; each step is independent and small.

1. **Close the entry gap (G6.2).** Export the existing `allowAccountView` logic from `router.js` (or move to `sessionUser.js`) as one helper; make `openReportEvidenceUpload`/`openReportEvidenceCamera` await it before touching `state.view`. In the wizard actions that open the camera or read a file, add the synchronous `isAccountSession()` check already provided by G5 (`startDocumentCamera`, `docPickMethod`, `docHandleFile`, `docHandleCameraCapture`, `useCapturedDocument`, `docStartSample`, `docStartManualCheck`): if it is false, show the login dialog and return before `getUserMedia`/`FileReader`.
2. **Isolate document history (G6.2).** Smallest safe option: load/show `kpt_doc_history` only for an account session, and remove the key on logout and account change (add it to `clearAccountBrowserState()` / `signOut()`); optionally key it by user id. A server-side history would be a larger design and needs an owner decision (see section 8).
3. **Fix the stale test (G6.3).** `tests/browser/camera_upload_test.py`: enter as a registered user, reach the evidence screens, and make the upload half real (choose a type, assert the file input exists, upload a PNG, assert the honest result). Add `tests/frontend/documentAccessGuard.test.js` (guest/signed-out/failed session refused before camera or file work; user and admin allowed; history not shown or kept across accounts) and one browser case for the injected-control bypass.
4. **Honest wording and documentation (G6.3).** One sentence in the wizard ("read in your browser, not uploaded; saved results stay on this device and are removed when you log out" once step 2 exists); new `docs/VERIFICATION.md`; correct `frontend/privacy.html`, `docs/COOKIES.md`, `docs/API.md` (guest 403, 429), `docs/KNOWN_ISSUES.md`, `HANDOFF.md`.
5. **Live OCR (separate, blocked here).** Vendor and pin Tesseract.js, PDF.js and language data with integrity hashes on a networked machine, update `index.html`, `ocr.js` and the CSP, then run `tests/manual/README.txt` on real documents and phones.

### Exact files that would change
- Step 1: `frontend/js/app/router.js`, `frontend/js/features/verifyDocument/flow.js`, `frontend/js/features/verifyDocument/camera.js`
- Step 2: `frontend/js/state/store.js`, `frontend/js/main.js`, `frontend/js/features/authNav.js`, `frontend/js/services/accountApi.js`, `frontend/js/features/verifyDocument/views.js` (history list/note)
- Step 3: `tests/browser/camera_upload_test.py`, new `tests/frontend/documentAccessGuard.test.js`, optionally `tests/browser/g6_document_access_test.py` plus `.github/workflows/ci.yml` registration
- Step 4: `frontend/privacy.html`, `docs/COOKIES.md`, `docs/API.md`, `docs/KNOWN_ISSUES.md`, `docs/VERIFICATION.md` (new), `HANDOFF.md`, `work.md`, `CHANGELOG.md`
- Step 5 (not G6.2/6.3): `frontend/index.html`, `frontend/js/services/ocr.js`, `backend/security/headers.py`, `scripts/vendor_assets*.json`, `public/assets/vendor/*`
- Backend code: **no change needed** for authentication or privacy of the owner API.

## 8. Decisions needed before implementation
1. **History storage:** device-only, shown only to a signed-in account and wiped at logout (smallest), or a server-side per-account history (new table and API)?
2. Should "Enter details manually" stay behind login too? (It is inside the gated view today, so the plan assumes yes.)
3. Who vendors the OCR libraries, and when? Until then live OCR stays unverified.
4. Should the owner-name check also get a per-account rate limit (currently per IP)? Optional; not part of the smallest plan.

**Stopped. No G6.2 or G6.3 work started. Waiting for review.**
