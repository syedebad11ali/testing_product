# Changelog
Reconstructed from `HANDOFF.md` (the archive has no git history). Newest first.

## Unreleased - Final consolidated package
- Packaged `karachi-property-trust-final.zip` (merged v2 + T5a/T5b + T6a). No code changes in this step; docs record the remaining unverified items (TOTP, live Google, PostgreSQL, real OCR/PDF, camera_upload upload branch, Vercel routing, live email/AI, dependency scans).

## Unreleased - T5a/T5b + T6a ported into the consolidated tree (v2 canonical)
- **Cookie consent after sign-in (T5a/T5b):** `consent-banner.js` removed from `frontend/login.html` and `frontend/developer-login.html` (`nice-try.html` never had it). The banner now first appears on the page after password login, sign-up, Google sign-in or Continue as guest, only when no current choice exists; consent code, cookie format, policy version and Accept/Reject parity unchanged. First-visit Remember me still gets no token (`remember_note`). Docs: `docs/COOKIES.md`, `docs/AUTH.md`.
- **Tests:** `tests/backend/test_cookies.py` page assertions; `tests/browser/cookies_test.py` gained section 0 (entry pages quiet; banner after sign-up, password login, guest; saved choice not reopened) and section 6 (Google with a fake verifier, `tests/browser/helpers/fake_google_server.py`; not live Google); shared helper `tests/browser/support/session_entry.py` now dismisses the banner after guest entry; `prefs`, `signup_single_click`, `listings`, `listing_lifecycle`, `admin_totp` (not runnable here) no longer wait for a banner on `/login` or `/signup`.
- **Google (T6a):** 3 failure-path tests in `tests/backend/test_auth.py` `GoogleTests` (no session/cookie/user on any failure, 400 on a missing credential, 503 without `google-auth`); `docs/AUTH.md` origin rules (`origin_mismatch`), no redirect URI, env names, how to check configuration. Live Google sign-in remains unverified.
- Results: `npm test` 221/221; backend 329 run, 1 error (`pyotp` missing); 18 runnable browser tests OK individually.

## Unreleased - Consolidation of three archives (Phase B.1 review + T1-T4 + Session 26)
- Applied the Phase B.1 review patch: approved-area comparison is unit-aware (compared in square yards; a number without a recognised unit is never a match), CNIC is masked in mismatch reasons, uncertainty notes and limitations, and `Extraction.verifyAgainstRecords` is the single rule used by the app and `scripts/manifest-report.mjs`. 15 new tests (`tests/frontend/verificationB1Review.test.js`).
- `/messages` login redirect now percent-encodes the return path (no duplicate `next` parameter); tests in `tests/backend/test_return_path.py`.
- Restored `.env.example` (placeholders only) with the guest settings; both T4 archives had dropped it.
- `tests/browser/listings_test.py`: wait for the browse list before the exact count (was intermittent). New `tests/browser/guest_entry_failures_test.py`: 429, network failure and double-click guard of "Continue as Guest".
- Docs: compact `HANDOFF.md`/`docs/HANDOFF_NEXT.md`, full history preserved in `docs/HANDOFF_ARCHIVE.md`.

## Unreleased - Login first and the Guest experience (T4)
- Server-side login-first: anonymous `GET /`, `/index.html`, `/listings`, `/listings.html` -> 302 `/login` (`/login?next=/listings` for listings; the return path is a fixed server value, never request input). User, guest and admin sessions are served; these pages are sent `Cache-Control: private, no-cache` and `Vary: Cookie`. Sign-in pages, assets, `robots.txt`/`sitemap.xml` and the auth endpoints stay public.
- Login page: **Continue as Guest** button (`POST /api/v1/auth/guest` through `fetchJson`, one request at a time, shows `429 guest_limit` and other errors, only a real `role: guest` answer counts as success). A guest on `/login` now gets the normal forms (before: "Signed in as ...", no way to log in). Guests land on `/` or the public `/listings`, never elsewhere.
- Guest interface (display only; the server guards are unchanged): header Guest badge + Log in / Sign up + Exit; listings page hides the create form, personal listings and Messages link; "Chat with seller" explains an account is needed and links to log in/sign up; the owner-name check is replaced by a prompt; the privacy page hides the devices/delete-account panel; narrow-screen header stays within the viewport at 320-375 px.
- Tests: backend `test_login_first.py` (16); frontend `guestEntry.test.js` (7); browser `guest_entry_test.py` (28 checks, in CI). Existing tests adapted to the new first-visit flow (they enter through the real Guest button via `tests/browser/support/session_entry.py`); `test_api.test_static_site_routes` now expects the 302. `a11y_basics_test` and `csp_test` audit `/` and `/listings` as a guest (otherwise they would have audited the login page).
- Browser test servers run with `GUEST_MAX_ACTIVE_PER_IP=1000` (a full run creates more than the default 10 guests). Product default unchanged.

