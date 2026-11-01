# G6.2a-3 - Owner data privacy remediation plan (PLAN ONLY)

Status: **plan and evidence only. No application code, data, test or configuration was changed.** Nothing below is implemented until the owner approves the scope (section 11).
Baseline: `karachi-property-trust-G6_1-integrated.zip` (SHA-256 `ef8f7052bcdb1af350827db6082cbfcb9d38a224e0799a179716f74911291a59`) + `g6-phase2a-1.patch` (dry-run clean, applied once, reverse dry-run confirms a single application). Input: `docs/G6_PHASE2A2_PRIVACY_AUDIT.md` (copied unchanged). This document contains **no personal values**: names and CNICs are referred to by property id, count, field and (for CNICs) the first five digits, which are an area code, not an identifier.

## 1. Facts re-verified in this tree (read-only)

| # | Finding | How checked |
|---|---|---|
| F1 | `frontend/js/data/properties.js` (9,570 bytes, public) holds `owner` for all 8 records `p1`-`p8` (2-word names, 8 distinct) and `cnic` for `p1,p2,p3,p4,p6,p8` (13-digit, prefixes `42101` x5, `42201` x1). `p5`,`p7` (sellerType Company) have no CNIC. `ownerRole` and `sellerType` exist on all 8; `seller` on `p8` is a single emoji (not identifying). | structural parse, values masked |
| F2 | Non-synthetic CNIC-shaped values exist in exactly these files: `properties.js` (6), `frontend/js/data/documentTypes.js` (1, a field placeholder L21), `frontend/js/features/property.js` (1, an input placeholder L77), `tests/frontend/extraction.test.js` (25), `tests/frontend/verificationB1Review.test.js` (4). Everything else is `00000-...` (synthetic) or `9xxxx-` (deliberate mismatch values in fixtures; prefixes `90000`, `90008`, `99000` only). | whole-tree scan, 0 secrets/private datasets included, values not printed |
| F3 | `p1`'s **name** also appears in `documentTypes.js` L18 (a placeholder) and 29 times in `extraction.test.js`. No other file contains any `p1`-`p8` name (docs, fixtures, other tests: 0). | per-file occurrence counts |
| F4 | **None of the 28 sample PDFs** contains a `p1`-`p8` name or CNIC (`pdftotext` scan). The 29-entry manifest and `scripts/manifest-report.mjs` use only `tests/fixtures/property_database.json` (3 synthetic `DEMO-KPT-00x` records, CNICs `00000-0000000-0/1/2`). The 29 PNG/JPG samples were not text-scanned (no OCR available); they are renderings of the same documents, **unverified**. | scan + code reading |
| F5 | Runtime verification matches against `allVerificationRecords() = DEMO_PROPERTIES U PROPERTIES` (`documentVerification.js` L119; `extraction.js` L322-381, L467-475 use `p.owner`/`p.cnic`). Replacing the `p1`-`p8` values changes only which *documents* match those records. No sample or fixture depends on them. | grep + F4 |
| F6 | Guest-visible exposure: `renderDetail()` in `frontend/js/features/property.js` L36-41 prints the owner avatar initials, owner name and `ownerRole . sellerType` for every property; the detail view is not in `GUEST_BLOCKED_VIEWS`. Gated views (`verify` L81 pre-fills the owner name, L77 CNIC placeholder; L120 and `report` L170 print the owner) require an account. | code reading |
| F7 | `home.js`, `featured.js`, `promo.js`, `propertyStatus.js`, `scripts/seed_demo_listings.py` import `properties.js` but never read `owner`/`cnic`. No API returns owner fields. No browser test and no test other than the two named in F2 reads owner values. `.owner-card`/`.owner-name` appear only in `frontend/css/property.css` (L17,19). | grep |
| F8 | The synthetic convention in the project is `00000-0000000-N` (all-zero area code and serial, `N` = check digit), used by `DEMO_PROPERTIES`, the fixtures and the tests (`N` in 0,1,2,5,7,9). The `DEMO_PROPERTIES` owner names are ordinary-looking names (not marked "Demo"). | grep |
| F9 | Baseline (actual): `npm test` **397/397**; `extraction` 34, `verificationB1Review` 15, `phaseB1` 34, `verificationRules` 21, `homePrefs` 23, `propertyDisplayStatus` 4, `propertyUploadHonesty` 7, `assetsPresent` 4, `ownerVerification` 9, `documentHistoryIsolation` 19, all passing. `node scripts/manifest-report.mjs`: "verified although the manifest expects otherwise = 0". (The report rewrote the generated `tests/.results/manifest_results.json` in the scratch copy; it was restored.) | run |
| F10 | `GET /js/data/properties.js` is public by owner decision (`/js/*` static). Hiding the owner card is therefore **display-only**; only R1 (synthetic values) removes the underlying exposure. | prior audits |

