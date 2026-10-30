# KPT Project Phase Audit (Phase B / B.1) — what was inspected, what was found, how to fix it

Audit date: 2026-10-28. Archive audited: `kpt-phaseB-verification-fix.zip` (109,459,585 bytes, SHA-256 `038a9372…889435`).
Original archive was never modified. All work is in a separate working copy.

> **Scope honesty.** This audit went deep on **document verification** (Phase B / B.1) and ran the full automated suites.
> It did **not** deeply audit authentication, Google OAuth, admin/TOTP, chatbot, listings/messaging, CSP or UI/accessibility beyond
> what the backend unit suite covers. Those areas are listed as *not yet audited* in section 8. No live service (Google OAuth,
> Gemini/OpenAI, PostgreSQL, Resend, Vercel) was tested.

---

## 1. Archive and project identity

| Item | Finding |
|---|---|
| Integrity | `unzip -t`: no errors. 523 entries, 191,436,070 bytes uncompressed, method *store*. |
| Layout | Single root folder `kpt/`. No nested duplicate project trees, no path traversal, no absolute paths. |
| Baseline or modified? | **Already-modified project.** It is the Session-25 master plus the "Phase B" verification fix (CHANGELOG top entry, `docs/KNOWN_ISSUES.md` item 1, `tests/frontend/verificationRules.test.js`). It is **not** the original baseline. |
| Phase B.1 | **No trace in the archive** at the start: no CHANGELOG/HANDOFF/KNOWN_ISSUES entry and none of the B.1 behaviours in code. |
| Git history | None (`CHANGELOG.md` says it was reconstructed from `HANDOFF.md`). |
| Stack | Frontend: static native ES modules, no build step (`frontend/`, `public/`). Backend: Flask 3.1.3 on Python 3.12 (`backend/`), Vercel serverless (`vercel.json`, `pyproject.toml`). DB: SQLite locally, PostgreSQL in production; migrations `0001`–`0007` applied by the app. Tests: Node `node --test` (frontend), `unittest` (backend), Playwright scripts (`tests/browser/*.py`, 16 files). |
| Verification architecture | **Runs entirely in the browser**: Tesseract.js / PDF.js text → `frontend/js/domain/extraction.js` (`parseDocumentText`, `matchProperty`, `compareToProperty`, `decide`) → `frontend/js/domain/documentVerification.js` (`buildAutomaticResult`) → `frontend/js/features/verifyDocument/views.js`. `scripts/manifest-report.mjs` runs the same `decide()` over fixtures. |
| Real-file locations | The prompt's paths all exist as named (`extraction.js`, `documentVerification.js`, `scripts/manifest-report.mjs`, `tests/frontend/pipeline.test.js`, `verificationRules.test.js`). |

### Things that should not ship / housekeeping
- `HANDOFF.md` is 109 KB and `AI_WORKLOG.md`, `REPAIR_REPORT.md`, `MERGE_REPORT_SESSION22.md`, `REFERENCE_MERGE_REPORT.md` are historical session logs — not harmful, but noisy. Consider moving to `docs/history/`.
- Archive weight (~109 MB) is mostly `public/assets/Property Images/*.jpg` (several 3–8 MB originals). Recompress to ≤ 300 KB WebP/JPEG for the site; keep originals out of the deploy bundle.
- `tests/.results/manifest_results.json` is overwritten every time the report runs (generated file, restored to the original in my copy).
- **No** secrets found (pattern scan for API-key/private-key/DB-URL shapes: none). `.env.example` has only empty values. **No** "Skip login" / dev-bypass code found anywhere (`frontend`, `backend`, `tests`).

---

## 2. Phase status table

