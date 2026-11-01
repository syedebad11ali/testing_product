# G6.2a-2 — Owner data provenance and privacy audit

Audit only. Baseline: `karachi-property-trust-G6_1-integrated.zip` (SHA-256 `ef8f7052…1a59`) with `g6-phase2a-1.patch` applied in a scratch copy (dry-run and apply clean; 549 files). Nothing in the project was modified. No data was removed, replaced, fabricated or masked. G6.2b not started.

**Privacy rules for this report:** no full CNIC and no personal name is reproduced. CNIC-shaped values appear masked as `PPPPP-*******-D` (first five digits, last digit). Records are referred to by property ID (`p1`–`p8`) and file path. Counts come from read-only scripts.

**Not available / not done:**
- `docs/G6_PHASE2A_AUDIT.md` was not among the uploaded files; its finding (public `properties.js` with owner/CNIC) was taken from your brief and re-verified independently here.
- `Continuation_of_work_.rar` (RAR5) was not opened: no RAR tool is installed and installing is not allowed.
- The archive has no `.git` history, so "repository history" can only mean the changelog/handoff documents inside it.

## 1. Summary

| Question | Answer |
|---|---|
| Are `p1`–`p8` owner names and CNICs publicly exposed? | **Yes.** `GET /js/data/properties.js` returns HTTP 200 to an anonymous caller with 8 owner names and 6 CNIC-shaped values (`p1,p2,p3,p4,p6,p8`). |
| Are they shown to guests on pages? | **Yes (by code reading):** the property detail page (`renderDetail`, not login-gated; browsing details is allowed for guests) prints the owner name and role for every property. |
| Are they documented as fictional? | **Yes, as an owner statement,** repeatedly (section 3). **No corroborating evidence of how they were made exists** in the archive. |
| Are they confirmed synthetic? | **Not confirmed.** Provenance: documented fictional + several synthetic indicators, but real-world status cannot be proven from the repository. |
| Any real-looking personal data proven? | **No.** Nothing proves the values belong to a real person; nothing proves they do not. |
| Other exposure paths? | Mostly closed: public CSVs have no owner columns, private datasets and `data-source/`, `notebooks/`, `tests/` return 404, APIs return no owner fields, the claimed name is not logged. |
| Can the values simply be deleted? | **No, not without changes:** the in-browser document verifier matches against them and two test files hard-code `p1`'s values (section 7). |

## 2. Where owner-identifying data exists

| # | Location | Public? | What it holds (counts/masks only) | Class |
|---|---|---|---|---|
| E1 | `frontend/js/data/properties.js` | **Public** (`/js/data/properties.js`, 200, 9,570 bytes) | `owner` for `p1`–`p8` (2-word names), `ownerRole`, `seller` note; `cnic` for `p1`,`p2`,`p3`,`p4`,`p6`,`p8` (none for `p5`,`p7`) | **Unknown/unverified provenance; documented fictional** |
| E2 | `frontend/js/features/property.js` L77 | **Public** | `p1`'s CNIC value as an input placeholder (`e.g. 42101-*******-1`) | Example value (see 4.2) |
| E3 | `frontend/js/data/documentTypes.js` L21 | **Public** | the same value as a field placeholder | Example value |
| E4 | `frontend/js/data/documentTypes.js` `DEMO_PROPERTIES` (3 records) | **Public** | owner names + CNICs of the form `00000-*******-0/1/2` | **Confirmed synthetic** (explicit comment L97-98; all-zero area code) |
| E5 | `public/assets/samples/*.pdf/png/jpg` (57 files) | **Public** | sample documents; 28 PDFs checked (two utility PDFs contain no CNIC-shaped value): every CNIC-shaped value starts `00000-` | **Confirmed synthetic** (and `tests/manual/README.txt`: "all fictional") |
| E6 | `public/assets/Dataset/*.csv` (5 files) | Public | sanitised copies; header checked: **no** `Owner ID / Owner Name / Property Owner / Previous Owner` column | Masked/removed |
| E7 | `backend/datasets/*.csv` (5 files, 16,000 rows) | **Not served** (404 over HTTP); ships in the project archive | `Owner ID`, `Owner Name`, `Property Owner`, `Previous Owner` for every row | **Unknown provenance** (section 4.3) |
| E8 | `data-source/properties_karachi_dataset*.xlsx`, `notebooks/*.ipynb` | Not served (404); ship in the archive | the same owner columns (17,450 and 16,000 data rows); notebook outputs show the `Owner Name` column | Unknown provenance |
| E9 | `tests/fixtures/**`, `tests/frontend/*.js`, `tests/.results/manifest_results.json` | Not served | CNIC-shaped values: fixtures use `00000-`/`9xxxx-` style values; `extraction.test.js` and `verificationB1Review.test.js` use `p1`'s value | Synthetic (fixtures); example value (tests) |
| E10 | `docs/*.md` | Not served | no owner CNIC (the only hits are a zip file name and prose) | n/a |