## 2. Principles
1. Do not claim the existing values are real or fake: the audit could not establish provenance. Treat them as *unverified* and stop publishing them.
2. Replace values; keep every key, id, plot, area, price, status and structure unchanged.
3. Never weaken a verification rule or a test assertion: tests keep asserting the same statuses; only the literal values change.
4. No change to authentication, the database schema, the owner-name API, OCR/extraction rules or the private dataset.
5. New synthetic values must be recognisably synthetic and collide with nothing.

## 3. Proposed synthetic values (specification, nothing applied)

| Record | `owner` (new) | `cnic` (new) |
|---|---|---|
| p1 | `Demo Owner Alpha` | `00000-0000101-0` |
| p2 | `Demo Owner Bravo` | `00000-0000102-0` |
| p3 | `Demo Owner Charlie` | `00000-0000103-0` |
| p4 | `Demo Owner Delta` | `00000-0000104-0` |
| p5 | `Demo Company Echo` | (none, as now) |
| p6 | `Demo Owner Foxtrot` | `00000-0000106-0` |
| p7 | `Demo Company Golf` | (none, as now) |
| p8 | `Demo Owner Hotel` | `00000-0000108-0` |

Rules and why: (a) prefix `00000-` is the project's established marker and is not a valid area code; the middle part `00001NN` encodes the property number so the six values are unique and **collide with none of the CNICs found in tests, fixtures and the 28 sample PDFs** (checked: those use only the middle part `0000000`); (b) names start with `Demo`, are distinct (edit distance large), so the in-browser matcher's near-match logic cannot confuse two records; (c) `ownerRole` and `sellerType` are kept as they are; (d) `p1`-`p8` keep the same record count and the `p5`/`p7` "no CNIC" shape, so the rules that depend on a missing CNIC (`usable(property.cnic)`) behave as before.

## 4. Implementation steps (each independent, with its tests)

### S1 - Replace the data (R1). File: `frontend/js/data/properties.js`
Change only the 8 `owner:` and 6 `cnic:` values to section 3. No key added or removed. Add a one-line comment above the array: "Synthetic demo records: names start with 'Demo', CNICs start with 00000-. Real people's data must never be added here." Test: new `syntheticOwnerData.test.js` (section 6) plus the existing suites in F9.

### S2 - Replace the example placeholders. Files: `frontend/js/data/documentTypes.js` L18, L21; `frontend/js/features/property.js` L77
* L18 `ownerName` placeholder -> `e.g. Full name as written on the document` (no name at all).
* L21 and `property.js` L77 CNIC placeholder -> `e.g. 00000-0000000-0` (clearly the demo format).
Test: the same new scan test (placeholders are plain strings in public JS).