| Phase / workstream | Status (at start of audit) | Evidence | Tests / verification | Remaining work |
|---|---|---|---|---|
| Phase B: false positives (`pdf/ocr power_of_attorney_mismatch`, `pdf altered_multiple_mismatch`) | **Implemented but not fully verified** | `extraction.js` `decide()`, `crossCheckParties()`, `crossCheckDescriptors()`, `boundaryContains()`; `documentVerification.js` | 165/165 frontend pass; `verificationRules.test.js` (21 tests) asserts the 3 cases are `not_verified`; synthetic fixtures only | Real-scan validation; see §4 |
| Phase B: whole-token plot/survey matching | **Implemented but not fully verified** | `tokenRuns()`, `boundaryContains()` | Rule tests for "4-C", "34" | Covered (extra tests added) |
| Phase B: verified needs all required fields found + compared | **Implemented but not fully verified** | `decide()` (`missing`, `uncompared`) | Rule tests | OK |
| Phase B: attorney identity | **Partially implemented** | Only a *contradiction* check when the attorney CNIC is on a record. No attorney data exists to confirm identity. | Rule tests | Product decision (see §5-P1) |
| Phase B.1: missing-value / placeholder handling | **Not implemented** (record side: `'—'` survey/plot read as mismatch; document side: `N/A`, `nil`, `none`, `unknown`, `TBD` accepted as names; `—` accepted as a survey) | Code read; KNOWN_ISSUES item 1 admits the record-side case | none | **Now implemented** (see §3) |
| Phase B.1: cautious OCR-confusable names | **Not implemented** (names compared exactly; only CNIC/plot had OCR caution) | `compareToProperty` name branch | none | **Now implemented** |
| Phase B.1: no record values in mismatch reasons/reports | **Not implemented** (reasons printed recorded owner, plot, survey, address, size; manual flow printed recorded owner and plot) | `compareToProperty`, `runDocumentChecks` | none | **Now implemented** |
| Phase B.1: result-screen limitations | **Partially implemented** (generic limitation only; no "what verified does not mean"; POA text did not mention legal validity/scope/status) | `buildAutomaticResult` | none | **Now implemented** |
| Phase B.1: result screen shows matched record's owner | **Defect present**: "Owner on record: …" shown for every status, in both auto and manual views | `views.js` (2 places) | none | **Now removed** |
| Phase B.1: tests, docs | **Not implemented** | — | — | Tests added; docs updated by this file (CHANGELOG/KNOWN_ISSUES still need the B.1 entry — see §7) |
| Synthetic OCR validation scripts/docs | **Implemented but not fully verified** | `scripts/manifest-report.mjs`, `tests/fixtures/` (29 OCR + 28 PDF texts) | Report runs; see §4 | Docs should say synthetic ≠ real-world accuracy (already stated in KNOWN_ISSUES) |

---

## 3. Changes made in the working copy (Phase B.1) — and how each works

> Per your `Prompt.txt` checkpoint ("present the audit before continuing development"), treat these as **proposed changes awaiting
> your authorization**. They are small, isolated, and tested; the original ZIP is untouched, so you can discard them.

| File | Change | Why |
|---|---|---|
| `frontend/js/domain/extraction.js` | Added `isMissingValue()` (placeholders `— – - N/A nil none null unknown TBD "not available" "no data"` …; a run of zeros is deliberately *not* a placeholder because the synthetic fixtures use `00000-0000000-0`). Applied in all four normalizers so such text is never a *detected* value. | Placeholders were being read as real names/surveys. |
| same | `compareToProperty`: a record value that is missing/placeholder (owner, CNIC, plot, survey, address, size) leaves the field `unknown` instead of `mismatch`. | Removes the documented "placeholder record reads as mismatch" bug. `decide()` then returns `unable_to_verify`. |
| same | `ocrNameClose()` + `editDistance()`: in the **OCR lane only**, names that differ by ≤ 1 character (or only by OCR-confusable characters), both ≥ 6 letters, are `uncertain` → `unable_to_verify`. A PDF text layer stays exact. Same for the party cross-check (attorney name). | Stops OCR typos becoming proven mismatch/fraud, without ever turning them into a match. |
| same | All mismatch/uncertain messages and `details` no longer contain **any record value**. | A mismatch message used to reveal the owner/plot/survey/address on record (an enumeration oracle). |
| same | Exposed `Extraction.isMissingValue`. | Reused by the manual flow (one source of truth). |
| `frontend/js/domain/documentVerification.js` | Manual flow: no record values in reasons; placeholders ignored. Auto flow: a `verified` result now carries a "what verified does NOT mean" limitation; the Power-of-Attorney limitation now says legal validity, scope, duration and current status were not checked. Conflicting CNIC values in "Checks Performed" are masked. | Honest result wording; privacy. |
| `frontend/js/domain/resultPrivacy.js` (new, pure, no imports) | `maskCnic()` (moved here, re-exported from `documentVerification.js`) and `sanitizeResultForStorage()`. | Avoids an import cycle with `state/store.js`. |
| `frontend/js/state/store.js` | `saveDocHistory()` now stores a CNIC-masked copy. | **Full CNICs, names and plots were being written to `localStorage` (`kpt_doc_history`).** |
| `frontend/js/features/verifyDocument/views.js` | Removed both "Owner on record" lines; conflict values masked on screen; note under "Possible Matching Property": the record owner is not shown and a match is not a confirmed link. | Privacy; avoids implying the matched owner is the confirmed owner. |
| `tests/frontend/phaseB1.test.js` (new, 34 tests) | Placeholders (10 values × document), placeholder record values, plot substrings, PDF-vs-OCR names, attorney CNIC contradiction, missing fields, optional descriptors, no record-value leakage, limitations text, history masking, result-screen rendering. | Regression coverage for every defect above. |

