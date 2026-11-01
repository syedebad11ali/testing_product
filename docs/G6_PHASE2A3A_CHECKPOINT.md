# G6.2a-3 Part A checkpoint - synthetic owner data (S1, S2, S3, T1)

**RECONSTRUCTED, not recovered.** The previous session's working directory (`/home/claude/work/kpt`) did not exist. Parent state rebuilt here: `karachi-property-trust-G6_1-integrated.zip` (SHA-256 `ef8f7052bcdb1af350827db6082cbfcb9d38a224e0799a179716f74911291a59`, verified) + `g6-phase2a-1.patch` applied exactly once (dry run first; its 7 tests pass). The supplied archives were not modified. The RAR is two concatenated RAR5 archives; it was read with the system `libarchive` via `ctypes` (no RAR tool is installed).

## Changes
| File | Change |
|---|---|
| `frontend/js/data/properties.js` | only the 8 `owner` and 6 `cnic` values of p1-p8, plus a one-line comment; no key added or removed |
| `frontend/js/data/documentTypes.js` | owner-name placeholder -> `e.g. Full name as written on the document`; CNIC placeholder -> `e.g. 00000-0000000-0` |
| `frontend/js/features/property.js` | CNIC input placeholder only (`00000-0000000-0`) in this part |
| `tests/frontend/extraction.test.js` | literal substitution only (see below); 34 tests, assertions untouched |
| `tests/frontend/verificationB1Review.test.js` | literal substitution only; 15 tests, assertions untouched |
| `tests/frontend/syntheticOwnerData.test.js` | new, 9 tests |

## Synthetic values
p1 Demo Person Alpha 00000-0000101-0; p2 Demo Person Bravo ...0102-0; p3 Demo Person Charlie ...0103-0; p4 Demo Person Delta ...0104-0; p5 Demo Company Echo (none); p6 Demo Person Foxtrot ...0106-0; p7 Demo Company Golf (none); p8 Demo Person Hotel ...0108-0. `Demo Owner` is deliberately NOT used (the extractor treats "owner" as a field label).

Test literals: the old p1 document name -> `Demo Person Alpha` (29, and the lower-case form 2x); the old p1 CNIC -> `00000-0000101-0` (23 in extraction, 4 in B1); bare 13-digit form -> `0000000001010`; OCR-letter form (`I`/`O` for 1/0, both confusions still present) -> `000OO-0000I0I-0`; the two non-record CNICs -> `00000-0000202-0` (duplicate-conflict case) and `00000-0000201-0` (second record); masked expectation -> `00000-******1-0` (keeps a NON-zero visible digit so the masking rule is still exercised).

## Verification compatibility
* Per-test comparison, G6.1 + 2a-1 tree vs this tree (TAP names, order, ok/not ok): extraction 34/34 identical, B1 15/15 identical.
* Differential script (outside the project): 12 documents derived from p1 (exact, name only, bare digits, lower case, OCR I/O letters, one confusable digit off, one hard digit off, two digits off, wrong plot, other owner with the same CNIC, two different CNICs, nothing readable) x `ocr` false/true = 24 cases through `parseDocumentText` + `verifyAgainstRecords`: **0 differences**; all four verdicts (`verified`, `not_verified`, `unable_to_verify`, `suspicious`) occur. `extraction.js` / `documentVerification.js` untouched.
* `node scripts/manifest-report.mjs` output identical to the baseline (108 lines).
* `npm test` 406/406 at the end of Part A (397 + 9).

## Scanner test and mutation check
`syntheticOwnerData.test.js` scans `frontend/`, `public/` (incl. the sample datasets), `tests/frontend/`, `tests/fixtures/` for formatted, masked and bare (13 digits on a CNIC line or under a CNIC CSV header) values; only `00000-` is allowed, tests/fixtures may also use the documented mismatch prefixes `90000`, `90008`, `99000`. Failures print file:line and a masked value. Self-tests: old-style value caught in all three forms; a timestamp ("not an identifier") is not flagged; a planted value in a temp tree is found. It also hashes the 8 removed owner names (SHA-256) so a returning name is caught without storing it. Fixes against the previous draft: owner regex accepts `Demo Person|Company`; the timestamp self-test says "not an identifier"; real exports (`DOC_FIELD_DEFS`, `SAMPLE_DOCS`, `DEMO_PROPERTIES`) are used.
Mutation checks (scratch copies, each must fail): old CNIC back in `properties.js` -> fails; non-Demo owner -> fails; old CNIC in a test file -> fails; old name in a frontend comment -> fails (hash test); bare digits in a public CSV with a CNIC column -> fails; old placeholder back -> fails; duplicate CNIC -> fails; CNIC added to p5 -> fails. **8/8 caught.**

**Not run / not verified:** the other browser tests (messaging, cookies, login, smoke, listings, prefs, admin_totp, google_button, property_images, ...); live OCR and PDF.js reading (the libraries are not vendored and there is no network, so only the offline "could not be loaded" path was exercised); PostgreSQL; live Google sign-in; a real WinRAR open of the ZIP (standard ZIP integrity only).