## 3. What the project says about the records

| Statement | Where | Scope |
|---|---|---|
| "The 8 sample records in `frontend/js/data/properties.js` are fictional demo data (owner decision)" | `HANDOFF.md` L45; `work.md` L9; `docs/HANDOFF_ARCHIVE.md` L890, L981; `docs/GUEST_BROWSE_ONLY_PLAN.md` L22 | `p1`–`p8`, explicit |
| "Demo site with fictional data" | `frontend/index.html` footer; `login.html`; `developer-login.html`; `privacy.html` ("demo site with fictional property data") | whole site, user-visible |
| "Synthetic verification database … Fictional records for testing only" | `documentTypes.js` L97-98 | `DEMO_PROPERTIES` only |
| "Demo property listings and the lookup tables derived from them" | header of `properties.js` | file header; says "Demo", not "fictional/synthetic" |
| "(demo/testing only — fictional)" | `verifyDocument/views.js` L96 | sample documents |
| `S4` plan: "move document verification to the server … and remove `owner`/`cnic` from `properties.js`" | `docs/HANDOFF_ARCHIVE.md` L910 | an earlier recommendation that was never done |

All of these are **assertions by the project owner.** None cites a source, a generator script or a date for `p1`–`p8`. No file in the archive generates or imports them. `properties.js` itself carries no "fictional" marker next to the personal fields.

## 4. Provenance evidence (what can and cannot be established)

### 4.1 Indicators that the `p1`–`p8` CNICs were invented
- The last digit increases by one in listing order: `p1`→1, `p2`→2, `p3`→3, `p4`→4, `p6`→5, `p8`→6 (`42101-*******-1` … `42101-*******-6`; `p4` uses prefix `42201`).
- The seven-digit part of `p1`, `p2`, `p3` is a plain ascending digit run (a typical placeholder); `p4`, `p6`, `p8` are not obviously patterned.
- None of the six values appears in any other file except `p1`'s (4.2).
- A CNIC has no public check digit, so validity cannot be tested.

### 4.2 `p1`'s CNIC is the project-wide example value
`p1`'s value (`42101-*******-1`) is also the form placeholder in `documentTypes.js` L21 and `property.js` L77, and appears ~25 times in `tests/frontend/extraction.test.js` and `verificationB1Review.test.js` next to a generic example name and plot `34-C`; `extraction.test.js` L220 builds a record "`p1`" with those same values. That is strong evidence `p1`'s owner/CNIC pair is the project's standard dummy example, **not** a real person. **Confidence: high** that `p1` is a placeholder.

### 4.3 Owner names and the private dataset
- 5 of the 8 `properties.js` owner names (`p1`,`p2`,`p3`,`p4`,`p6`) also occur in `backend/datasets/*.csv` (1-2 rows each: as `Previous Owner` for `p1`–`p4`; as `Owner Name`/`Property Owner` for `p6`). In every case the dataset row is for a **different area/property type** than the `properties.js` listing. So the names are reused from, or drawn from the same pool as, the dataset; they are not the dataset's record for that property. `p5`,`p7`,`p8` match nothing.
- The dataset looks machine-generated, but this is **an indicator, not proof:** every `Property ID` is `DEMO-KPT-<digits>`; owner names are always exactly two words built from ~800 distinct tokens across 16,000 rows with at most 2 repeats per name; the `Column Guide` says prices are "randomly generated"; the `.xlsx` files were written by `openpyxl` (created 2026-09-27/28).
- **Nothing states that the names themselves are generated**, there is no source, licence or collection note for the dataset, and the notebooks (no `faker`/`random` use for names) do not generate them.
- Names are common: during the API scan, the throw-away test account's own name matched a dataset name. A match between a name and a real person therefore cannot be excluded for any of the 16,000 + 8 names.

