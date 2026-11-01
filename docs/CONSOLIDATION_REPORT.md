# KPT archive comparison and reconciliation plan

Archives (all extracted read-only under `/home/claude/cmp/`; originals untouched):
| Label | Archive | Files | Notes |
|---|---|---|---|
| S26 | `kpt-session26-checkpoint.zip` (baseline, not one of your three) | 479 | Phase B.1 + Session 26 fixes + `dev_skip`; no T1-T4 |
| A | `kpt-session26-T4.zip` (inside `files.zip`, from your other AI) | 490 | S26 + T1-T4 (its own T4 implementation) |
| B | `kpt-phaseB1-inprogress.zip` | 474 | Session 25 + Phase B.1 working changes, **without** `dev_skip.py` and without Session 26 fixes |
| C | `kpt-session26-T4-wip.zip` (my earlier T4 work in progress) | 488 | S26 + T1-T3 (identical backend to A) + my partial T4 |
| - | `files.zip` extras | - | `phaseB1-review.diff` (a Phase B.1 REVIEW patch), A's `work.md`/`HANDOFF.md` (identical to the copies inside A) |

## 1. Which archive is most complete
**A.** Evidence (actually run in this audit, in place, no bytecode): `npm test` 206/206; backend 318 run, 1 error = `test_admin_totp` (`pyotp` not installed, environment); browser 17 of 18 pass (smoke, login, login_busy, developer_login, guest_entry, csp, a11y_basics, cookies, creators, featured, listing_lifecycle, listings, messaging, prefs, property_images, signup_single_click, camera_upload); `admin_totp_test` cannot run here. C (from my earlier runs): npm 200/200, backend 316 run with the same 1 error, 17 browser OK.
B and S26 contain no Developer Login, Guest, or login-first code. B is a strict subset of S26 (every B file exists in S26; B-only lines are older forms that Session 26 replaced).