## Unreleased - Restricted guest sessions (T3)
- `POST /api/v1/auth/guest`: server-side guest session (`role='guest'`, 15 min idle / 2 h absolute, no remember-me, per-IP cap). `login_required` denies guests (`403 guest_not_allowed`) unless a route sets `allow_guest=True`; guests are hidden from admin user list/CSV/session view and cannot be admin targets; `/messages` redirects guests to login. Bounded cleanup of expired guests. Tests: `tests/backend/test_guest.py` (incl. route-authorization matrix).

## Unreleased - Developer Login page restored (T2)
- New `/developer-login` page (admins only; invalid -> `/nice-try`), Developer link on `/login` replaces the Skip-login toggle; browser test `developer_login_test.py` registered in CI.
- Fix: `backend/app.py` was missing `import os` (dev server crashed on start since the Session 26 bind-address change); regression test added.

## Unreleased - Developer Login backend restored (T1)
- `POST /api/v1/auth/developer-login`, `AuthService.login(admin_only=True)`, `developer_login` in `/auth/features`; tests in `tests/backend/test_developer_login.py`.

## Session 26: scanner follow-up (Priorities 1-5)

* Test determinism: `tests/backend/test_auth.py` Client now defaults `google_client_id=None` (create_app() loads the developer's `.env`, so a real GOOGLE_CLIENT_ID leaked into `Settings.from_env()` and broke `test_unconfigured_is_503_and_never_signs_in`); that test also passes `google_client_id=None` explicitly. Assertion unchanged.
* Security (from the Bandit log): `UpstashStore` now validates its URL (`validate_rest_url`: https, or http for loopback only; no credentials in the URL) and `build_store` falls back to in-memory counters with an ERROR log if it is unusable; the dev server binds `127.0.0.1` unless `KPT_HOST` is set (was `0.0.0.0`; matches docs/DEVELOPMENT.md); `RetentionService._delete` whitelists table names. The 12 B608 (SQL) and 2 B105 findings were reviewed and are false positives (fixed fragments or whitelists, bound values); each carries a rule-specific `nosec` with its reason.
* Dependencies: `cryptography` requirement raised from `==46.0.6` to `>=50` (pip-audit: 9 findings). NOT installed or tested here; pin the exact version after `pip_audit` is clean. `pip` itself (tooling, not a project dependency) needs `python -m pip install --upgrade pip`.
* Tests: `tests/backend/test_bandit_hardening.py` (10). `tests/backend/__init__.py` makes the Flask test client buffer responses, which closes static files: unclosed-file ResourceWarnings 43 -> 0.
* Ruff: no new findings were introduced by these edits (lines kept within 110 characters); the remaining baseline is listed in docs/KNOWN_ISSUES.md.

## Dev-only "Skip login" / `admin__01` restored (owner-confirmed feature)
* Restored byte-for-byte from the Session 25 archive: `backend/services/dev_skip.py`, the `/auth/dev-skip` route and `dev_skip` flag in `backend/api/auth.py`, `dev_admin_password` / `dev_skip_enabled` in `backend/config.py`, the login-page button (`login.html`, `auth-page.js`, `login.css`), `.env.example`, `SECURITY.md`, `docs/AUTH.md` and `tests/backend/test_dev_skip.py`. It had been absent from the Phase B archive; the owner confirmed it is a deliberate feature (everything goes to `/nice-try` except `admin__01` + `DEV_ADMIN_PASSWORD`, which opens `/admin`).
* Safety limits unchanged and covered by its 9 tests: 404 and no button when `APP_ENV=production`, refused when `DATABASE_URL` is set (local SQLite only), empty password never matches, constant-time compare, wrong guesses at `admin__01` are logged, CSRF still required.
* Never set `DEV_ADMIN_PASSWORD` on Vercel.

## Phase B.1: verification hardening (PROPOSED: awaiting owner authorization)
* Placeholders (—, N/A, nil, none, null, unknown, TBD ...) are missing values on documents and records; a record with a placeholder survey/plot/owner no longer produces a mismatch.
* OCR lane only: a name one character off the record is "unable to verify", never a proven mismatch.
* Mismatch reasons, checks and details no longer contain any value from the record; "Owner on record" removed from both result screens; conflicting CNICs masked.
* Verified and Power-of-Attorney results state what they do not confirm; history saved in `localStorage` is CNIC-masked (`domain/resultPrivacy.js`).
* Tests: `tests/frontend/phaseB1.test.js` (34). Baselines unchanged: OCR 17/29 (app free-search lane) / 18/29 (anchored report), PDF 28/28, synthetic fixtures only.

## Phase B: document-verification false positives
* Fixed: mismatching documents reported as *Verified*. The attorney's CNIC is cross-checked against records; survey/plot/address a document states must agree with the matched record; plot and survey match on whole tokens; `verified` needs every required field found and positively compared; an unreadable approved area is no longer a match (`extraction.js`, `documentVerification.js`). Details and limits: `docs/KNOWN_ISSUES.md` item 1.
* Tests: new `tests/frontend/verificationRules.test.js` (21 tests); `pipeline.test.js` baseline now OCR 17/29, PDF 28/28, no false positives. `scripts/manifest-report.mjs` passes the record list like the app.

## Session 25b (merge of Session 22 saved-heart styling)

* Saved properties: the heart buttons (home cards and property page) now get a `saved` class, `aria-pressed` and an accessible label, and the saved state is highlighted using the stylesheet rules carried over from the legacy `styles.css`.
* Merge basis: Session 25 is the master. Session 22's photos and samples were already identical in Session 25; Session 22's `CHANGELOG.md`, `docs/DEPLOYMENT.md` and `docs/KNOWN_ISSUES.md` were not copied (Session 25's versions kept).

## Reference merge (WinRAR archive into Session 23)
* Added: header "Creators" credit menu (`css/creators.css`, `js/features/creators.js`), CSP-safe (initial avatars, no remote images). Tests: `tests/frontend/creators.test.js`, `tests/browser/creators_test.py`.
* Fixed: signup/reset forms needed two clicks when the confirm-password field was focused (blur error shifted the button before mouse-up). Regression test `tests/browser/signup_single_click_test.py`; `login_test.py` passes again.
* Changed: `tests/backend/test_external_assets.py` gains a narrow outbound-link allowlist (`github.com`, HTML anchors only, never in the CSP).
* Report: `docs/REFERENCE_MERGE_REPORT.md`.

## Session 23 (in progress: improvements merged into Session 22)

* Login page: Caps Lock hint on password fields; confirm-password mismatch shown on blur; strength meter can no longer read "Okay" below the 10-character minimum. New `tests/frontend/authPage.test.js` (8 tests, incl. the open-redirect guard).
* Chatbot: new OPT-IN OpenAI Agents SDK engine `backend/services/ai/agents_engine.py` (`AI_ENGINE=agents`; provider `openai`, or `gemini` via its OpenAI-compatible endpoint). Reuses the existing owner-safe `make_tools` and `SYSTEM_PROMPT`; tracing disabled; live-search questions still go to native Gemini; any failure falls back to Gemini/offline. Default (`AI_ENGINE=gemini`) behaviour is unchanged. New env vars are listed in `.env.example`. NOT yet run against the real `openai-agents` package (tests use a fake SDK).
* Reference `Chatbot/` was decoded (CRC-verified) and compared; see `docs/CHATBOT_REFERENCE_COMPARISON.md`. Ported: `classify_error` + key `redact()` (`backend/services/ai/errors.py`); Agents engine model-fallback list (`OPENAI_MODEL=a,b`), one retry when busy, stop on auth errors, `status()`, and the no-live-data prompt note; admin `/health/detail` now shows `agents` status.
* Widget (from the reference): 60 s timeout, tolerant response parsing, offline-mode label/footer; footer shows which engine answered; subtitle typo fixed.
* `docs/DEPENDENCIES.md`: openai/openai-agents rows now say where they are imported; `openai` range corrected to match `pyproject.toml` (`>=3,<4`). `tests/backend/test_dependencies.py`: both packages removed from PLANNED (they are now imported, as that guard requires).
* Not ported from the reference: public health endpoint with key status, CORS/rate-limit code (Session 22 has its own). (An earlier note here said the widget CSS differed by a Google Fonts import; it does not: both files contain it and are identical.)
* Chatbot, full reference review (see `docs/CHATBOT_REFERENCE_COMPARISON.md`): `Store`, price pipeline, widget CSS and `app.py` concerns are already equivalent or better in Session 22. Merged what was missing: **block follow-ups** (`block 10` / `10` after a price question; `Memory.block`), targeted clarifying questions, "Cheapest / Most expensive … by median price" labels, rows without "None"/"0 rooms", `AI_ORDER` engine order, Gemini `status()`/`last_error`, `reason` in the chat response, admin health `gemini_status`.
* Agents SDK: specialist **handoffs** (Price Estimator, Market Analyst, Property Finder; `AGENTS_MODE`), owner-privacy **guardrail** (`services/ai/guardrails.py`). Fake-SDK tested only.

## Session 22b (featured properties carousel)
* Home: the single featured card is now a **Featured Properties carousel** (p1, p4, p8, p2): previous/next buttons, progress dots, swipe, arrow keys, auto-rotation every 6 s that stops on hover/focus/hidden tab, a visible **Pause/Play** button (WCAG 2.2.2), no rotation under `prefers-reduced-motion`. Ported from the supplied `js/app.js`, rewritten for the strict CSP (no inline style/handlers, CSS in `css/featured.css`, `data-bg`, `data-onclick`) with every value escaped; quick repeated clicks interrupt the slide animation instead of being dropped. New: `frontend/js/features/featured.js`, `frontend/css/featured.css`, `tests/frontend/featured.test.js`, `tests/browser/featured_test.py` (added to CI). Not imported from the zip on purpose: `owner_verification.js` (it re-adds owner names/IDs to the browser) and `extraction.js` (identical to the master).

## Session 22b (assets, from `public.zip`)

* Added `public/assets/Property Images/` (51 files) and `public/assets/samples/` (57 files) from `public.zip`. Home cards, the featured property and the document-verification samples now use real files.
* Not copied (privacy): the zip's raw `Dataset/*.csv` (owner columns), `*.xlsx`, notebooks, `price_model.joblib` and the pipeline script. Session 22's sanitised datasets are unchanged.
* Merge note: these 108 files are byte-identical to the ones already present in the Session 23 merge (verified by SHA-256 in the Session 24 merge), so nothing was copied twice. Their dataset-privacy decision is the same as ours.

## Session 22 (UI polish: login and home)

* Login: Google button now matches the form width; "Remember me" and "Forgot password?" share one row; feature items sit side by side; tighter spacing on short desktops; focus glow on inputs; reduced-motion respected.
* Home: one clear hero (headline, search, trust chips) instead of a duplicated logo/menu/brand block; navigation shows Log in / Sign up pills (Log in only on phones, no wrapping).
* Missing property photos now fall back to a solid brand panel instead of a grey box. Note: `public/assets/Property Images/` is not in the supplied archive; the photos themselves must be restored from your copy.
* No change to auth, sessions, CSRF, lockout or the admin account. `ADMIN_001_PASSWORD` stays an environment variable (never committed).

## Session 21 (review of the windows-path patch)
* Fixed: `scripts/check_installed_versions.py` treated pre-releases as the final release, `~=` as `>=`, `1.8` as different from `1.8.0`, and ignored version parts after the 4th. Now a PEP 440 subset; unparseable versions fail. Tests: `tests/backend/test_check_installed_versions.py`.
* Added: `.gitattributes` (LF for all text, vendored files and binaries untouched) and `tests/backend/test_gitattributes.py`; docs note in `docs/DEVELOPMENT.md`. Reason: a Windows clone with `core.autocrlf=true` changed the hash of a vendored file in a real-Git reproduction.
* Hardened: `tests/backend/test_text_encoding.py` also flags `subprocess` calls using `text=True` without `encoding=`; fixed `test_records.py` and `test_totp_missing_library.py` accordingly.

## Session 22 merge (reference archive + login design)
* Added from the reference archive (all CRC-verified): `public/assets/Property Images` (51 photos; 16 are referenced by the UI and used to 404) and `public/assets/samples` (57 sample documents fetched by the document-verification flow). Guards: `tests/frontend/assetsPresent.test.js`, `tests/browser/property_images_test.py`.
* Chatbot: deterministic `help` and `dataset_overview` intents (the reference bot answered these offline; Session 22 sent "help" to the off-topic reply and "how many houses..." to the listing finder). Answers come only from the store (counts, areas, price stats); no model call. `backend/services/router.py`, `chat_service.py`; tests `HelpAndOverviewTests` + router cases in `tests/backend/test_chat.py`.
* Login: the uploaded design was already implemented in Session 22 (`login.css` is a port of it); only the Google button busy state from the design was missing: it is now disabled while a request is in flight. `tests/browser/login_busy_test.py` (CI list updated).
* Report: `docs/MERGE_REPORT_SESSION22.md`.

## Session 19 (continued)
* Windows: every text-mode file call in `tests/` and `scripts/install_deps.py` now passes `encoding="utf-8"` (12 sites; Python 3.12 on Windows defaults to cp1252, which can mis-decode this repo's UTF-8 files, including `pyproject.toml` read by the installer). Guard: `tests/backend/test_text_encoding.py` (AST scan of `backend/`, `tests/`, `scripts/`). `backend/` already complied. No POSIX-only modules/syscalls or shell syntax were found.
* Security hardening found by a manual Bandit-style review (Bandit itself could not be run): `UpstashStore` now requires an `https://` URL (plain `http://` only for loopback), so a bad `UPSTASH_REDIS_REST_URL` cannot make `urlopen` read `file://` or send the bearer token in cleartext; a bad value raises at startup. The local dev server now binds to `127.0.0.1` by default (`KPT_HOST` overrides; was `0.0.0.0`). Two `urlopen` calls carry narrow `# nosec B310` comments with the reason. Tests: `tests/backend/test_network_config.py` (5).
* Windows: `tests/frontend/strictStyles.test.js` uses `fileURLToPath` (was `URL#pathname`, which breaks on Windows); guard `tests/frontend/portablePaths.test.js`; read-only `scripts/check_installed_versions.py`; `tests/browser/camera_upload_test.py` (camera, unsupported/empty/PNG/PDF uploads with the CDN libraries unavailable) added to the CI browser list.

## Session 19
* Accessibility: `a11y_basics_test.py` now also covers the single-page views (property detail, document verification, dataset listing, owner verification). It found and fixed (attributes only, no layout change): no level-1 heading in three views, and two unnamed inputs in document verification (labels now use `for=`).
* Tests: `test_external_assets.py` (third-party host + floating-version inventory and served-CSP checks), `test_sql_portability.py` (SQL text safe for the psycopg `?`->`%s` rewrite, no SQLite-only syntax). No application behaviour changed.
* Hardened `scripts/vendor_assets.py` (strict version match, validate-all-before-download, https-only redirects, 50 MB cap, config-vs-manifest check in `verify`) with 3 new tests. Documented that `package.json` has no dependencies, so no npm lockfile/audit applies.

## Session 17
* Fixed: a missing `pyotp` package crashed the whole app at import time; TOTP now fails closed (`503 totp_unavailable`) and the rest keeps working.
* Fixed: malformed ban requests (`kind`/`days`) no longer consume a one-time step-up proof.
* Changed: `/chatbot-demo` is served without `style-src 'unsafe-inline'` (inline style moved to `css/widget-demo.css`).
* Pinned: `cryptography==46.0.6`, `playwright==1.56.0`.
* Tests: missing-library module, step-up ordering, Google-only admin, strict `/chatbot-demo`; `listing_lifecycle_test.py` race removed.

## Session 18
- Accessibility: names for the home menu button, filter/sort selects and two back buttons; level-1 heading on the home page; new `a11y_basics_test.py`.
- TOTP: parallel enrolment starts now return `409 enrolment_in_progress` instead of a possible 500 (`ON CONFLICT DO NOTHING`).
- `scripts/vendor_assets.py` (+ example config, tests): owner-run, hash-recording downloader/verifier for self-hosting Tesseract.js / PDF.js. Test race in `listing_lifecycle_test.py` fixed (waits for the list refetch).

## Session 16
- Admin TOTP (pyotp 2.10.0, Fernet-encrypted secrets via `TOTP_ENCRYPTION_KEY`, fail closed), one-time step-up proofs bound to session and action class (moderation, role change, CSV export), replay protection, rate limiting, audit events, Security panel in `/admin`, CSV export via POST, `scripts/reset_admin_totp.py` recovery. Migration `0007_admin_totp.sql`. Enforcement optional (`ADMIN_TOTP_REQUIRED`, default off).

- `tests/backend/test_ci_config.py`: static checks of the CI workflow and Dependabot config (Python version, npm scripts, every browser test is run by CI, audit tools declared); `admin_totp_test` added to the CI browser job. GitHub Actions has still never run.

## Session 15
- Listings: owner-only edit (title/area) and reversible close/reopen; closed listings hidden from browse and closed to new chats, existing conversations kept. No delete (see `docs/LISTING_DELETION_PROPOSAL.md`).
- Banned/inactive sellers refused at the service level for create/edit/reopen.
- Added CI workflow, Dependabot config, SECURITY.md, ADMIN/DEPLOYMENT docs and ADRs (not yet run on GitHub).
- Admin TOTP still not built at that time (`pyotp` unavailable in the build sandbox); added in session 16.

## Sessions 13-14
- Strict `style-src` on every HTML page except `/chatbot-demo` (inline styles migrated to classes / CSSOM).

## Earlier
- Sessions 1-12: accounts, sessions, CSRF, admin, Google sign-in, forgot-password, remember-me, cookie consent, messaging with reports/blocks/moderation, seller listings, retention tooling (disabled by default). See `HANDOFF.md`.