### S3 - Update the two tests that hard-code `p1` values (without weakening them)
* `tests/frontend/extraction.test.js`: 29 name and 25 CNIC literals (one of the CNICs is `p4`'s). Introduce one constant block at the top (`REC_OWNER`, `REC_CNIC`, plus derived confusable variants) with synthetic values and replace the literals. The **assertions stay identical** (same statuses, counts, messages). Where a test depends on specific digit confusions (`ocrConfusable`, `confusionKey`), the synthetic CNIC used by that test is chosen to contain the same confusable digit pairs (e.g. 0/8, 1/7, 5/6) and the variants are *derived programmatically* from the constant, so the confusion is still exercised. The implementer must show that each OCR-confusion case still hits the same branch (uncertain vs mismatch).
* `tests/frontend/verificationB1Review.test.js`: 4 CNIC literals (L99, L122-123, L160) -> synthetic constants; assertions unchanged (CNIC masking: first 5 digits and last digit rules must still be checked against a value that has a non-zero middle part, so the constant used there is `00000-0000101-0`-style, not all zeros).
Acceptance: both files keep their test counts (34 and 15) and all pass; the diff shows only literal substitutions plus the constant block.

### S4 - Hide owner identity from guests and signed-out visitors (smallest safe change). File: `frontend/js/features/property.js` (+ one line in `frontend/js/main.js`)
Current: owner card for everyone (F6). Proposed:
* In `renderDetail`, build the owner card with a small pure helper `ownerCardHtml(p, canSeeOwner)`. `canSeeOwner = isAccountSession()` (already exported by `services/sessionUser.js`; true only for a loaded registered user or admin).
  * `true` -> exactly today's card (avatar initials, name, `ownerRole . sellerType`).
  * `false` (guest, signed out, session still loading, failed lookup: **fail-closed**) -> a neutral card with the same `owner-card` classes: label "Listed by" + `p.sellerType` only, and the line "Log in or sign up to see the owner details." with the existing shared login prompt wiring (`showLoginRequired`, feature name "Owner details") on a button. No name, no initials, no `ownerRole`.
* Re-render once the session answer arrives so an account does not stay on the neutral card: in `main.js` add `loadSessionUser().then(() => { if (state.view === 'detail') render(); })` next to the existing `firstRoute`/history hooks (no new request: `loadSessionUser` is cached).
* No CSS change is required (reuse `.owner-card`, `.owner-name`, `.owner-role`; the project's strict-CSP test forbids inline styles, so none will be added).
* Public details are untouched: title, price, area, plot, size, scheme, description, photos, status, favourites, "Verify This Property".
Not changed: the gated verify/report pages (account-only; they now show the synthetic names), the owner-name API, chat.

### S5 - Documentation
`docs/KNOWN_ISSUES.md` (D5 / S4 entry: values are now synthetic, owner card hidden for guests, `properties.js` still public, S4 server-side plan still open), `docs/G6_PHASE2A2_PRIVACY_AUDIT.md` is left as the historical audit, `HANDOFF.md`, `work.md`, `CHANGELOG.md`, `docs/G6_PHASE2A3_REMEDIATION_PLAN.md` (completion record), and one sentence in `tests/manual/README.txt` if it names records.

### S6 - Private dataset: **no change** (item 6 of the brief)
`backend/datasets/*.csv` (16,000 rows with owner columns), `data-source/*.xlsx`, `notebooks/*.ipynb` stay exactly as they are. They are not served over HTTP (404 in the Flask test client) but they travel inside the project archive. Provenance and distribution are a **separate owner decision** (section 11, Q4). This plan adds a note in `KNOWN_ISSUES.md` that the archive still contains them and that replacing `p1`-`p8` does not address them.

## 5. Dependencies affected (checked)

| Area | Affected by S1-S3? | Affected by S4? |
|---|---|---|
| Public APIs (`/api/v1/listings*`, chat, owner-name check) | No (no owner fields; owner check uses the private dataset by id) | No |
| Document verification (`documentVerification.js`, `extraction.js`) | Behavioural: documents carrying the *old* `p1`-`p8` names/CNICs stop matching those records (intended); synthetic documents match as before | No |
| Sample documents (57 files) and the 29-entry manifest | No (F4); re-run `manifest-report` to confirm the "= 0" line | No |
| `home.js`, `featured.js`, `promo.js`, `propertyStatus.js`, `seed_demo_listings.py` | No (they do not read owner/cnic) | No |
| Gated views `verify`/`report` | Show new synthetic names; owner-name input pre-fill changes value only | No |
| Detail page (guest) | Shows synthetic name until S4 | **Yes**: neutral card for guests; account unchanged |
| a11y / CSP browser tests | No | Re-run `a11y_basics_test.py` and `csp_test.py`: the neutral card must keep an accessible name and add no inline style |
| Tests importing `PROPERTIES` (`homePrefs`, `propertyDisplayStatus`, `propertyUploadHonesty`) | No (ids/structure only) | No |
| Tests with literals | `extraction.test.js`, `verificationB1Review.test.js` (S3) | No |

## 6. Regression tests (new, exact)

**T1 `tests/frontend/syntheticOwnerData.test.js` (new file, no new dependency)**
1. *Scan of served and test text*: walk `frontend/**` and `public/**` (text extensions `.js .html .css .json .txt .md`), plus `tests/frontend/**` and `tests/fixtures/**`. Every CNIC-shaped value (`\d{5}-[\d*]{7}-\d`) must start `00000-`; in `tests/` only, the explicit allow-list prefixes `90000`, `90008`, `99000` are also accepted (deliberate mismatch values; adding a prefix requires editing the test). Bare 13-digit runs in served files must start `00000`.
2. *Record shape* (imports `properties.js`): every `cnic` matches `^00000-\d{7}-\d$`; every `owner` matches `^Demo (Owner|Company) [A-Z][a-z]+$`; the 8 owners are distinct; the CNICs are distinct and not among `DEMO_PROPERTIES` or any fixture CNIC; `p5`/`p7` still have no CNIC.
3. *Placeholders*: the `ph` strings in `documentTypes.js` and the CNIC placeholder in `property.js` contain no CNIC-shaped value other than `00000-`.
4. *Failure demonstration* (mutation check, run once by hand and recorded): re-inserting one old-style value makes test 1 fail; changing one owner to a non-"Demo" name makes test 2 fail.
**T2 `tests/frontend/propertyOwnerVisibility.test.js` (new, DOM stub as in `propertyUploadHonesty.test.js`)**: with the session stubbed as signed-out, guest, failed lookup and still-loading, `renderDetail('p1')` output contains no owner name, no initials block, no `ownerRole`, but still contains the title, price, area, plot, size and the sellerType; as registered user and admin it contains the owner card; `ownerCardHtml` fails closed for any non-account value (`null`, `{}`, unknown role); the "Log in" button uses the shared login prompt (no navigation, no request).
**T3 (optional, small) `tests/browser/guest_owner_privacy_test.py`**, registered in `.github/workflows/ci.yml`: as a guest open a detail page: the page text contains none of the 8 owner names and shows the "Log in or sign up" note; as a registered user the owner card appears after load (exercises the re-render hook); no console or CSP errors.
**Existing tests re-run, none weakened**: the ten files in F9, `npm test` (expect 397 + new), `manifest-report` ("= 0"), `a11y_basics_test`, `csp_test`, `camera_upload_test`, `tests.backend.test_ci_config`.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| OCR-confusion tests lose their meaning when digits change | S3 keeps the confusable digit pairs and derives variants from one constant; each case must hit the same branch; reviewer checks the diff |
| A real document of someone matching the *old* names will no longer "match" | Intended (those values were never confirmed fictional); note in KNOWN_ISSUES |
| UI-only hiding is bypassable by reading `/js/data/properties.js` | Stated plainly (F10); R1 removes the exposure itself; the S4 server-side plan stays open |
| Owner card flashes the neutral version for accounts while the session loads | Re-render hook (S4); T3 browser test; the failure mode is safe (hidden), not leaking |
| The old values remain in earlier archives (G4, G5, G6.1 ZIPs, `docs/G6_PHASE2A2_PRIVACY_AUDIT.md` masks only) | Cannot be fixed by this change; owner decides whether those archives must be withdrawn if the values turn out to be real |
| Over-strict scan test blocks legitimate future fixtures | Explicit allow-list for `9xxxx` mismatch prefixes, documented in the test header |
| Names "Demo Owner X" look odd in the demo UI | Cosmetic; alternative wording can be chosen at approval |
| `.xlsx`/notebook/private CSV still hold owner columns | Out of scope by instruction (S6); recorded as an open item |

## 8. Acceptance criteria (for the later implementation)
1. `GET /js/data/properties.js` contains no CNIC-shaped value outside `00000-` and no owner name that is not `Demo ...`.
2. The scan test T1 passes and was shown to fail on a re-inserted old-style value.
3. A guest or signed-out visitor sees no owner name, initials or role on any property detail page; registered users and admins still see the owner card; public property details are unchanged.
4. `npm test` passes (397 + new tests, 0 fail); `extraction` 34/34 and `verificationB1Review` 15/15 keep their counts; `manifest-report` still reports 0; `a11y_basics`, `csp`, `camera_upload` pass.
5. No change under `backend/`, `backend/datasets`, `data-source`, `notebooks`, migrations, authentication code, `extraction.js`, `documentVerification.js` or the owner-name API (verifiable by diff).
6. Docs record exactly what was done and what remains (S4 server-side plan, dataset provenance).

## 9. Out of scope (explicitly not done here)
Server-side document matching (S4 plan); removal or anonymisation of the 16,000-row dataset, the `.xlsx` or notebooks; the hard-coded "Verified" badge (D2); OCR comparison rules (D3/D4); the owner-name API's rate-limit scope, fail-open store and honorific stripping (D6); the fake "Saved" message (D7); any authentication, schema or CSP change.

## 10. Patch strategy
One patch from this baseline (G6.1 integrated + 2a-1), built so S1+S2 (data), S3 (tests), S4 (guest hiding), S5 (docs) apply in that order and can each be reverted alone. S1 and S3 must ship together (S1 alone leaves two tests holding old literals; they would still pass but the scan test would fail).

## 11. Owner approvals needed before implementation
1. **Q1 Data:** approve section 3 (names `Demo Owner <NATO word>`, CNIC `00000-00001NN-0`) or give different synthetic values. If you can instead confirm in writing that the current values were invented, say so: S1/S2/S3 become optional and the plan reduces to S4 + T1 on the *existing* values (then T1's allow-list would need a documented exception).
2. **Q2 Guests:** approve hiding the owner card from guests and signed-out visitors (S4), keeping `sellerType` visible. Should registered users keep seeing the (synthetic) owner name?
3. **Q3 Scope of T3:** include the optional browser test and its CI registration?
4. **Q4 Dataset:** the private 16,000-row owner dataset, `.xlsx` and notebooks are left untouched; confirm that provenance and archive distribution will be decided separately.
5. **Q5 Older archives:** if any of the old values prove to be real, do you want a note added to the handoff about withdrawing earlier ZIPs?

**STOP: awaiting approval. Nothing in the application has been modified.**