### 4.4 Classification (no guessing)

| Data | Classification | Confidence | Basis |
|---|---|---|---|
| `p1` owner + CNIC | **Confirmed placeholder/example** | High | used as the generic example in UI placeholders and tests; ascending pattern |
| `p2`,`p3` CNIC | **Likely invented** (sequential check digit, ascending pattern) | Medium | pattern only; no source |
| `p4`,`p6`,`p8` CNIC | **Unknown provenance** (documented fictional by owner) | Low-medium | non-patterned middle digits; only the sequential last digit and the owner statement |
| `p1`–`p8` owner names | **Unknown provenance** (documented fictional by owner); likely drawn from the same pool as the dataset | Medium | reuse across the dataset; no source |
| `DEMO_PROPERTIES` (3), sample documents (57), `tests/fixtures` | **Confirmed synthetic** | High | explicit labels, all-zero area codes, README |
| `backend/datasets` + `data-source` owner columns (≈16,000 names/IDs) | **Unknown provenance** (strong "generated" indicators, no statement) | Medium | section 4.3 |
| Public CSVs | **Masked/removed** (verified) | High | header check |

Only the owner can settle E1/E7/E8 (a one-line written statement of how the data was made, or the generator script).

## 5. Exposure paths checked

| Path | Result | Evidence |
|---|---|---|
| `GET /js/data/properties.js` (anonymous) | **Exposes** 8 owner names, 6 CNIC-shaped values | HTTP 200 |
| `GET /js/features/property.js`, `/js/data/documentTypes.js` | Expose `p1`'s example CNIC; synthetic `DEMO_PROPERTIES` | HTTP 200 |
| Property **detail** page (guest allowed) | **Shows owner name, owner role, seller type** for `p1`–`p8` (`property.js` L37-40) | code reading; view not in `GUEST_BLOCKED_VIEWS`; not exercised in a browser |
| Verify / report pages (login-gated) | Show owner name; pre-fill the owner-name field with the owner name; show the CNIC placeholder | `property.js` L77, L81, L120, L170 |
| Home search and cards | Do not use owner/CNIC (`home.js` has no reference) | grep |
| Document-verification matching | The in-browser verifier compares uploaded documents with `allVerificationRecords() = DEMO_PROPERTIES ∪ PROPERTIES` (`documentVerification.js` L119), so `p1`–`p8` owner/CNIC are active reference data. A registered user can learn nothing from it that the public file does not already show. | code |
| `/assets/Dataset/*.csv` | No owner columns | header check of all 5 |
| `/backend/datasets/*`, `/data-source/*`, `/notebooks/*`, `/tests/*` | 404 | Flask test client. **Vercel static serving outside Flask was not testable**; `vercel.json` only sets function and header options |
| APIs | `GET /api/v1/listings`, `/chat/session`: no owner/CNIC, no dataset names. `POST /verification/check`: only `result`, `indicative`, `note`. `backend/records/store.py` never loads owner columns. Chat has a deterministic owner-details refusal (`guardrails.asks_for_owner_details`). | live calls (registered user) + code |
| Logs | The claimed name is not logged; only property id, verdict, hashed actor (`verification_service.py` L20-21) | code |
| Browser state | History entries keep an owner name and masked CNIC but are account-bound and wiped at logout (G6.1b). Saved properties hold ids only. No owner data in cookies. | G6.1b tests; `resultPrivacy.js` |
| Search-result / export files | No public export contains owner data (public CSVs sanitised; admin exports are user/login data) | G5/G6.1 audits |
| Archive distribution | Owner columns for ~16,000 rows travel inside the project ZIP (`backend/datasets`, `data-source`, notebooks) | file listing |

The earlier statement "it is the owner decision that `/js/*` is public static" still holds, so the public-JS exposure is a known, accepted limitation. What this audit adds is that the **guest-visible detail page also prints the owner name**, which is not mentioned in the plan.

## 6. Existing test coverage