Unchanged on purpose: statuses, `suspicious` handling, fixtures, `pipeline.test.js` baseline (17/29, 28/28), CSP/auth/admin code, dependencies.

---

## 4. Tests — exact commands and real results

| Command | Result |
|---|---|
| `npm test` (original archive, before edits) | **165 tests, 165 pass, 0 fail, 0 skipped** |
| `npm test` (after B.1 changes) | **199 tests, 199 pass, 0 fail, 0 skipped** (165 + 34 new) |
| `node scripts/manifest-report.mjs` | **OCR lane 18/29, PDF lane 28/28** (before and after the edits; unchanged) |
| `python -m unittest discover -s tests/backend -t .` (before and after) | **253 run; 252 pass; 1 error**: `tests.backend.test_admin_totp` → `ModuleNotFoundError: pyotp`. Environment blocker, **not an application defect**: `pip install pyotp==2.10.0` fails offline. The TOTP tests therefore did **not** run. |
| Browser tests (`tests/browser/*.py`, Playwright 1.56.0 package present) | **Not attempted** (no Chromium found in the Playwright cache; no network to install it). |
| PostgreSQL-specific tests | **Not attempted** (no database service). SQLite path was exercised by the unit suite. |
| `pip-audit`, `bandit`, `ruff`, Lighthouse | **Not run.** |

Environment notes: `scikit-learn` installed here is 1.8.0 but the model is pinned to/serialized with 1.9.1 → `InconsistentVersionWarning` (the suite still passes; production pins 1.9.1).

### Why the handoff numbers disagree (now explained, not guessed)
- **165 vs 184 frontend tests:** only **165** is reproducible in this archive. The 184 figure is not supported by any file here (the 199 now includes my 34 new tests).
- **OCR 17/29 vs 18/29:** both are real, from **two different lanes**.
  - `tests/frontend/pipeline.test.js` uses **free-search** matching (what the live app does): **17/29**.
  - `scripts/manifest-report.mjs` anchors each document to its **expected** property: **18/29**.
  - The one-document difference is `ocr/altered_multiple_mismatch`: anchored → `not_verified` (correct), free-search → matches `DEMO-KPT-002` instead and ends `unable_to_verify`. The report itself prints this under "Free-search vs anchored-property agreement".
  - **Fix for the docs:** always write "OCR 17/29 (app lane) / 18/29 (anchored report)".
- **`pyotp` missing / TOTP browser test blocked:** confirmed as an environment problem (see above); the archive pins `pyotp==2.10.0`.

Important caveat: all 29 + 28 documents are **synthetic**. These numbers show regression behaviour, **not** real-world fraud-detection or OCR accuracy.

---

## 5. Problems, priority, evidence, and how to fix

### Security / privacy
| # | Item | Class / priority | Evidence | How to fix |
|---|---|---|---|---|
| S1 | Mismatch messages revealed record owner/plot/survey/address/size; result screen showed "Owner on record" for every status | Security-critical, **fixed** in working copy | `extraction.js` (old messages), `views.js` (2 lines) | Done (§3). Keep `phaseB1.test.js` leakage tests. |
| S2 | Full CNIC/name/plot persisted in `localStorage` history | Security-critical, **fixed** | `store.js saveDocHistory`, `config.js STORAGE_KEYS.docHistory` | Done (masked copy). Consider also letting users delete all history and add a retention limit (e.g. last 20). Existing users' old entries stay until overwritten: on load, re-save once. |
| S3 | Full conflicting CNICs shown in "Checks Performed" and conflict row | Privacy, **fixed** | `buildAutomaticResult`, `autoFieldRow` | Done. |
| **S4** | **Owner names and CNICs for the property records are shipped to every browser** (`frontend/js/data/properties.js` has `owner`/`cnic`; verification runs client-side). Anyone can read them in DevTools. | **Security-critical, product/architecture decision — NOT fixed** | `properties.js` lines 4–10 (`owner`, `cnic`), `allVerificationRecords()` | Move verification to a backend endpoint (e.g. `POST /api/v1/verify-document`) that receives only the **extracted fields**, compares server-side and returns only `status` + generic reasons; remove `owner`/`cnic` from `properties.js`. Add per-IP rate limiting (the backend already has `VERIFY_RATE_LIMIT_PER_MIN`) so the endpoint can't be used to enumerate records. Until then, "advisory only, runs in your browser" must stay in the UI. |
| S5 | Verification is client-side, so a user can alter the result in DevTools | Product decision | KNOWN_ISSUES item 1 already says "advisory, not enforcement" | Same fix as S4; never use the result for any authorization decision. |
| S6 | OCR/PDF libraries loaded from CDNs without SRI (Tesseract.js `@5` unpinned, PDF.js 3.11.174, Google Fonts) | Security | `docs/KNOWN_ISSUES.md` "Third-party asset inventory"; `scripts/vendor_assets.py` exists | Vendor and pin the assets (the script and docs already describe the steps), then drop the CDN hosts from the CSP. Needs network, so not done here. |
| S7 | Secrets / login bypass | — | Scan found none | No action. Keep `tests/backend/test_external_assets.py`-style guards. |