## 2. Relationships found
* **Backend: A and C are byte-identical** except `backend/web.py` (they share my T1-T3 code; they diverged at T4).
* **Phase B.1 verification code is identical in S26, A, B, C** (27 of 29 checked files byte-identical; the two that differ are `docs/PROJECT_PHASE_AUDIT.md` and C's `messaging.test.js`).
* Assets, migrations, datasets, scripts, notebooks: identical in all trees (no differences listed).
* **`phaseB1-review.diff` is NOT applied in any archive** (`verifyAgainstRecords`, `areaInSqYards`, `verificationB1Review.test.js` exist nowhere). It applies cleanly (dry run, 0 rejects) to S26, A and B. It contains the three Phase B.1 review fixes you named: unit-aware area comparison, CNIC masking in reasons/uncertainty text/limitations, and one shared `verifyAgainstRecords` used by both the app and `scripts/manifest-report.mjs`, plus new unit tests. **Choosing any single archive would lose it.**

## 3. Feature matrix
| Feature | S26 | A | B | C |
|---|---|---|---|---|
| Phase B.1: CNIC masked in stored history (`sanitizeResultForStorage`) | yes | yes | yes | yes |
| Phase B.1 review: masked CNIC in reasons/limitations, unit-aware area, shared rule with manifest-report | no | **no** | no | no (only in the diff) |
| Session 26 scanner fixes (bandit hardening, `import os` fix needed in `app.py`) | yes | yes | no | yes |
| Developer Login endpoint + page | no | yes | no | yes |
| Guest sessions backend (restricted, cleanup, admin exclusion) | no | yes | no | yes |
| Login-first routing | no | yes, `private_page` + `Cache-Control: private` + `Vary: Cookie`, also gates `/index.html` | no | yes (`_login_first`, no cache headers) |
| `/messages` return path encoded (no duplicate `next`) | n/a | **no** (`safe="/?=&"`) | n/a | **yes** |
| Guest UI | no | yes: locked button with spinner, trusts only a real `role: guest`, exported helpers + 7 JS tests, mobile header overflow fix, owner-check guest message, helper `sessionUser.js` | no | yes, simpler: nav Guest/Create account/Exit guest, `need=account` banner |
| Guest browser test | - | `guest_entry_test` (28 checks, in CI) | - | `guest_login_first_test` (30 checks, in CI) |
| `.env.example` | yes | **missing** | yes | **missing** (my zip pattern `*/.env.*` excluded it; A lacks it too) |
| `dev_skip` (`admin__01`) | yes | yes | **removed** | yes |
| Cryptography pin | `>=50` (deliberate, pip-audit) | same | `==46.0.6` (9 known CVEs) | same as A |
| HANDOFF | long | 844 lines | long | compact + `docs/HANDOFF_ARCHIVE.md` |

## 4. Conflicts that cannot be merged automatically
1. **Same T4 UI implemented twice** (`auth-page.js`, `authNav.js`, `sellerChat.js`, `login.html`, `listings.html`, `listings-page.js`, `privacy-page.js`, `verificationApi.js`, `web.py`, tests). Taking both would duplicate handlers. Decision: keep A's (more complete, more tested).
2. **Chat with seller for a guest:** A keeps the guest on the page with Log in / Sign up links; C redirects to login with an explanation banner. Owner decision; default A.
3. **Guest nav labels:** A "Guest / Log in / Sign up / Exit"; C "Guest / Create account / Exit guest". Default A.
4. **Open product decisions (unchanged, not merge issues):** V3 POA ending `verified`, V4 `suspicious` status, V7 free-search matching.

## 5. What would be lost by picking one archive
* Pick A alone: lose the B.1 review fixes (diff), the `/messages` return-path encoding, the compact handoff + archive, `.env.example`.
* Pick C alone: lose A's cache headers on private pages, `/index.html` gating, A's guest button hardening and tests, mobile overflow fix.
* Pick B alone: lose Session 26 fixes, `dev_skip`, Developer Login, Guest, login-first, and it keeps the vulnerable `cryptography==46.0.6` pin.

## 6. Reconciliation plan
**Base: A.** Merge into `/home/claude/cons/kpt` (a copy; A and the others stay untouched).
| Step | Change | Source | Test after |
|---|---|---|---|
| M1 | Copy A as base | A | `npm test`, backend (expect 206 / 318+1 err) |
| M2 | Restore `.env.example` (placeholders only) and add placeholders for the guest settings | S26 + new lines | `test_dependencies`/config tests; secret-shape scan |
| M3 | Apply `phaseB1-review.diff` (unit-aware area, CNIC masking, `verifyAgainstRecords`, manifest-report, new test file) | files.zip | `npm test` (new tests), `node scripts/manifest-report.mjs` consistency check, verification browser view in `smoke` |
| M4 | `/messages` return path: `safe="/"` + `ReturnPathTests` in a new small test file (no overwrite of A's `test_login_first.py`) | C | `test_login_first`, `test_api`, new tests |
| M5 | Docs: compact `HANDOFF.md`, move A's long history and C's archive into `docs/HANDOFF_ARCHIVE.md` (verbatim), `HANDOFF_NEXT.md`, `work.md`, `CHANGELOG.md` entries, `KNOWN_ISSUES.md` (V5 resolved, camera_upload upload-step gap) | A + C | doc-consistency (`test_ci_config`) |
| M6 | Regression: `npm test`, full backend, all 17 browser tests in batches | - | record actual numbers |
| M7 | Package `karachi-property-trust-consolidated.zip` (one `kpt/`, exclude secrets, sqlite, `.local`, caches, `node_modules`, venvs; KEEP `.env.example`), `unzip -t`, listing check | - | - |

**Not merged (outdated, duplicate or harmful):** B's `cryptography==46.0.6` pin and the B-only older lines; C's `_login_first`, `auth-page.js`, `authNav.js`, `sellerChat.js`, `listings*`, `privacy-page.js`, `login.html` (superseded by A's); C's `guest_login_first_test.py` and the C-specific guest case in `messaging.test.js` (they assert C's UI labels and would fail against A's UI); B's removal of `dev_skip` (a regression).

## 7. Outcome (what was actually done and run)
Base A; M1-M7 executed as planned, with these additions found while merging: `.env.example` comment updated (it still described the removed "Skip login" button); `tests/browser/listings_test.py` race fixed (A itself failed 1 of 12 runs; 15/15 after); new `tests/browser/guest_entry_failures_test.py` so C's 429 / network-failure / double-click checks are not lost (C's `guest_login_first_test.py` itself asserts C's UI labels and was not merged).
Results, actually run in this consolidation: `npm test` 221/221; backend 321 run, 1 error (`pyotp` missing, environment); browser 18/18 runnable tests pass (`admin_totp_test` not runnable); `node scripts/manifest-report.mjs`: OCR 18/29 anchored, 17/29 application path, PDF 28/28, 0 "verified although expected otherwise". Not verified: PostgreSQL, TOTP, live Google/Resend/AI, real scans, Vercel routing, dependency scans.
