> **Consolidated tree: Session 26 + T1-T4 (other AI's T4) + Phase B.1 review fixes + return-path fix + `.env.example` restored. T5 is next. Consolidation record: section 10.**
>
> Origin note: an earlier copy of this file came from a different tree; T1-T3 were re-implemented natively on the Session 26 checkpoint and verified (see `HANDOFF.md`).

# work.md — Karachi Property Trust: login-first / Developer Login / Guest / consent plan

Legend: **[C]** confirmed from source or a test run; **[A]** assumption (stated, to be verified).
Memory across runs = this file + the "CURRENT STATE" section at the top of `HANDOFF.md`.
Standing owner decisions (`docs/HANDOFF_NEXT.md`): the `admin__01` dev shortcut is deliberate (local only, 404 in prod, never weaken); the 8 sample records in `properties.js` are fictional.

## 1. Project Goal
1. No valid session -> the main login page appears first.
2. "Developer" opens a separate admin username/password page; valid authorised admin -> admin dashboard; anything else -> Nice Try page, no access.
3. "Continue as Guest" -> restricted guest session (no admin power, no private data).
4. Google login works (subject to external OAuth config).
5. Cookie-consent UI appears after a successful login (incl. Google) when no choice is recorded.
6. Pages and APIs enforce permissions server-side; direct URLs, frontend tampering and legacy bypasses give nothing.
7. Existing property features keep working.

## 2. Current-State Analysis (what actually exists)
| Area | Behaviour today | Evidence |
|---|---|---|
| Stack | Flask 3.1 + static ES-module frontend; SQLite local, PostgreSQL prod; Vercel. [C] | `backend/app.py`, `vercel.json` |
| `GET /` | Serves `index.html` to anyone, no session check. [C] | `backend/web.py` `index()` |
| Other pages | `/messages` redirects to `/login?next=` without a session; `/admin` requires admin role and no pending password change; `/listings`, `/privacy`, `/nice-try`, `/login` public. [C] | `web.py` |
| Login page | `login.html`: login/signup/forgot/reset, Google button, and a **"Skip login (dev only)" toggle** that re-targets the same form to `/auth/dev-skip`. [C] | `login.html:59`, `auth-page.js:244-259` |
| Dev skip | `POST /auth/dev-skip`: all inputs -> `/nice-try`, except `admin__01` + `DEV_ADMIN_PASSWORD` -> `/admin`; 404 in production; refused with a shared DB; empty password never matches. 9 tests. [C] | `services/dev_skip.py`, `api/auth.py` |
| Normal login | `POST /auth/login`: wrong password for `admin_001` -> Nice Try redirect; wrong credentials for anyone else -> 401. [C] | `api/auth.py`, `auth_service.py` |
| Admin | `admin_001` seeded from `ADMIN_001_PASSWORD`; 19 admin routes all `@role_required("admin")`; TOTP optional/off. [C] | `db/seed.py`, `api/admin.py` |
| Roles | Only `user`/`admin`; `users.role` is TEXT without CHECK. [C] | `admin.py:22`, `0001_auth.sql` |
| Guest | At the start of T3 nothing existed (0 hits for "guest"). Now: backend done (T3); **no frontend/UI yet** (T4). [C] | grep; `test_guest.py` |
| Google | `/auth/google/config` + `/auth/google` implemented with nonce/aud/iss/exp/email_verified checks; 5 tests pass with a fake verifier; never live-tested; `google-auth` not installed here. [C] | `auth.py`, `google_oauth.py`, prior audit |
| Cookie consent | `initConsent()` shows the banner at **page load** on every page incl. `/login`, whenever no choice is stored. [C] | `consent.js:25`, `consent-banner.js`, `main.js:23` |
| Private APIs | Messaging, my listings, verification, prefs, devices are `@login_required`; `GET /listings`, chat, health are public. [C] | `api/*.py` |
| Baseline tests | This tree: backend 272 at the Session 26 checkpoint; 282 after T1; 286 after T2; **302 after T3**, always with the same 1 error (`test_admin_totp`, `pyotp` missing). JS 199/199 (unchanged). [C] |

## 3. Gap Analysis (per requirement)
| Req | Current | Desired | Gap | Solution | Acceptance test |
|---|---|---|---|---|---|
| R1 Login first | **DONE (T4)**; was: `/` public | no session -> `/login` | missing; needs Guest first or visitors are locked out | `web.py` redirect for `/` (+ `/listings`) when `current_session()` is None | Flask client: anon `GET /` = 302 `/login`; user/guest = 200 |
| R2 Developer Login | **DONE (T1 backend re-done + T2 page)**; the login-page toggle is now a link | separate page; valid admin -> `/admin`; all else -> `/nice-try`, no session | none (live-browser verified) | T1 `POST /auth/developer-login` (admin-only, lockout/audit shared); T2 page `/developer-login` + link on login page | backend tests (done); Playwright: valid -> `/admin`, invalid -> `/nice-try`, no cookie |
| R3 Guest | **DONE (T3 backend + T4 button/UI)** | restricted guest session | UI only | T3 `POST /auth/guest`: `role='guest'` row + short session; guards deny guests on private/write/admin routes; hidden from admin lists; cleanup | guest hits every `login_required` and admin route -> 401/403; `/auth/me` role guest |
| R4 Google | coded, never live | works with correct config | config + live test (owner); `google-auth` not pinned/installed | T6: local verification, fix defects, document exact Console steps | existing 5 tests; live round-trip = manual |
| R5 Consent after login | banner on load incl. login page | after login only | behaviour mismatch | T5: skip banner on login/developer/nice-try pages; show on first page after login/guest entry | cookies_test updated; banner absent on `/login`, present after login |
| R6 Security | route guards good; no guest role; legacy dev-skip button is a UI toggle | no bypass via URL/API/frontend | verify with guest role; keep dev-skip limits | T3/T4 tests parametrised over all routes | route-matrix test |
| R7 Preserve | 271 backend / 199 JS / browser tests | unchanged green | risk: first-visit flow changes browser tests | update fixtures to log in/guest first; run CP1 | full suites |

## 4. Proposed Changes (files / routes)
- `backend/services/auth_service.py`: `login(..., admin_only=True)` — **done (re-implemented in T2 run)**; later `guest_login()`.
- `backend/api/auth.py`: `POST /auth/developer-login` — **done**; later `POST /auth/guest`; `/auth/features` adds `developer_login` (done), `guest`.
- `backend/security/guards.py`: guest-aware `login_required` (guests rejected unless `allow_guest=True`) — **done (T3)**.
- `backend/services/session_service.py`, `config.py`, new `guest_service.py`: guest session limits + cleanup — **done (T3)** (cleanup lives in `guest_service`, not `retention_service`).
- `backend/api/admin.py`, exports, admin session view: exclude `role='guest'` — **done (T3)**.
- `backend/web.py`: `/developer-login` **done (T2)**; login-first redirects (T4).
- `frontend/developer-login.html`, `frontend/js/developer-login.js` (new, **done**); `login.html`, `auth-page.js`, `login.css`: Developer link **done**; Guest button (T4).
- `frontend/js/features/consent.js`, `consent-banner.js`, `main.js`: post-login consent.
- Docs: `docs/AUTH.md`, `docs/COOKIES.md`, `SECURITY.md`, `CHANGELOG.md`.

## 5. Implementation Tasks (one per run)
| ID | Task | Depends | Status |
|---|---|---|---|
| **T1** | Developer Login backend + tests | - | **COMPLETE** (found MISSING from kpt.zip at the start of the T2 run; re-implemented there, see HANDOFF) |
| T2 | Developer Login page + login-page link (replace toggle button; keep `/auth/dev-skip` working) | T1 | **COMPLETE** |
| T3 | Guest session backend + guard changes + admin exclusion + cleanup + route-matrix tests | T1 | **COMPLETE** |
| T4 | Guest button + login-first gating of `/` and `/listings`; restricted guest UI | T2, T3 | **COMPLETE** |
| T5 | Cookie consent after login | T4 | **COMPLETE** (T5a/T5b ported into v2; see section 12) |
| T6 | Google OAuth readiness + docs | T4 | T6a **DONE** (tests + origin docs ported); T6b = owner live check, **BLOCKED** |
| CP1 | Regression checkpoint (npm test, full unittest, browser tests) | T1-T5 | results in section 12 (run on v2 after the port); final ZIP not built |
| T7 | Docs, final audit, final ZIP | all | todo |

## 6. Testing Plan
Targeted per task (Flask test client `tests/backend/*`, Playwright `tests/browser/*`); full suites only at CP1/T7. Per requirement: R1 route test; R2 backend tests + browser test; R3 route matrix + `/auth/me`; R4 existing Google tests + manual live check; R5 browser cookies test; R6 matrix of every route x {anonymous, user, guest, admin}; R7 `npm test` (199), `unittest` (baseline 271 / 1 env error), browser suite (15).

## 7. Risks and Blockers
- [C] `pyotp`, `google-auth`, `psycopg`, PostgreSQL unavailable here: TOTP, live Google and Postgres paths cannot be verified in this sandbox; **production-mode login is only checkable on settings level**.
- [C] Google needs `GOOGLE_CLIENT_ID` and an authorised JS origin in Google Cloud Console (owner action).
- [A] Guests may read listings, use the chatbot and property search; no messaging, listing creation, document verification, prefs or devices. Confirm with owner.
- [C] Gating `/` changes the first-visit flow: existing browser tests (smoke, listings, etc.) must log in or use guest first.
- Guest rows in `users` must not appear in admin lists and must expire.
- Do not set `DEV_ADMIN_PASSWORD` on Vercel; `ADMIN_001_PASSWORD` must be strong in prod.

## 8. Acceptance Criteria
1. Anonymous `GET /` -> 302 `/login`.
2. `/developer-login` is a separate page; valid admin -> `/admin`; every invalid attempt -> `/nice-try` with no session cookie.
3. "Continue as Guest" creates a server-side guest session denied by every private/admin endpoint (tested).
4. Admin APIs return 401/403 to anonymous, normal user and guest.
5. Google path tested locally; manual configuration documented accurately.
6. Consent banner absent on login pages, shown after login/guest entry when unrecorded.
7. All new tests pass; existing suites pass except the documented `pyotp` environment error.
8. `work.md`/`HANDOFF.md` match the final code.

## 9. Deviations from the plan (T2 run)
- [C] T1 was NOT in `kpt.zip` (no `developer-login`/`admin_only` anywhere, backend 262 tests not 271). Re-implemented to the planned shape. If the owner has a separate tree with the original T1, diff it against this one before merging.
- [A] The Developer page omits `consent-banner.js` (end state wanted by T5; the main `/login` page is unchanged until T5).
- [A] In development, the Developer page sends username `admin__01` to `/auth/dev-skip` so the owner's shortcut stays reachable after the toggle was removed. Server limits unchanged.
- The `/developer-login` page is public by design (it is a login form); access control is the server session on `/admin` and `/api/v1/admin/*`. Only a valid admin session is redirected away from it.
- [C] T3: guest cleanup is in the new `guest_service.py` (opportunistic + on logout), not in `retention_service.py`, which is for messages and is disabled by default. Guest entry is not written to `login_events`. Guests also cannot use `allow_guest` routes yet because none exist; the R3 assumption (guests may browse listings and use the chatbot) holds because those routes are public anyway.

## 9b. T4 run: actual changes, acceptance results, deviations
**Changed.** `backend/web.py` (`private_page()` gate for `/`, `/index.html`, `/listings`, `/listings.html`; fixed `next` value; `Cache-Control: private, no-cache` + `Vary: Cookie`); `frontend/login.html` + `js/auth-page.js` (Guest button, `guestDestination`, `guestErrorMessage`, guests see the login forms); new `js/services/sessionUser.js`; `js/features/authNav.js` (Guest badge, Log in/Sign up, Exit); `js/listings-page.js` + `listings.html` (no create form / personal listings / Messages link for guests, Guest badge); `js/features/sellerChat.js` (guest -> prompt + login/sign-up links, no API call); `js/features/ownerVerification.js` + `js/services/verificationApi.js` (owner-name check replaced by a prompt; clear message on `guest_not_allowed`); `js/privacy-page.js` (account panel hidden for guests); `css/layout.css`, `css/auth.css` (badge, narrow-screen rules); `.github/workflows/ci.yml`; docs.
**Tests.** New: `tests/backend/test_login_first.py` (16), `tests/frontend/guestEntry.test.js` (7), `tests/browser/guest_entry_test.py` (28 checks), helper `tests/browser/support/session_entry.py`. Adapted (assertions kept): `test_api.test_static_site_routes`; browser tests `smoke, camera_upload, creators, featured, messaging, cookies, csp, a11y_basics, prefs, property_images` now enter through the real Guest button.
**Acceptance (from section 8).** 1 PASS (`test_login_first`, `guest_entry_test`). 3 PASS for the guest session and UI (`guest_entry_test`, `test_guest`, `test_login_first`). 4 PASS (guest/user get 401/403 from admin APIs; `test_login_first`, `test_guest` matrix, browser 403 checks). 2 PASS (developer login unchanged: `test_developer_login` 13, `developer_login_test`). 5, 6 (Google, consent) are T5/T6, untouched. 7 PASS apart from the `pyotp` environment error.
**Deviations / findings (all [C] unless marked).**
- The first browser run found a real regression of my own: the guest header made the home page scroll sideways at 375 px (`scrollWidth 380 > 375`); fixed (narrow screens keep Guest badge + Log in, hide Exit), verified at 375/360/320 px. The signed-out header on the pre-T4 tree already fit at 320 px.
- `a11y_basics_test` and `csp_test` would have audited the *login page* instead of the app once `/` redirects; they now audit as a guest.
- Browser test servers run with `GUEST_MAX_ACTIVE_PER_IP=1000`: a full suite creates more than the default 10 guests per IP. The product default is unchanged and the limit itself is tested (`test_guest`, `test_login_first`, `guest_entry_test` with a cap of 1).
- A guest who then logs in or signs up gets a new session; the old guest row stays until its idle expiry (15 min) or cleanup and counts toward the per-IP cap meanwhile. Not changed.
- The in-browser document analysis (no server call, fictional records from `properties.js`) is left available to guests; only the server-backed owner-name check is replaced by a prompt. [A] confirm this is the intended guest scope.
- `vercel.json` has no static rewrites, so `/` should reach Flask on Vercel; **not verifiable here**.
- The cookie banner still shows on every page load including `/login` (T5 will change that). `cookies_test` assertions about consent were not changed.

## 10. Consolidation record (three archives reconciled into this tree)
**Inputs** (all extracted read-only, originals untouched): A = `kpt-session26-T4.zip` (inside `files.zip`), B = `kpt-phaseB1-inprogress.zip`, C = `kpt-session26-T4-wip.zip`; baseline S26 = `kpt-session26-checkpoint.zip`; plus `phaseB1-review.diff`. Full comparison: `docs/CONSOLIDATION_REPORT.md`.
**Findings [C].** A and C share byte-identical backend except `web.py`; Phase B.1 verification code is identical in S26/A/B/C; B is a strict subset of S26; the review diff was applied in none of them; `.env.example` was missing from A and C; A's T4 is more complete (cache headers + `/index.html` gate, hardened guest button, 7 extra JS tests, mobile fix) but kept the unencoded `/messages` return path.
**Merged.** (1) `phaseB1-review.diff` (applies cleanly): `documentVerification.js`, `extraction.js` (`areaInSqYards`, `verifyAgainstRecords`), `resultPrivacy.js`, `verifyDocument/views.js`, `scripts/manifest-report.mjs`, new `tests/frontend/verificationB1Review.test.js`. (2) `backend/web.py`: `/messages` return path `safe="/"`; new `tests/backend/test_return_path.py` (3 tests). (3) `.env.example` from S26 (comment updated for Developer Login) + `GUEST_*`. (4) `tests/browser/listings_test.py`: wait for `#browse li` before the exact count (intermittent race, 1 failure in 12 runs on A itself; 15/15 after); new `tests/browser/guest_entry_failures_test.py` (6 checks: 429, network failure, double click; registered in CI) because C's equivalent checks had no counterpart in A. (5) `docs/HANDOFF_ARCHIVE.md` (verbatim history, Parts A-F), compact `HANDOFF.md`/`HANDOFF_NEXT.md`, `CHANGELOG.md`, `docs/KNOWN_ISSUES.md`.
**Deliberately NOT merged.** B's `cryptography==46.0.6` (9 known CVEs; S26 moved to `>=50`, still "PIN ME"); B's removal of `dev_skip`; C's `_login_first`, `auth-page.js`, `authNav.js`, `sellerChat.js`, `listings*`, `privacy-page.js`, `login.html`, `guest_login_first_test.py` and the guest case in `messaging.test.js` (superseded by A's, would assert C's labels).
**Results [C], actually run.** npm 221/221; backend 321 run, 1 error (`pyotp` missing); browser 18/18 runnable tests pass; manifest-report OCR 18/29 anchored, 17/29 application path, PDF 28/28, 0 "verified although expected otherwise". Not verified: PostgreSQL, TOTP, live Google/Resend/AI, real scans, Vercel routing, dependency scans.
**Owner decisions pending.** Guest Chat-with-seller UX (A stays on page with links; C redirected with a banner); V3/V4/V7 verification decisions; key rotation.

## 11. Final archive verification + guest->account transition (post-consolidation)
Archive `karachi-property-trust-consolidated.zip` verified (valid, 549 files, one `kpt/` root, `.env.example` included, no secrets/db/caches/venvs). Guest->account transition was absent; implemented in `_start_session` (`backend/api/auth.py`) with `tests/backend/test_guest_transition.py` (5 tests; fail without fix, pass with it). Related tests run: 91 backend OK; browser `guest_entry`, `guest_entry_failures` OK. Not run: JS, full backend, other browser. Existing `test_guest` cleanup counts adjusted. New archive `karachi-property-trust-consolidated-v2.zip`. Lineage gap: T5a/T5b/T6a/CP1 work from the earlier tree is not in this tree; T5 stays open here. T5/T6 not started. Blockers unchanged: PostgreSQL, TOTP (`pyotp`), live Google/email/AI, real scans OCR/PDF, Vercel routing, dependency scans.

## 12. T5a/T5b + T6a ported into the consolidated v2 tree (canonical)
**Source:** earlier working tree (T5a/T5b/T6a/CP1), merged file by file into v2; v2's own tests, helpers and UI kept. **Code:** `frontend/login.html`, `frontend/developer-login.html` (banner script removed). **Tests:** `tests/backend/test_cookies.py`, `tests/backend/test_auth.py` (+3 Google), `tests/browser/cookies_test.py` (+sections 0, 6), new `tests/browser/helpers/fake_google_server.py`, `tests/browser/support/session_entry.py` (dismiss after guest entry), `prefs_test`, `signup_single_click_test`, `listings_test`, `listing_lifecycle_test`, `admin_totp_test` (edited, compiled, NOT executed: `pyotp`). **Docs:** `docs/COOKIES.md`, `docs/AUTH.md`, `CHANGELOG.md`, `HANDOFF.md`, `docs/HANDOFF_NEXT.md`, `work.md`.
**Results (actually run, v2 tree):** `npm test` 221 run / 221 pass; backend `unittest discover` 329 run, 0 failures, 1 error = `test_admin_totp` import (`pyotp` missing; TOTP unverified); `GoogleTests` 11 OK; browser, each `timeout 90`: a11y_basics, camera_upload, cookies (24 s), creators, csp, developer_login, featured (34 s), guest_entry, guest_entry_failures, listing_lifecycle, listings, login, login_busy, messaging, prefs, property_images, signup_single_click, smoke = 18/18 OK; `admin_totp_test` not runnable.
**Unresolved/unverified:** live Google sign-in (needs owner OAuth client + exact origins + `google-auth`); production origin `https://karachi-property-trust-55s4.vercel.app` unconfirmed; `google-auth` pin ("PIN ME"); PostgreSQL; TOTP; real OCR/PDF extraction (`camera_upload_test` does not reach the file input: upload step sits behind the document-type chooser, a test-coverage gap, not an app regression); live email/AI; Vercel routing; dependency scans. Owner decisions still open: guest Chat-with-seller UX, V3/V4/V7, key rotation. No deploy, no push, no final ZIP yet.

## 13. Final package
`karachi-property-trust-final.zip` built from the merged v2 tree (no older ZIP as base, no features/tests removed). **Remaining limitations (not verified, not marked complete):** TOTP tests (`pyotp` missing; `test_admin_totp` import error, `admin_totp_test` not executed); live Google OAuth (fake verifier only; production origin unconfirmed; `google-auth` pin open); PostgreSQL (all SQL ran on SQLite); real OCR/PDF extraction; `tests/browser/camera_upload_test.py` still does NOT reach the file input (`file inputs present: 0`), so its upload branch has not been tested and the test must not be described as a successful upload test; production Vercel routing; live email/AI; dependency scans (`pip-audit`/`bandit`/`ruff`/Lighthouse not run).