### Verification correctness
| # | Item | Class / priority | How to fix |
|---|---|---|---|
| V1 | Placeholder document/record values | Verification correctness, **fixed** | Done. |
| V2 | OCR name typos → hard mismatch | Verification correctness, **fixed** (OCR lane only) | Done. Tune the "≥ 6 letters, distance ≤ 1" rule only with real scans. |
| V3 | An attorney whose CNIC is on no record can still end `verified` | Product decision, **open** | Today the result says the attorney was not confirmed (now also "legal validity, scope, duration, status not checked"). Choose: (a) keep `verified` + strong limitation, or (b) make POA documents max out at `unable_to_verify` unless an attorney record exists. Recommended: **(b)** for POA, because "verified" currently over-reads. Change in `decide()`: if `profile.label==='Power of Attorney'` and an attorney party is present and not on any record → `unable_to_verify`. |
| V4 | `suspicious` is a **fourth** status alongside `verified / not_verified / unable_to_verify` | Product decision | It is consistently defined across `extraction.js`, `documentVerification.js`, `AUTO_STATUS_META` and the tests, and means "the document contradicts itself". Either document it as the fourth state (recommended) or map it into `not_verified`. Update every doc that says "three statuses". |
| V5 | Area units (sq ft vs sq yards) not converted | Functional bug (low) | Parse unit; convert to sq yd before comparing; unknown unit → `unknown` (never match). |
| V6 | OCR still can't confirm 5 *valid* synthetic documents (`sale_deed`, `allotment`, `transfer_order`, `power_of_attorney` matching, `ocr_challenge`) | Verification correctness (false negatives, safe direction) | CNIC `90000-0000000-0` shows OCR confusing leading `0`→`9`; plot `17-8` for `17-B`. Improve capture of those fields (pre-process image contrast, whitelist digits/`-` for CNIC lines, re-OCR the CNIC line region) and **re-measure on real scans**, not only synthetic ones. |
| V7 | Free-search can match the wrong record (`altered_multiple_mismatch` → `DEMO-KPT-002`) | Verification correctness | Prefer the record that matches the **most strongly** (CNIC > plot > name); when two records tie or when fields point to different records, return `suspicious`/`not_verified`. Add a test for "fields point to two different records". |
| V8 | Name matching uses exact normalized equality in `matchProperty` | Functional | Acceptable (candidate selection only); revisit with real data. |

### Test coverage / docs
| # | Item | How to fix |
|---|---|---|
| T1 | `pyotp` not installable offline → TOTP tests unrun | On your machine: `python scripts/install_deps.py --dev` then `python -m unittest tests.backend.test_admin_totp -v`; record the result. |
| T2 | Browser tests not run | `python -m playwright install chromium`, then run each `tests/browser/*_test.py` / `smoke.py` (CI already does: `.github/workflows/ci.yml`). Add one browser test that loads a verified result and asserts no "Owner on record" text. |
| T3 | Test-count and OCR-count inconsistencies in HANDOFF/CHANGELOG | Replace with the two-lane wording above and the real counts. |
| T4 | CHANGELOG/KNOWN_ISSUES/HANDOFF have no Phase B.1 entry; KNOWN_ISSUES still lists "placeholder record reads as a mismatch" and "attorney with unknown CNIC verified" | Update when the B.1 changes are authorized (suggested text in §7). |
| T5 | `pipeline.test.js` computes the file name with a regex that only works because manifest entries are literally `name.png/.pdf` | Cosmetic: replace with `path.parse(...)`-based logic; low priority. |