| Test | What it covers | Depends on `p1`–`p8` owner/CNIC? |
|---|---|---|
| `tests/frontend/extraction.test.js` | OCR text parsing + matching | Yes: hard-codes `p1`'s name, plot and CNIC (~25 occurrences; L220 builds the "p1" record) |
| `tests/frontend/verificationB1Review.test.js` | CNIC masking, privacy of results | Yes: `p1`'s CNIC literal (L99, L122-123, L160) |
| `tests/frontend/phaseB1.test.js`, `verificationRules.test.js` | decision rules | Use `DEMO_PROPERTIES` / own CNICs, not `p1`–`p8` |
| `tests/frontend/propertyDisplayStatus.test.js`, `homePrefs`, `propertyUploadHonesty` | listings/ids | Reference `PROPERTIES` structure, not owner/CNIC values |
| `tests/backend/test_auth.py`, `test_guest*.py`, `test_api.py` | owner-name API: auth, guest 403, verdict-only response, rate limit | No (private dataset ids) |
| `tests/fixtures`, `scripts/manifest-report.mjs` | recorded document texts | No (`00000-`/`9xxxx-` values) |
| (none) | **Nothing asserts that the public JS or property pages contain no owner/CNIC data, nor that they use only synthetic-marked values** | gap |

## 7. Features that depend on the fields

1. **Property detail page** (public): owner card (`property.js` L37-40) needs `owner`, `ownerRole`, `sellerType`.
2. **Verify page** (gated): owner-name input pre-filled from `owner`; CNIC placeholder.
3. **Report page** (gated): "Owner" row.
4. **Document verification:** `PROPERTIES` records are reference data (`documentVerification.js` L15-17, L58-59; `extraction.js` L322-381, L467-475). Changing or removing them changes which documents "match".
5. **Two tests** (above).

## 8. Recommended action (not executed)

The records are *documented as fictional* but *provenance is not provable*, and `p4`,`p6`,`p8` CNICs and all names cannot be shown to be non-real. Because the file is public by decision, the smallest safe remediation treats them as unverified.

**R0. Ask the owner (no code).** Obtain a written statement or the generator for `p1`–`p8` and for the dataset's owner columns. If the owner confirms they were invented, record it in `properties.js` and `HANDOFF.md`, and stop here for the CNICs (still consider R3).

**R1. Smallest data-only change (recommended if R0 cannot confirm):** replace `owner` and `cnic` for `p1`–`p8` with values that follow the project's existing, already-documented synthetic convention (CNIC `00000-…`, names marked "Demo …"), keep every other field and every key. Files that would change: `frontend/js/data/properties.js`; the two placeholders `property.js` L77 and `documentTypes.js` L21 (switch to a `00000-` example); `tests/frontend/extraction.test.js` and `tests/frontend/verificationB1Review.test.js` (update the hard-coded `p1` values). No logic change; verification still matches because records and tests change together.

**R2. Add a guard test:** a frontend test that fails if any CNIC-shaped value in `frontend/js/**` or the property detail output does not start with `00000-`, or if an owner name is not marked demo. New file only.

**R3. Larger, separate decisions (not part of the smallest fix):** (a) stop printing owner names on the guest-visible detail page; (b) the S4 plan: move document matching to the server and drop `owner`/`cnic` from `properties.js`; (c) decide whether the 16,000-row owner dataset and the `.xlsx`/notebooks should ship in the archive at all and obtain provenance for them. If any real data was ever involved, the ZIP and any earlier deployment already contain it; removal from the current tree does not remove it from earlier copies.

**Do not** rewrite in-browser verification or the owner API for this issue; both are working as designed.

## 9. Open questions for the owner
1. How were `p1`–`p8` (names and CNICs) and the dataset's owner names produced?
2. Should guests keep seeing an owner name on property detail pages?
3. Is R1 acceptable, or do you prefer only R0/R2 until provenance is confirmed?

## 10. Checks run (read-only)
CNIC-shape scan of the whole tree (counts); property schema/masked classification; cross-reference of `p1`–`p8` against other files and against the 16,000 dataset rows (counts and area/type only); static-route probes with the Flask test client; header check of the 5 public CSVs; text extraction of 28 sample PDFs (masked prefixes); registered-user API response scan; `.xlsx` metadata and Column Guide; documentation keyword search. No tests were run and no project file was changed.

**Stopped.** No data removed, replaced or masked. G6.2b not started.