---

## 6. Phase B checklist (your 11 items), with verdict

| # | Check | Verdict |
|---|---|---|
| 1 | Required fields actually detected before `verified` | ✅ `decide()` `missing` |
| 2 | Values positively compared with usable record values | ✅ (after B.1: placeholder record values are not "usable") |
| 3 | Missing/blank/placeholder not treated as valid identifiers | ✅ after B.1 (was ❌) |
| 4 | Placeholders `— – - N/A nil none null unknown TBD` | ✅ after B.1 (tested for all ten) |
| 5 | Token-aware plot/survey matching | ✅ already present |
| 6 | Attorney identity vs records | ⚠️ contradiction-only; no attorney registry exists (V3) |
| 7 | PDF contradiction vs OCR inconclusive | ✅ `opts.ocr` lane distinction |
| 8 | OCR confusables not proven fraud | ✅ CNIC/plot already; **names added in B.1** |
| 9 | Optional fields corroborate but don't create false confidence | ✅ (`crossCheckDescriptors` only reports contradictions) |
| 10 | Missing field → inconclusive | ✅ |
| 11 | Status definitions consistent | ⚠️ four statuses (V4) |

Result-screen/privacy: verified result explains limits ✅ (new); POA does not imply legal validity ✅ (new); no unnecessary record data in reasons/reports ✅ (new); matched owner no longer shown ✅ (new); localStorage masked ✅ (new); client-side record data ❌ (S4).

---

## 7. Suggested documentation text (to add on authorization)

**CHANGELOG.md — Phase B.1**
```
## Phase B.1: verification hardening
* Placeholders (—, N/A, nil, none, null, unknown, TBD …) are treated as missing on the document and on records.
* OCR lane: names differing by one character are "unable to verify", never a proven mismatch.
* Mismatch reasons, checks and details no longer contain any value from the record; "Owner on record" removed from result screens.
* Verified/POA results state what they do not confirm. History in localStorage stores masked CNICs.
* Tests: tests/frontend/phaseB1.test.js (34). Baselines unchanged: OCR 17/29 (app lane) / 18/29 (anchored report), PDF 28/28.
```
**docs/KNOWN_ISSUES.md** — remove the two items B.1 fixed; add S4/S5/V3/V4/V5/V6/V7.

---

## 8. Not yet audited (honest gaps)

Authentication (registration, login, lockout, CSRF, sessions, password reset, remember-me), **Google sign-in** (implementation/tests may exist; no live OAuth test was or could be run), admin/TOTP (tests unrun, `pyotp`), chatbot/AI providers (fake-SDK tested only per the changelog), listings/messaging, cookie consent flows, CSP/header review, accessibility, performance, dependency audit (`pip-audit`), "PIN ME" version ranges in `pyproject.toml`. The backend unit suite passes for these (252/253) but that is **not** a security review or a live test.

## 9. Recommended next steps (in order)
1. Authorize (or reject) the B.1 working-copy changes; if authorized, add the §7 documentation edits.
2. Decide V3 (POA) and V4 (fourth status).
3. Plan S4/S5: server-side verification endpoint and removal of owner/CNIC from `properties.js` (highest remaining risk).
4. On your machine: install `pyotp`, Playwright Chromium; run `npm run test:all` and the browser tests; send me the output.
5. Then audit auth/Google/admin/chatbot per `Prompt.txt` Phase 3 and report before any further code changes.

---

## 10. Update after owner feedback (2026-10-28)
- **Skip login / `admin__01`:** confirmed by the owner as a deliberate feature. It was absent from `kpt-phaseB-verification-fix.zip` (so it was not removed by this audit) and has been restored byte-for-byte from the Session 25 archive. Its own limits (404 in production, local SQLite only, empty password never matches) are unchanged. Tests: `tests/backend/test_dev_skip.py` 9/9 pass; the earlier statement "no bypass code found" was true only of the Phase B archive.
- **Fictional records:** owner says the 8 records in `properties.js` are fictional demo data (S4 stays an architecture risk, not a live data leak).
- **B.1:** still awaiting explicit authorization (see CHANGELOG).
- **Current totals:** `npm test` 199/199; backend 262 run, 261 pass, 1 environment error (`pyotp`); browser `login_test`, `csp_test`, `smoke` pass.
