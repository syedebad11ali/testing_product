# HANDOFF ARCHIVE (historical material, moved mechanically from HANDOFF.md and docs/HANDOFF_NEXT.md)

Nothing below was rewritten; only these part headings were added. Read this file only when you need old details (a specific session, an old decision). The active checkpoint is `HANDOFF.md`.

Contents (Parts E-F were added in the consolidation): Part A - original CURRENT STATE of the Session 26 checkpoint (from `kpt-session26-checkpoint.zip`); Part B - the T1-T3 checkpoint that was in HANDOFF.md before compaction; Part C - older session hand-offs (Sessions 13-26 and earlier, verbatim); Part D - the previous `docs/HANDOFF_NEXT.md`, verbatim.

<!-- ===== PART A ===== -->

## PART A - Session 26 checkpoint: original CURRENT STATE (verbatim)

## CURRENT STATE (Session 26 checkpoint) - read this first

**This tree = `Kpt-phaseb1-after-tests.zip` (Phase B.1) + the scanner fixes below. It does NOT contain T1, T2 or T3 of `work.md`** (no `developer-login` page, no `admin_only` login, no guest sessions, no login-first redirect). The T3 patch (`kpt-T3-patch.zip`) was deliberately NOT applied: it was built on a tree that has T1+T2 (not supplied), its `web.py` serves `developer-login.html` which does not exist here, and it would overwrite `backend/api/admin.py` and `backend/app.py`, which carry the fixes below.

**Done in this tree (all verified in the Linux sandbox, not on Windows)**
* `test_unconfigured_is_503_and_never_signs_in` made deterministic (`google_client_id=None`); passes with a dummy `GOOGLE_CLIENT_ID` set.
* Bandit review: dev server binds `127.0.0.1` (`KPT_HOST` to override); `validate_rest_url` for the Upstash store (+ fallback to memory with an ERROR log); `_DELETABLE_TABLES` whitelist in retention; B608/B105 reviewed = false positives, rule-specific `nosec`; `tests/backend/test_bandit_hardening.py` (10 tests).
* `tests/backend/__init__.py`: buffered Flask test client, unclosed-file warnings 43 -> 0.
* `cryptography` requirement `==46.0.6` -> `>=50` (**unverified**: not installed/tested here; rerun `pip_audit`, then pin exactly). `pip` needs `python -m pip install --upgrade pip` in the venv.
* Results: `npm test` 199/199; backend 272 run, 1 error = `test_admin_totp` (`pyotp` not installed in the sandbox). Not run: `ruff`, `bandit`, `pip_audit` (not installed, no network), PostgreSQL, live Google, Windows.
* The `.env` that was inside the uploaded archive was deleted unread and is not in this ZIP. Rotate any keys it held.

**Not done**
* Priority 6 (revalidate Phase B / B.1: POA mismatch, altered documents, placeholders, whole-token identifiers, OCR uncertainty, result-screen limits, personal-data leakage).
* Ruff triage fixes (baseline recorded in `docs/KNOWN_ISSUES.md`; two real `F401` unused imports remain in `backend/api/chat.py` and `backend/api/messages.py`).
* `work.md` tasks T1-T7 for THIS tree (see the banner in `work.md`).

**EXACT NEXT ACTION:** get the full project that has T1+T2+T3 applied (or decide to rebuild T1-T3 on this tree), merge it with this tree (three-way: keep the fixes above), run the full suites, then start T4.


<!-- ===== PART B ===== -->

## PART B - T1-T3 checkpoint as recorded in HANDOFF.md before compaction (verbatim)

## CURRENT STATE (Session 26 checkpoint + T1 + T2 + T3) - read this first

**Tree = Phase B.1 + Session 26 scanner fixes + T1 + T2 + T3.** Do not apply `kpt-T3-patch.zip`: T3 was re-implemented natively on this tree (it would overwrite `admin.py`/`app.py`).

**T1/T2 (done earlier):** `POST /auth/developer-login`, `/developer-login` page + Developer link, `import os` fix in `backend/app.py`.

**T3 (done this run, verified):** restricted guest sessions, backend only (no UI yet).
* New: `backend/services/guest_service.py` (`GuestService.create/cleanup/discard`), `tests/backend/test_guest.py` (16 tests incl. route-authorization matrix).
* Changed: `backend/security/guards.py` (`login_required(..., allow_guest=False)`: guest -> `403 guest_not_allowed`), `backend/api/auth.py` (`POST /auth/guest`, logout discards guest row, `/auth/features` has `guest: true`), `backend/services/session_service.py` (guest lifetimes; admin session view hides guests), `backend/config.py` (`guest_session_idle_s` 900, `guest_session_absolute_s` 7200, `guest_max_active_per_ip` 10, `guest_cleanup_batch` 200; env `GUEST_SESSION_IDLE_S`, `GUEST_SESSION_ABSOLUTE_S`, `GUEST_MAX_ACTIVE_PER_IP`), `backend/app.py` (`guests()` accessor), `backend/api/admin.py` (user list/CSV exclude guests; `_target` 404 for guests), `backend/api/messages.py` (`by-ref` treats guest as anonymous), `backend/api/chat.py` (no first-name greeting), `backend/web.py` (`/messages` redirects guests to `/login`), `docs/AUTH.md`, `CHANGELOG.md`, `work.md`.
* No DB migration needed (`users.role` is plain TEXT, `email`/`username` nullable).
* Tests run: `test_guest` 16/16. Backend full: 302 run, 1 error = `test_admin_totp` (`pyotp` missing). `npm test` 199/199. Browser: login, csp, cookies, developer_login, smoke, messaging, listings, listing_lifecycle, prefs all OK.
* The matrix asserts: every route that answers anonymous requests with 401 answers a guest with 403 `guest_not_allowed`; every admin route answers guest/user 403 and admin not 401/403 (GET); no route 5xx for guests.
* NOT verified: PostgreSQL (the cleanup `NOT EXISTS` / `IN (...)` SQL uses only `?` placeholders but ran on SQLite only), UI, remaining browser tests (CP1), `admin_totp_test`, ruff/bandit/pip-audit (the new f-string SQL carries `noqa S608`/`nosec B608`, only `?` markers interpolated).
* Assumption still awaiting owner confirmation: guests may browse listings and use the chatbot; nothing else.

**Not done:** T4-T7, Session 26 leftovers (Priority 6 revalidation, ruff F401 in `chat.py`/`messages.py`, pin `cryptography`).

**EXACT NEXT ACTION: T4** - "Continue as guest" button on `login.html`/`auth-page.js` calling `/auth/guest` (CSRF via `fetchJson`; handle 429 `guest_limit`); login-first gating: anonymous `GET /` (and `/listings`) -> 302 `/login`, user/guest/admin -> 200 (edit `backend/web.py`, keep `/privacy`, `/nice-try`, `/login`, `/developer-login`, static assets public); restricted guest UI (hide messaging/listing/verification entry points for `role == 'guest'` using `/auth/me`; header shows "Guest"); update existing browser tests that open `/` unauthenticated (smoke, listings, a11y, csp, etc.) to enter as guest first; tests: Flask redirect tests + new browser test. Then T5 (cookie consent after login).


<!-- ===== PART C ===== -->

## PART C - older session hand-offs (verbatim, unchanged from HANDOFF.md line 21 onward)


> **START HERE: read `docs/HANDOFF_NEXT.md` first (current state, rules, next steps). The rest of this file is older session history.**

# Hand-off addendum - reference (WinRAR) merge into the Session 23 master

**Read `docs/REFERENCE_MERGE_REPORT.md` first** (it also has an addendum for the later `session22b-assets` merge: 108 byte-identical asset files, 3 docs merged by hand). Summary: the reference and the master are mostly the same files (182 of 301 reference files byte-identical, 60 more differ only in CRLF). I imported the one missing feature (header **Creators menu**, rebuilt CSP-safe), fixed a **pre-existing two-click signup bug** (found because `login_test.py` failed on the untouched archive), and deliberately did **not** import the reference login demo server, its CSVs with owner names, or its monolith sources.
Verified (Linux/SQLite/Chromium): `npm test` 144/144; Python 229 run with 1 error = `test_admin_totp` (real `pyotp` not installed); 15 browser tests OK. **Not run:** `admin_totp_test`, PostgreSQL, live Google/email, real OCR/PDF, GitHub Actions, Windows, real touch.
Owner actions: run `python tests/browser/creators_test.py` and `python tests/browser/signup_single_click_test.py` locally; install real `pyotp==2.10.0` and run `test_admin_totp` + `admin_totp_test.py`; **rotate any keys** in the reference's two `.env` files (never read or packaged here); review the Creators links/names and confirm the credits you want shown.

---

# Hand-off: KPT Session 22 merge (reference archive + login design)

**Read `docs/MERGE_REPORT_SESSION22.md` for the full file-by-file comparison.** Summary:

* The reference RAR could not be opened with any available tool, so it was read with a purpose-written pure-Python RAR5 decompressor; every extracted file is CRC32-verified (296 files, 0 failures). Large irrelevant groups (12,995 `node_modules` files, `.git`, old owner-name CSVs, `.env` files) were not extracted or imported.
* **Added:** 51 property photos + 57 sample documents (were missing; the UI referenced them), chatbot `help` and `dataset_overview` answers (grounded in the data, no model call), Google-button busy state on the login page. **Login design:** the uploaded design was already implemented in Session 22 (verified rule-by-rule and visually at 4 sizes); nothing was replaced; the dev-only "skip login" button was deliberately not imported.
* **Not imported:** old Node/JWT login server, old owner-name datasets, duplicate `testpack` documents, `OpenAIEngine` (gated: needs `openai` + rotated keys), older config/fixtures/README.
* **Tests actually run here:** `npm run test:all` 125 JS pass; Python 207 run with 1 error (`test_admin_totp`: no real `pyotp` in this sandbox). 12 browser tests pass (smoke, login, login_busy, csp, a11y_basics, camera_upload, cookies, messaging, listings, listing_lifecycle, prefs, property_images). Not run: `admin_totp_test`, PostgreSQL, live Google/Resend, Lighthouse, pip-audit/bandit/ruff.
* **Owner actions:** rotate any keys in the reference archive's `Chatbot/.env` and `Chatbot/Login Page/.env` (they exist there); on your machine run `npm run test:all` with real `pyotp` and `python tests/browser/admin_totp_test.py`; consider optimising the 175 MB of images; keep `ADMIN_TOTP_REQUIRED=0` and `MESSAGE_RETENTION_DAYS=0` until their prerequisites are met.
* **Remaining work:** unchanged from the session 19-21 handoff below (PostgreSQL run of the four DB modules, vendoring Tesseract.js/PDF.js and tightening the CSP, dependency pins and scans, first real CI run, Agents SDK, listing deletion decision).

---

# Session 22b: featured carousel merged from `1793064294764_js.zip`

**What the zip was.** Three files from the reference project's static site: `js/app.js` (2,401-line monolith), `js/extraction.js`, `js/owner_verification.js`. Compared with this Session 22 master (not replaced):
* `extraction.js`: logic identical to `frontend/js/domain/extraction.js` (only the UMD wrapper vs ES module and comment paths differ). **Nothing to merge.**
* `owner_verification.js`: identical except four lines (`ownerId`, `ownerName`, `listedOwner`, `previousOwner`) that the master deliberately removed (owner data must not reach the browser). **Not imported**: it would re-open that exposure.
* `app.js`: 124 functions; 113 already exist in the modular app. The only genuinely new feature is the **Featured carousel** (`featuredList`, `featGo`, `featInit`, ...). Also not present: `cmpCheckLine`, `docTypeLabelFor`, `isSecureCameraContext` (names only; not investigated, not merged).

**What was implemented.** `frontend/js/features/featured.js` + `frontend/css/featured.css`; wired through `home.js` (`renderFeatured()`), `router.js` (`initFeatured()` after each render), `ui/actions.js` (`featGo`, `featMove`, `featToggle`), `state/store.js` (`featIdx`), `index.html` (stylesheet link), `.github/workflows/ci.yml` (`featured_test`). Rewritten for this app: no inline style/handlers or injected style element (strict CSP), `data-bg` images, escaped values, ids validated before use in an action. Accessibility additions beyond the original: labelled carousel region and slides, `aria-current` on the active dot, visible Pause/Play button, polite announcements only for visitor-initiated changes, no rotation under reduced motion or in a hidden tab, 44 px call-to-action. Bug fixed relative to the original: a second click during the slide animation was ignored; it now interrupts the animation.

**Verification (Linux sandbox, Python 3.12.3, Node as installed; SQLite; real `pyotp` present; nothing run on Windows).**
* Untouched master: `npm test` 122 JS pass; `python -m unittest discover -s tests/backend -t .` 229 pass.
* After the change: **131 JS pass (+9 new in `tests/frontend/featured.test.js`), 229 Python pass.** The existing `strictStyles`, `handlers` and CI-config tests pass unchanged.
* Browser (Playwright, local server): new `tests/browser/featured_test.py` OK (next/previous/wrap/dots, auto-rotation, Pause/Play, keyboard Enter on the call-to-action, reduced motion, 360 px no horizontal scroll, no CSP/page errors); `csp_test.py`, `smoke.py`, `a11y_basics_test.py`, `prefs_test.py` OK.
* Not run: other browser tests, PostgreSQL, Google/Resend, Lighthouse, GitHub Actions, live AI. Property photos are not in the archive (`public/assets/Property Images/` missing), so the slide image check shows the fallback panel plus the correct image URL in the style, not the real photo.

**Not done / notes.** The task prompt `Pasted text(2).txt` was not attached, so I could not follow the Phase 0..13 plan from it; the formal Phase 0 baseline report was replaced by the before/after numbers above. `FEATURED_IDS` is `['p1','p4','p8','p2']` as in the zip (edit in `featured.js`). Rotation period `FEAT_AUTOPLAY_MS` is 6000.

**Owner actions.** Run `python tests/browser/featured_test.py` on your machine (about 40 s) and look at the carousel with the real photos in light and dark themes.

---

# Session 21b reconciliation note (read first)

This tree was assembled in a Linux sandbox from `kpt_full_Check_needed.rar` plus both nested patch ZIPs (`kpt-windows-path-fix-patch.zip`, `kpt-session21-patch.zip`). See `REPAIR_REPORT.md` for exact results.

* **The archive snapshot is older than the Windows checkout.** Session 20 network hardening (`KPT_HOST` default `127.0.0.1`, Upstash URL validation, narrow `nosec`, `tests/backend/test_network_config.py`) is described in the notes below but is **NOT present in this tree** (`app.py` still binds `0.0.0.0`; the test file does not exist). It was not reconstructed. Compare with your Windows folder before relying on this archive for those files.
* Integrated: both patch sets (Session 21 checker, `.gitattributes`, encoding guard, `fileURLToPath` fix + `portablePaths` test, CI `camera_upload_test`, docs, changelog), plus UTF-8 on the two subprocess calls and 12 bare text-file calls the stronger guard flagged in this older tree.
* Sandbox results are Linux only; nothing here was run on Windows.

# Hand-off: KPT upgrade (Session 21, 2026-10-26: patch review from a Linux sandbox - NOT a Windows verification)

## Session 21 - what actually happened (read this first)
**I had no access to your Windows checkout (`C:\\Users\\HASEEB\\Downloads\\kpt`, `.venv312`) and no full repository.** The archive `kpt-session19d-patch.zip` holds only the files changed by the windows-path slice, which depend on files that are not in it (`scripts/vendor_assets.py`, `tests/browser/a11y_basics_test.py`). So I could not apply the patch to your tree, run anything on Windows, run `check_installed_versions.py` against your venv, run the real-`pyotp` TOTP test, or touch PostgreSQL. **Nothing below is a Windows result.** What I did was a static review of every patch file plus a labelled run on a *scratch overlay* (my older session-17 tree + the patch + my fixes, Linux, Python 3.12.3, **no `pyotp`, no shim**).

### Addendum (same session): Windows line-ending hazard found, fixed and proven with real Git
**Finding:** the repository had no `.gitattributes`/`.editorconfig`. Your current Windows folder came from zips (LF), so it works today, but a fresh `git clone` on Windows with Git's default `core.autocrlf=true` rewrites text files to CRLF. That breaks anything that hashes file bytes, most importantly the vendored Tesseract.js/PDF.js that will live in `public/assets/vendor/` with SHA-256/SRI in a manifest (`scripts/vendor_assets.py verify`).
**Reproduced (git 2.43.0, throwaway repo, simulated Windows clone):** without the file a vendored `.js` changed hash (`7833c2755c22` -> `d8420d547a59`); with it the hash stayed `7833c2755c22`, other text stayed LF, PNG bytes untouched (`git check-attr` shows `eol=lf` and `text: unset` for the vendor path).
**Fix (in `kpt-session21-patch.zip`):** `.gitattributes` (`* text=auto eol=lf`, `public/assets/vendor/** -text`, binary types), self-maintaining guard `tests/backend/test_gitattributes.py` (4 tests; fails if a binary type exists in the repo without being declared), and a "Windows notes" section in `docs/DEVELOPMENT.md`. **After copying it in, run `git add --renormalize .` and read `git status` before committing**; do not commit a mass line-ending change you did not expect. Not verified on your machine; `autocrlf` behaviour was simulated with `git clone -c core.autocrlf=true` on Linux.
**Static Windows scan result (no problems found):** `npm run test:all` uses `python` (not `python3`); no `shell=True`, `/tmp`, `fcntl`, POSIX signals, `NamedTemporaryFile` reopen, `chmod` or symlinks in `tests/`, `scripts/` or CI. Not verified: Node 20 vs the quoted glob in `npm test` (`node --test "tests/frontend/*.test.js"`; `engines` says `>=20`; the sandbox has Node 22 and your earlier Windows run executed these tests, so it evidently works for you, but tell me your `node --version`).
**Overlay results after the addendum:** JS 122 pass; Python 192 run with the same 3 known problems (real `pyotp` missing; two overlay-only missing files) and no new failures.

### Patch review (static): files inspected
* `tests/frontend/strictStyles.test.js`: only change is `FE = fileURLToPath(new URL('../../frontend/', import.meta.url))` plus the import. No assertion removed or weakened. Correct fix for the `C:\\C:\\...` `ENOENT` (`URL#pathname` is `/C:/...` on Windows).
* `tests/frontend/portablePaths.test.js`: sound guard (rejects `.pathname` on `import.meta.url`, checks `fileURLToPath` is readable).
* `backend/security/ratelimit_store.py`: `check_store_url()` precedence is correct (`(scheme != https and not (http and loopback)) or not hostname`); rejects `file://`, `ftp://`, scheme-less, `//host`, empty, `https://`, non-loopback `http://`; the token is never sent to a refused URL (tested). `backend/config.py` + `backend/app.py`: `KPT_HOST` defaults to `127.0.0.1`, no hard-coded `0.0.0.0`. `backend/services/mailer.py`: the `nosec B310` is justified (URL is the constant `https://api.resend.com/emails`). `nosec` comments are narrow and explained.
* `tests/backend/test_network_config.py`, `tests/backend/test_text_encoding.py`: reviewed, see findings.
* `.github/workflows/ci.yml`: browser loop adds `a11y_basics_test` and `camera_upload_test` (read-only change); this is NOT evidence that Actions ran.
* `tests/browser/camera_upload_test.py`: reviewed behaviour from its output (below). It proves validation and graceful-unavailable states, **not** OCR/PDF extraction.

### Defects found in the patch and fixed (files in `kpt-session21-patch.zip`)
1. **`scripts/check_installed_versions.py` compared versions wrongly.** Probed on the original: `2.10.0rc1` reported as an exact match for `==2.10.0`; `~=1.8` accepted `2.0.0` (treated as `>=`); `1.8` failed against `==1.8.0`; only the first 4 version parts were compared. It decides which `PIN ME` can be pinned, so a pre-release passing as a pin matters. Replaced with a stdlib PEP 440 subset (`parse_version`/`satisfies`): pre/dev builds sort before the final release, post after, trailing zeros ignored, `+local` ignored, `==X.*`, `!=`, `~=` correct, unparseable versions **fail**. Still read-only. New `tests/backend/test_check_installed_versions.py` (8 tests, includes a check that the script never installs or writes). No env-marker evaluation (none are declared today; 20 specs, 0 with `~=`, 0 with markers).
2. **Encoding guard gap.** `test_text_encoding.py` did not cover `subprocess.run(..., text=True)`, which also decodes child output with the Windows locale code page. Extended the guard (flags `run/check_output/Popen/check_call/call` with `text=True`/`universal_newlines=True` and no `encoding=`; verified it flags only the unsafe pattern). Two existing calls needed the fix and are provided as `subprocess_encoding.diff` (apply with `git apply`, or add `encoding="utf-8", errors="replace"` by hand): `tests/backend/test_records.py` and `tests/backend/test_totp_missing_library.py`. Risk today is latent (the child prints ASCII only). **If you do not apply the diff, the strengthened guard will fail on those two lines - that is intended.**

### Verification actually run (scratch overlay, Linux, Python 3.12.3, no real pyotp, no shim)
* `node --test tests/frontend/strictStyles.test.js tests/frontend/portablePaths.test.js`: **15 pass / 0 fail**. `npm test`: **122 pass / 0 fail** (matches the inherited sandbox figures).
* `python -m unittest tests.backend.test_check_installed_versions tests.backend.test_text_encoding tests.backend.test_network_config`: **14 pass / 0 fail**.
* Python full discover on the overlay: 188 run, **3 problems, none in the patch's logic**: (a) `test_admin_totp` import error - real `pyotp` is not installed here (**a blocker, not a pass; no shim used**); (b) `test_vendor_assets` - `scripts/vendor_assets.py` missing in my older base tree; (c) `test_ci_config` - the workflow lists `a11y_basics_test`, which does not exist in my older base tree. (b) and (c) are overlay artifacts and should pass in your real tree; confirm there.
* Browser (Chromium, throwaway DB): `camera_upload_test`, `csp_test`, `smoke`, `login_test`, `cookies_test` OK. In `camera_upload_test` Tesseract.js/PDF.js are unavailable offline, so the page showed the expected "could not be loaded" states; **no OCR or PDF text extraction was proven.**

### NOT run / blocked
Windows anything; `python scripts/check_installed_versions.py --dev` in `.venv312`; `python tests/browser/admin_totp_test.py` with real `pyotp`; `a11y_basics_test`; `listings`/`lifecycle`/`messaging`/`prefs` browser tests on the real tree; PostgreSQL (no server/`psycopg`/`DATABASE_URL`); vendoring Tesseract.js/PDF.js/fonts (no network, so no `vendor_assets.py fetch/verify`, no CDN removal from CSP); remaining `PIN ME` pins, `pip-audit`, `bandit`, `ruff`, Lighthouse; GitHub Actions; Google OAuth, Resend, Vercel, live AI. No git: no `git status/diff/diff --check` could be run.

### Do this on your machine (activate `.venv312`; never print `.env`)
1. Check status first: `git status --short --branch`. Copy the files from `kpt-session21-patch.zip` over the checkout (`scripts/check_installed_versions.py`, `tests/backend/test_check_installed_versions.py`, `tests/backend/test_text_encoding.py`, `tests/backend/test_gitattributes.py`, `.gitattributes`, `docs/DEVELOPMENT.md` - the last one replaces the patch's copy and only appends the Windows notes) and `git apply subprocess_encoding.diff` (check `git apply --check` first). If you have not yet applied `kpt-session19d-patch.zip`, apply that first.
2. `node --test tests/frontend/strictStyles.test.js tests/frontend/portablePaths.test.js` then `npm run test:all`. Report JS and Python separately.
3. `python --version`, `python -c "import sys; print(sys.executable)"`, `python scripts/check_installed_versions.py --dev`, `python -c "import importlib.metadata as m; print('pyotp', m.version('pyotp'))"` (expect 2.10.0), then `python tests/browser/admin_totp_test.py`.
4. Run the other browser tests one at a time (`a11y_basics_test`, `csp_test`, `camera_upload_test`, `smoke`, `login_test`, `cookies_test`, `listings_test`, `listing_lifecycle_test`, `messaging_test`, `prefs_test`). Send back full output with secrets removed. Windows-specific risks I cannot see: tests that spawn `python -m backend.app`, hard-coded `/` paths, and camera permission prompts.
5. Review `git diff --check` and `git diff` before committing; I did not commit or push anything.

### Gates preserved (unchanged)
`ADMIN_TOTP_REQUIRED=0` until every admin enrols with a real authenticator and `scripts/reset_admin_totp.py` is rehearsed on a database copy; `TOTP_ENCRYPTION_KEY` private; `MESSAGE_RETENTION_DAYS=0` (730-day default is not approved); no hard delete and no listing-deletion work without the owner decision in `docs/LISTING_DELETION_PROPOSAL.md`; Agents SDK / live AI gated until exposed keys are rotated, deps pinned and offline fake-provider tests exist; disposable databases only; Upstash URL validation and loopback default not to be weakened; no `unsafe-inline`/`unsafe-eval`.

### Next actions, in order
1. Windows verification (items 1-4 above). 2. Real-`pyotp` TOTP browser test + PostgreSQL run of the four modules on a disposable DB. 3. Vendor Tesseract.js/PDF.js/fonts with the repo tool, then tighten `script-src`/`connect-src` and rerun `csp_test`/`camera_upload_test` with real extraction. 4. Pins, `pip-audit`, `bandit` (expect the CI bandit step to surface findings), `ruff` baseline, Lighthouse. 5. First real GitHub Actions run.

---

# Hand-off: KPT upgrade (windows path fix, after session 19B)

## What this change is (and is not)
**I cannot run anything on your Windows machine (`C:\Users\HASEEB\Downloads\kpt`, `.venv312`).** Everything below was run in my Linux sandbox (Python 3.12.3, no real `pyotp`). The Windows results you asked for (`npm run test:all` with real `pyotp`, `admin_totp_test.py`, version check against your venv) still have to be run by you; commands are at the end. The uploaded `.rar` could not be opened here (no RAR tool), so it was not inspected.

### Root cause and fix (task 1-3)
`tests/frontend/strictStyles.test.js` built its folder with `new URL('../../frontend/', import.meta.url).pathname`. On Windows that is `/C:/Users/HASEEB/.../frontend/`, and `path.join` / `readFileSync` turn it into `C:\C:\Users\...` (`ENOENT`). On Linux the same code works, so earlier sessions never saw it. **Fix:** `const FE = fileURLToPath(new URL('../../frontend/', import.meta.url));`. It was the only `.pathname` file-path use in `tests/`, `scripts/` and `frontend/js`. No assertion was changed or weakened.
* New guard `tests/frontend/portablePaths.test.js`: fails if any test file uses `URL#pathname` on `import.meta.url`, and checks `fileURLToPath` yields a readable folder.
* Sandbox result: `node --test tests/frontend/strictStyles.test.js tests/frontend/portablePaths.test.js` = 15 pass / 0 fail; `npm test` = **122 pass / 0 fail** (120 + 2 new). **I could not reproduce the Windows failure itself here**; the expectation is that your 11 failing tests (all in `strictStyles.test.js`) now pass, which only you can confirm.

### New read-only helper (task 6)
`scripts/check_installed_versions.py [--dev]` compares the packages in the interpreter running it with `pyproject.toml` (exact pins must match; ranges reported as in/out of range; missing reported). Installs nothing, guesses nothing. Sandbox output is NOT your environment's result; for reference it reported `scikit-learn` 1.8.0 vs the declared 1.9.1 here: check yours, the price model was serialised with 1.9.1.

### Other sandbox verification after the change
* Python (no real pyotp): 190 run, the same single import error (after adding `camera_upload_test` to the CI browser list, which `test_ci_config` requires) (`tests.backend.test_admin_totp`); `a11y_basics_test`, `camera_upload_test`, `csp_test` OK.
* `tests/browser/camera_upload_test.py` (new): under the strict CSP with Tesseract.js / PDF.js **unavailable** (offline sandbox) it checks, in Chromium with a fake camera: live camera starts -> frame captured -> photo used; upload step rejects an unsupported `.txt` ("Unsupported file") and an empty PNG ("empty"); a real-sized generated PNG reaches OCR and shows "The OCR engine could not be loaded..."; a PDF shows "The PDF could not be read (PDF reader could not be loaded)..."; zero `securitypolicyviolation` events and zero page errors. **It does NOT prove OCR or PDF text extraction work**: those need the libraries on a networked machine (a 1x1 PNG is correctly refused earlier by the image-quality check, so the test generates a larger image).

### Added after the path fix: network-config hardening (manual security review)
Bandit is not installed here, so I scanned `backend/` for the patterns it flags and fixed the two real ones: (1) `UpstashStore` opened a config-supplied URL without checking its scheme (a `file://` value would be read; `http://` would send the bearer token in cleartext) -> now `https://` only, plain `http://` only for loopback, otherwise `ValueError` at startup (the existing fail-open test uses `http://127.0.0.1:9` and still passes); (2) the dev server bound to `0.0.0.0` -> `Settings.host` from `KPT_HOST`, default `127.0.0.1`. Two `urlopen` calls got narrow `# nosec B310` comments with reasons. Files: `backend/security/ratelimit_store.py`, `backend/services/mailer.py`, `backend/config.py`, `backend/app.py`, `.env.example`, `docs/DEVELOPMENT.md`, `CHANGELOG.md`, `docs/KNOWN_ISSUES.md`, new `tests/backend/test_network_config.py`. **Check on Windows:** if you start the dev server and open it from your phone, set `KPT_HOST=0.0.0.0`. Sandbox result: `npm run test:all` = 122 JS pass; Python 195 run, still the single `test_admin_totp` import error (needs real `pyotp`, which your venv has); smoke, login, csp, messaging browser tests OK. The Session 20 prompt was read; its priorities (3.12 venv + real pyotp, PostgreSQL, vendoring, pins/scans, real CI run) remain blocked in this sandbox (re-checked: no `pyotp`, no network).

### Added: Windows text-encoding audit
AST scan found 12 `read_text()/write_text()/open()` calls without `encoding=` (none in `backend/`): `scripts/install_deps.py` (reads `pyproject.toml`), and tests (`test_dependencies`, `test_vendor_assets`, `test_cookies`, `test_moderation_messaging`, `test_api`, `test_ci_config`, `admin_totp_test`). All now use `encoding="utf-8"`; new guard `tests/backend/test_text_encoding.py` fails on any new bare call. Also scanned for POSIX-only imports/syscalls, `/tmp` paths, shell-only npm syntax and temp-dir cleanup with open SQLite handles: none found. Sandbox result: `npm run test:all` = 122 JS pass; Python 196 run, still the single `test_admin_totp` import error (your venv has real `pyotp`). I could not run these on Windows; if any Windows-only failure remains, send the traceback.

### Run these on your machine (activate `.venv312` first; do not print `.env`)
1. `node --test tests/frontend/strictStyles.test.js` then `npm run test:all` (expect 122 JS; Python should now include `test_admin_totp` (195 discovered here + that module's tests; report the real number)).
2. `python scripts/check_installed_versions.py --dev`
3. `python tests/browser/admin_totp_test.py`, `python tests/browser/a11y_basics_test.py`, `python tests/browser/csp_test.py`, `python tests/browser/camera_upload_test.py`
4. Send back any failures with the full output (remove secrets). Windows-specific risks I cannot see from here: Python tests that spawn subprocesses or use hard-coded `/` paths, and the browser tests that start `python -m backend.app`.

### Still blocked / owner actions (unchanged)
PostgreSQL run of the four database modules, vendoring Tesseract.js/PDF.js (no network here), remaining `PIN ME` pins, `pip-audit`/`bandit`/`ruff`, Lighthouse, first real CI run (the bandit step is predicted to fail; see `docs/KNOWN_ISSUES.md`). Keep `ADMIN_TOTP_REQUIRED=0`, `MESSAGE_RETENTION_DAYS=0`, and the Agents SDK / listing deletion gated.

---

# Hand-off: KPT upgrade (status after session 19)

## Session 19 result
**This environment could NOT do the three top priorities.** Facts checked now: Python **3.12.3** (the declared version; system interpreter, no `.venv`), `cryptography` 46.0.6 and Playwright 1.56.0 (both match the pins), but **`pyotp` is not installed** (`pip download pyotp==2.10.0` -> `No matching distribution found`; no network; no wheel anywhere on disk), **`psycopg` and PostgreSQL are not installed**, and `ruff`/`bandit`/`pip-audit` are absent. No `.git` in the archive, so no status/diff was reviewed. `.env` was not read.

### Verification actually run now (Python 3.12.3, NO real pyotp)
* Baseline before edits: `npm run test:all` = **120 JS pass; Python 178 run, 1 error** (`tests.backend.test_admin_totp` cannot import without the real `pyotp`; it is NOT a pass, and no shim was used). The session 18 reference (120 + 204 with real pyotp 2.10.0 on Python 3.13.17) is therefore unconfirmed on 3.12.
* After edits: **120 JS pass; Python 187 run, the same 1 import error** (+6 `test_external_assets`, +3 `test_sql_portability`).
* Browser (Chromium, throwaway DB) all OK: `a11y_basics_test` (extended), `csp_test`, `smoke`, `listing_lifecycle_test`, `cookies_test`, `login_test`, `listings_test`, `messaging_test`, `prefs_test`. **`admin_totp_test.py` NOT run** (needs real `pyotp`).

### Done this session
| Change | Where |
|---|---|
| `a11y_basics_test.py` now audits the SPA views (property detail, document verification, dataset listing, owner verification) by clicking through. **Found and fixed real defects, attributes only:** no level-1 heading in three views (`role="heading" aria-level="1"` on the existing title element), and two unnamed inputs in document verification (`<label for=...>`) | `tests/browser/a11y_basics_test.py`, `frontend/js/features/property.js`, `frontend/js/features/ownerVerification.js` |
| Third-party asset inventory test: fails on a new host or a new floating CDN version; records the known floating `tesseract.js@5`; checks the served CSP has no `unsafe-eval`/script `unsafe-inline`, only known third-party origins, strict styles on HTML pages | `tests/backend/test_external_assets.py` |
| SQL portability checks for the PostgreSQL adapter (no literal `%` / quoted `?` in SQL text, no SQLite-only syntax; 0 hits in the current code) | `tests/backend/test_sql_portability.py` |
| Docs | `CHANGELOG.md`, `docs/KNOWN_ISSUES.md` |
No application logic, endpoint, migration or env var changed.

### Added later in session 19 (still offline, still no real `pyotp`)
* **`scripts/vendor_assets.py` reviewed and hardened** (it had never run): strict exact-version check (the old substring check let `5.1.1` match `5.1.10`), all entries validated before any download (no half-written vendor dir), redirects to non-https refused, 50 MB cap, `verify` now also reports assets that the config lists but the manifest lacks. `tests/backend/test_vendor_assets.py` 5 -> 8 tests. `python scripts/vendor_assets.py verify --config scripts/vendor_assets.example.json` correctly says no manifest exists (nothing vendored).
* **npm:** `package.json` has no dependencies at all, so no `package-lock.json` was created and `npm audit` does not apply (reason in `docs/DEPENDENCIES.md`).
* **CI review (static, nothing run):** workflow commands match the repo (3.12, `install_deps.py --dev`, `npm run test:all`, browser loop incl. `admin_totp_test` and `a11y_basics_test`). **Predicted risk:** the `audit` job's `bandit -r backend -q` has no severity filter and the code has zero `# nosec`; reviewed f-string SQL and `app.run(host="0.0.0.0")` are likely findings, so expect that job to fail on the first real run (see `docs/KNOWN_ISSUES.md`). This is a prediction, not a result.
* Final numbers for the whole session: `npm run test:all` = **120 JS pass; Python 190 run, the same single import error** (`test_admin_totp`, needs real `pyotp`).

### NOT done (blocked here) and exact next action
| Item | Blocker | Next action (owner machine, networked) |
|---|---|---|
| Fresh Python 3.12 `.venv` + real `pyotp` 2.10.0 suite | no network/package | create `.venv`, read `scripts/install_deps.py`, install, verify `importlib.metadata.version("pyotp") == "2.10.0"`, run `npm run test:all` (expect 120 JS + 204+9 Python) and `python tests/browser/admin_totp_test.py` |
| Four PostgreSQL modules (`test_admin_totp`, `test_listings_retention`, `test_moderation_messaging`, `test_listing_lifecycle`) | no PostgreSQL server, no `psycopg` | throwaway DB via `DATABASE_URL` (never print it), install `psycopg[binary]`, run the four modules, fix failures, keep SQLite green |
| Vendor Tesseract.js/PDF.js, SRI, tighten CSP, camera/upload/OCR/PDF browser checks | no network (CDN unreachable) | copy `scripts/vendor_assets.example.json` to `scripts/vendor_assets.json`, add Tesseract.js + matching core, worker and language data at exact versions, run `python scripts/vendor_assets.py fetch` then `verify`, point `index.html`/`ocr.js` at local files, remove jsDelivr/tessdata origins from `backend/security/headers.py` and the matching `KNOWN_FLOATING` entry, then run `csp_test.py` and exercise camera/OCR/PDF with DevTools open |
| Pin `openai-agents`, `openai`, `google-auth`, `requests`, `psycopg[binary]`, `ruff`, `bandit`, `pip-audit`, `argon2-cffi` | cannot install | pin only after a passing install + tests on 3.12 |
| `pip-audit`, `bandit`, `ruff`, `npm audit` (needs a deliberate `package-lock.json`), Lighthouse, ZAP | tools/network absent | run on the owner machine and record counts (session 18 ruff baseline: 1,272 legacy findings) |
| First real GitHub Actions run | not pushed | push when ready; actions still use major tags (no invented SHAs) |
| Agents SDK, listing deletion | gated | unchanged: see session 18 gates and `docs/LISTING_DELETION_PROPOSAL.md` (owner decision first) |
| `Property Images` folder | not in the archive | check the owner checkout |

### Owner actions (names only, never values)
1. Run the networked steps above (3.12 `.venv`, real `pyotp`, PostgreSQL modules, vendoring, pins, scans, first CI run).
2. Keep `ADMIN_TOTP_REQUIRED=0` until every admin is enrolled with a real authenticator app and `scripts/reset_admin_totp.py` is rehearsed on a database copy; set `TOTP_ENCRYPTION_KEY` (see `docs/ADMIN.md`); Google-only admins need a password first.
3. Rotate the exposed Gemini/OpenAI keys; approve retention periods (keep `MESSAGE_RETENTION_DAYS=0`; 730 days is NOT approved) and the listing-deletion policy.

### Next-session plan
1. Networked 3.12 + real pyotp + PostgreSQL modules. 2. Vendor assets, tighten CSP, camera/OCR/PDF checks. 3. Pins and scans, Lighthouse. 4. First CI run. 5. Soft delete only after the owner decides. 6. Agents SDK only after its gates.

---

# Hand-off: KPT upgrade (status after session 18: real-pyotp verification)

## Session 18 result
**The Session 17 TOTP results are now confirmed with the REAL library.** This sandbox has the real `pyotp` (importlib.metadata -> `2.10.0`, imported from `/usr/local/lib/python3.13/site-packages/pyotp`; no shim, no `PYTHONPATH`). The session 16 wheel was re-checked: `sha256sum` = `1df2f6a1bcc3bb0716172a5215ddc2f8c7c7fd26a13df9927d52e1746934836c` (matches). It had been installed offline from the owner's wheel earlier in this environment. **Interpreter caveat:** tests ran on Python **3.13.17**, not the declared 3.12 (`/usr/bin/python3.12` exists here but has none of the packages and PyPI is blocked, so no 3.12 venv could be built). Pins that were not exercised on 3.12 here: `cryptography==46.0.6` (sandbox has 50.0.1), `playwright==1.56.0` (sandbox has 1.63.0); the suite passes with the installed versions.
No `.git` in the archive: no status/diff could be reviewed.

### Verification actually run (real `pyotp` 2.10.0, Python 3.13.17)
* Baseline before edits: `npm run test:all` = **120 JS + 198 Python pass** (equals the session 17 stand-in figure; now a real-library result).
* After edits: `npm run test:all` = **120 JS + 204 Python pass** (+5 in `test_vendor_assets.py`, +1 enrolment race test); `admin_totp_test.py` re-run OK after the fix.
* Browser (Playwright 1.63.0, Chromium, throwaway DB, real `pyotp` codes): `admin_totp_test`, `login_test`, `csp_test`, `smoke`, `messaging_test`, `cookies_test`, `listings_test`, `prefs_test` OK. `listing_lifecycle_test` failed once on the baseline run (`closed listing still in browse`): the test asserted right after the status message, one request before the list refetch finished. Fixed in the test (it now waits for the refetched list); **6 of 6 consecutive runs pass**. The page itself was not changed.
* **PostgreSQL, SQL level only (NOT the Python test modules):** a local PostgreSQL 16.15 server is installed here but `psycopg` is not (and cannot be installed), so `PostgresDatabase` and the four test modules could not run. I started a throwaway cluster (unix socket only, deleted afterwards) and, with `psql`: applied all 7 migrations in order including `0007_admin_totp.sql` (no errors; `admin_totp` and `admin_stepups` created) and ran the exact TOTP compare-and-set statements: replay update `last_step < ?` -> `UPDATE 1` then `UPDATE 0`; one-time proof update -> `UPDATE 1` then `UPDATE 0`; deletes behave. This supports (does not prove) the atomicity claim; the Python facade's `?` -> `%s` rewrite and transactions are still unrun on PostgreSQL.
* Code review of `totp_service.py` and `admin_totp.py` against the checklist: no new defect found. One edge case found and FIXED later this session: two truly concurrent `enroll/start` calls could race on the primary key of `admin_totp` (generic 500, no data exposure). The insert is now `ON CONFLICT (user_id) DO NOTHING` and the loser gets `409 enrolment_in_progress` (regression test `test_parallel_enrolment_start_loses_cleanly...`; the `ON CONFLICT` form is valid in SQLite and PostgreSQL but was run on SQLite only). `ruff` finds nothing security-relevant new.
* `ruff check backend tests scripts` (ruff 0.16.9): 1,272 findings, all pre-existing style/legacy classes (E501 874, E702 252, E701 56, I001 22, ...) plus reviewed `S` findings that are fixed-SQL/dev-server/test items; `ruff check --select F,E9` on the files changed this session: clean. Not mass-fixed.

### Implemented this session
* `scripts/vendor_assets.py` + `scripts/vendor_assets.example.json` + `tests/backend/test_vendor_assets.py`: owner-run downloader/verifier for self-hosting third-party assets. https only; refuses URLs not pinned to an exact `x.y.z`; refuses paths outside the vendor dir; writes `MANIFEST.json` with sha256 and the SHA-384 string for `integrity=`; `verify` works offline and detects tampering/missing files. **Nothing was downloaded or hashed here** (the proxy answered 403 for `cdn.jsdelivr.net`; not worked around). Documented in `docs/KNOWN_ISSUES.md`. Only PDF.js 3.11.174 is pre-filled; Tesseract.js (still `@5`), its core/worker/language data and fonts need exact versions chosen by the owner.
* `tests/browser/listing_lifecycle_test.py` race fixed (above). Docs: `KNOWN_ISSUES.md`, `CHANGELOG.md`.

### Added later in session 18: basic accessibility regression
* New `tests/browser/a11y_basics_test.py` (also in the CI browser loop): per page, `<html lang>`, non-empty title, exactly one level-1 heading, accessible names for visible form controls/buttons/links/dialogs, `alt` on images. **It is NOT Lighthouse and NOT a WCAG audit**; no Lighthouse score exists. Pages: `/login`, `/signup`, `/privacy`, `/`, `/listings` (anon and signed in), `/nice-try`, `/messages`, `/admin`.
* It found real defects on the home page, fixed with attributes only (no layout change): menu button had no name (`aria-label="Open menu"`), the type filter and sort `<select>`s had no name, the brand text is now `role="heading" aria-level="1"` (the page had no h1), and two back buttons in `js/features/property.js` had no name (`aria-label="Back"`). Property detail/verify/document/owner-verification views were NOT covered by the test (only the two back buttons found by grep were fixed).
* After: `npm run test:all` = 120 JS + 204 Python pass; `a11y_basics_test`, `csp_test`, `smoke`, `cookies_test`, `listings_test` OK.

### NOT run / blocked
Python 3.12 environment; PostgreSQL via Python (`psycopg`); a real authenticator app; GitHub Actions (YAML unchanged, still unrun, actions pinned by major tag); `pip-audit`, `bandit` (not installed); `npm audit` (no lockfile, no network); Lighthouse; ZAP; Google OAuth, Resend, Vercel, live AI; strict-CSP asset pinning/self-hosting and the camera/OCR/PDF flows (CDN blocked); the `Property Images` folder is still absent from the archive. Remaining `PIN ME`: `openai-agents`, `openai`, `google-auth`, `requests`, `psycopg[binary]`, `ruff`, `bandit`, `pip-audit`, `argon2-cffi` (none pinned: no tested install on 3.12 here; `ruff` 0.16.9 and `requests` 2.34.2 only exist on 3.13 here). The Agents SDK stays gated.

### Owner actions (names only, never paste values)
1. Fresh **Python 3.12** `.venv`; review `scripts/install_deps.py`, install, check `python -c "import importlib.metadata as m; print(m.version('pyotp'))"` = `2.10.0`, then `npm run test:all` (expect 120 JS + 204 Python) and the browser tests. Pin the remaining `PIN ME` entries from versions that pass.
2. Generate `TOTP_ENCRYPTION_KEY` (command in `docs/ADMIN.md`), back it up, set it locally and on Vercel; enrol every admin with a **real authenticator app** (Google-only admins need a password first); rehearse `scripts/reset_admin_totp.py` on a copy of the database; only then set `ADMIN_TOTP_REQUIRED=1`.
3. With a throwaway PostgreSQL via `DATABASE_URL` (never print it): run `tests.backend.test_admin_totp`, `test_listings_retention`, `test_moderation_messaging`, `test_listing_lifecycle`.
4. Vendor assets: copy `scripts/vendor_assets.example.json` to `scripts/vendor_assets.json`, add Tesseract.js (+ core, worker, language data) with exact versions, run `python scripts/vendor_assets.py fetch`, review licences, switch `index.html`/`ocr.js` to the local files, test camera/upload/OCR/PDF with DevTools open, then tighten `script-src`/`connect-src` in `backend/security/headers.py`.
5. Run `pip-audit`, `bandit -r backend`, `ruff check`, Lighthouse (accessibility >= 95); create a `package-lock.json` deliberately before relying on `npm audit`; push and watch the first GitHub Actions run.
6. Rotate the exposed Gemini/OpenAI keys; approve retention periods (`MESSAGE_RETENTION_DAYS` stays `0`; the 730-day report default is NOT approved) and the listing soft-delete policy.

### Next-session plan
1. 3.12 environment + PostgreSQL Python modules. 2. Vendor and self-host assets, tighten CSP, test camera/OCR/PDF. 3. Pins and scans. 4. First real CI run and fixes. 5. Soft delete once policy is explicit. 6. Agents SDK only after every gate.

---

# Hand-off: KPT upgrade (status after session 17: TOTP review, strict `/chatbot-demo`, two pins)

## Session 17 result
**Important caveat first: the real `pyotp` could not be installed in this sandbox** (no network; `pip download pyotp==2.10.0` -> "No matching distribution found"; the wheel from session 16 was not among this session's uploads, so its SHA-256 could not be compared). Results marked **[stand-in]** below used a throwaway RFC 6238 implementation placed outside the repo (`/tmp/pyotp_shim`, validated against the RFC 6238 test vectors at t=59 and t=1111111109, never committed or shipped). They prove the project's own TOTP logic, not the `pyotp` library. The pinned `pyotp==2.10.0` was verified against the real wheel in session 16 (historical).

### Baseline (before any edit)
* Checkout: no `.git` directory (a diff/status could not be reviewed). Python 3.12.3 (matches `.python-version`), `cryptography` 46.0.6, Playwright 1.56.0 + Chromium available, no `.venv` used (system interpreter), no `package-lock.json`.
* `npm run test:all`: **119 JS pass; Python: 8 test modules failed to import** because `backend/services/totp_service.py` did `import pyotp` at module level, so the whole application could not start without the package.

### Implemented this session
| Change | Where |
|---|---|
| **Fix (availability):** a missing `pyotp` no longer crashes the app. TOTP fails closed with `503 totp_unavailable` (same path as a missing key); nothing is stored; login and the rest of admin keep working while `ADMIN_TOTP_REQUIRED=0` | `backend/services/totp_service.py` (`pyotp = None` fallback, check in `_fernet()`), `tests/backend/test_totp_missing_library.py` (2 tests, run without `pyotp`) |
| **Fix (usability):** malformed ban requests (`kind`, `days`) are validated before the one-time step-up proof is consumed; state checks (already banned / not banned) deliberately stay after the proof so authorization ordering is unchanged | `ModerationService.validate_ban_request`, `api/admin.py`, `test_malformed_ban_requests_do_not_burn_the_one_time_proof` |
| Documented + tested the Google-only admin limitation (no password => `403 reauth_failed`, cannot enrol or do sensitive actions; fix = set a password via the reset flow) | `docs/ADMIN.md`, `GoogleOnlyAdminTests` |
| `/chatbot-demo` now served **without** `style-src 'unsafe-inline'` (its only inline `<style>` moved to `frontend/css/widget-demo.css`; widget writes styles only through the CSSOM). No page is served with `'unsafe-inline'` any more | `backend/security/headers.py`, `frontend/widget/demo.html`, `tests/frontend/strictStyles.test.js`, `StrictStyleTests`, `tests/browser/csp_test.py` |
| Pins: `cryptography==46.0.6`, `playwright==1.56.0` (both actually exercised here on Python 3.12.3) | `pyproject.toml`, `docs/DEPENDENCIES.md` |
| Test race removed: `listing_lifecycle_test.py` asserted right after the "Saved" status, one request before the list refetch finished. It failed intermittently on the **untouched** session 16 tree too (1 of 2 runs). The page was not changed. | `tests/browser/listing_lifecycle_test.py` |
| Docs: `ADMIN.md` (edge cases), `KNOWN_ISSUES.md`, `DEPENDENCIES.md`, `CHANGELOG.md` | |

### TOTP review result (read against code, not just the handoff)
Confirmed in code and tests: Fernet-encrypted secrets, fail-closed key handling, pending inactive until confirmed, atomic replay protection (`UPDATE ... WHERE last_step < ?`), attempt rate limiting and audit without codes/proofs, hashed single-use short-lived proofs bound to admin + session + action class (atomic `UPDATE ... WHERE used_at IS NULL AND expires_at >= ?`), ban/reinstate/disable/enable/role/CSV all gated, CSV GET refused when TOTP is active or required, demotion removes TOTP state, protected-account and last-admin checks run before the proof, recovery script is dry-run by default and needs `--confirm RESET`. No secret, code or proof is logged (no logging calls in the TOTP service/API). One proof per 120 s TTL covers any action of its class in that session (by design, documented). **No Google-password-free re-auth design was added.**

### Verification actually run (this session)
* `npm run test:all` **without** `pyotp` (this sandbox as-is): **120 JS pass**; Python **173 tests run, `test_admin_totp` cannot import** (needs the library to make codes) -> exit 1. This is expected without the dependency, not a pass of that module.
* `npm run test:all` **[stand-in]**: **120 JS + 198 Python pass** (historical 119 + 194; +1 JS strict-page test, +2 missing-library, +2 TOTP tests).
* Browser (Playwright 1.56.0, Chromium, throwaway DB, **[stand-in]** for the TOTP codes): `admin_totp_test`, `login_test`, `csp_test` (now includes `/chatbot-demo` opening, answering a question, zero violations), `smoke`, `messaging_test`, `cookies_test`, `listings_test`, `prefs_test` OK; `listing_lifecycle_test` OK 5 of 5 consecutive runs after the fix (it failed 1 of 4 runs before it, including on the original tree).
* Static only (NOT a run): migration `0007_admin_totp.sql` and the TOTP/step-up SQL use portable types (`TEXT`, `BIGINT`) and the PostgreSQL facade returns `cursor.rowcount` under autocommit, so the compare-and-set updates should be atomic there.

### NOT run / blocked (no network or tools here)
* **PostgreSQL:** no server, no `psycopg`, no `DATABASE_URL`. None of `test_admin_totp`, `test_listings_retention`, `test_moderation_messaging`, `test_listing_lifecycle` ran on PostgreSQL; migration 0007 was never applied there.
* **Real `pyotp`** and a **real authenticator app**; **GitHub Actions** (YAML inspected only: `ci.yml` browser loop includes `csp_test` and `admin_totp_test`; actions are pinned by major tag `@v4`/`@v5`, not commit SHA, left unchanged because SHAs could not be looked up); `pip-audit`, `bandit`, `ruff` (not installed); `npm audit` (fails: no lockfile, no network); Lighthouse; ZAP; Google OAuth, Resend, Vercel; live AI.
* **Strict-CSP third-party assets (priority B1):** needs downloads. Tesseract.js `@5` (unpinned), PDF.js 3.11.174 and Google Fonts are still loaded from CDNs without SRI; inventory and owner steps unchanged in `docs/KNOWN_ISSUES.md`. Property photo folder `Property Images` is still absent from the archive.
* **Pins still `PIN ME`:** `openai-agents`, `openai`, `google-auth`, `requests`, `psycopg[binary]`, `ruff`, `bandit`, `pip-audit`, `argon2-cffi` (none installable/exercised here).

### Owner actions (names only, never paste values)
1. On your machine with a fresh Python 3.12 `.venv`: review `scripts/install_deps.py`, install, confirm `python -c "import pyotp; print(pyotp.__version__)"` is `2.10.0` and that the wheel hash matches `1df2f6a1bcc3bb0716172a5215ddc2f8c7c7fd26a13df9927d52e1746934836c`, then run `npm run test:all` (expect 120 JS + 198 Python) and `python tests/browser/admin_totp_test.py`.
2. Generate `TOTP_ENCRYPTION_KEY` with the command in `docs/ADMIN.md`, back it up, set it locally and on Vercel. Enrol with a **real authenticator app**. For Google-only admins, set a password first. Rehearse `scripts/reset_admin_totp.py` on a copy of the database, **then** set `ADMIN_TOTP_REQUIRED=1`.
3. Run the four modules above against a throwaway PostgreSQL via `DATABASE_URL` (never print it).
4. Run `pip-audit`, `ruff check`, `bandit -r backend`, Lighthouse (accessibility >= 95), then pin the remaining `PIN ME` entries from versions that passed; create a lockfile before relying on `npm audit`.
5. Push to GitHub and read the first real Actions run; consider pinning actions to commit SHAs. Self-host Tesseract.js/PDF.js/fonts with SRI (steps in KNOWN_ISSUES). Rotate any exposed Gemini/OpenAI keys before live AI work.
6. Decisions still open: `MESSAGE_RETENTION_DAYS=0` (730-day default is not approved policy); `docs/LISTING_DELETION_PROPOSAL.md` (soft vs hard deletion). Agents SDK (Part 10) remains gated.

### Next-session plan
1. Owner feedback from items 1-3. 2. Third-party asset self-hosting + SRI (needs network), then tighten `script-src`/`connect-src`. 3. Pins/audits/lint/CI first run. 4. Password-free re-auth design for Google-only admins if wanted. 5. Retention and listing-deletion decisions, then implementation. 6. Part 10 only after every gate.

---

# Hand-off: KPT upgrade (status after session 16: admin TOTP + step-up)

## Session 16 result
**Implemented (priority A, now unblocked):** admin two-factor (TOTP) and step-up verification. Optional by default (`ADMIN_TOTP_REQUIRED=0`); recovery for `admin_001` is implemented and tested, so enforcement can be switched on by the owner once every admin has enrolled.

| Piece | Where |
|---|---|
| `TotpService`: Fernet-encrypted secrets (`TOTP_ENCRYPTION_KEY`, fails closed with 503 `totp_unavailable` when missing/invalid or after key rotation), pending vs active, library-generated codes (`pyotp`), +/-1 step window, replay protection via compare-and-set of the last accepted time step, one-time step-up proofs (only SHA-256 stored) bound to admin + session + action class + expiry | `backend/services/totp_service.py` |
| Admin TOTP routes: `GET /admin/totp/status`, `POST /admin/totp/enroll/start` (password re-auth), `/enroll/confirm`, `/disable` (password + code), `/stepup` (code -> proof); 8 attempts / 5 min per admin and IP, fail-closed limiter; audit events without secrets/codes/proofs | `backend/api/admin_totp.py`, `app.py` (`totp()`, `totp_limiter()`) |
| Step-up enforced on ban, unban, disable/enable (`moderation`), role change (`role_change`), CSV export (`csv_export`, now `POST` with proof; `GET` refused once TOTP is active/required); demotion deletes the admin's TOTP row; `ADMIN_TOTP_REQUIRED=1` blocks sensitive actions for unenrolled admins (`totp_enrollment_required`) but not login, reading, or enrolment | `backend/api/admin.py` |
| Recovery: `scripts/reset_admin_totp.py --user admin_001 [--confirm RESET]` (dry run by default; deletes secret + proofs, revokes sessions, audits `totp_reset_by_operator`; operator shell access only, no web bypass) | `scripts/reset_admin_totp.py` |
| UI: Security panel (enrol with one-time setup key, confirm, turn off), accessible `<dialog>` for the code, export buttons using POST + download | `frontend/admin.html`, `js/admin/admin.js`, `services/http.js` (`loadCsrf` exported) |
| Migration `0007_admin_totp.sql` (`admin_totp`, `admin_stepups`); config `TOTP_ENCRYPTION_KEY`, `ADMIN_TOTP_REQUIRED`, `TOTP_ISSUER`, `STEPUP_TTL_S`; `pyproject.toml`: `pyotp==2.10.0` pinned, `cryptography>=46,<47` declared (PIN ME); dependency test PLANNED list updated | |
| Docs: `docs/ADMIN.md` (how it works, key generation, rotation, recovery, enforcement order), `API.md`, `AUTH.md`, `KNOWN_ISSUES.md`, `DEPENDENCIES.md`, `DEVELOPMENT.md`, `SECURITY.md`, `CHANGELOG.md`, `.env.example` (names only) | |

## Verification (exact commands and results)
* Archive: the `.rar` was unpacked with `libarchive` through `ctypes` (no `unrar` here); `.venv`, `node_modules`, `__pycache__` and any `.env` were skipped, no secrets were read. **No `.git` directory** in the archive, so no diff was reviewed.
* Wheel: `python3 -m pip install --no-index --find-links offline_wheels "pyotp==2.10.0" --break-system-packages` -> already satisfied; `importlib.metadata.version("pyotp")` = `2.10.0`; a generated code verifies. sha256 of the wheel: `1df2f6a1bcc3bb0716172a5215ddc2f8c7c7fd26a13df9927d52e1746934836c`. Interpreter here: Python 3.12.3 (`.python-version` is 3.12; your Windows venv was 3.13.6, not used). Note `pyotp` has no `__version__` attribute: use `importlib.metadata`.
* Baseline before changes: `npm run test:all` = 119 JS + 164 Python, all passed (matches the last handoff).
* After changes: `npm run test:all` = **119 JS + 188 Python, all passed** (24 new in `tests/backend/test_admin_totp.py`: access control, CSRF, fail-closed key (none/empty/garbage), pending vs active, encryption at rest, no secret/code/proof in status or audit, replay, key rotation, disable, missing/invalid/expired/consumed/wrong-class/wrong-session/garbage proofs, protected account still protected, CSV POST/GET, rate limit + audit, demotion cleanup, default (off) behaviour, required mode, operator recovery incl. dry run, non-admin refusal).
* Browser (Playwright, throwaway DB): **new** `python tests/browser/admin_totp_test.py` OK (real wall-clock codes: enrol with wrong then right code, export download needing a code, wrong code stays in dialog, cancelled ban, ban with fresh code; ~1 min). Also OK: `csp_test.py`, `login_test.py`, `listings_test.py`. Not re-run this session: `messaging_test.py`, `cookies_test.py`, `smoke.py`, `listing_lifecycle_test.py` (pages unchanged except admin).
* Playwright note: `wait_for_function` is blocked by the strict CSP (`unsafe-eval`); use selector waits.

## Security/privacy notes
* TOTP secret shown once at enrolment, never returned again, never logged; codes and proofs never logged or audited; proofs stored hashed.
* Step-up checks run after request validation and the protected-account / last-admin checks, then consume the proof atomically (`UPDATE ... WHERE used_at IS NULL AND expires_at >= now`).
* `admin_001` is not exempt (it can and should enrol). Its recovery requires shell access with the real database URL.
* Admins who sign in only with Google have no password, so they cannot pass the existing password re-auth and therefore cannot enrol; unchanged limitation.
* No QR image (no QR library installed); users enter the key manually.

## Owner actions (variable names only)
1. Generate and set `TOTP_ENCRYPTION_KEY` in Vercel and local `.env` (command in `docs/ADMIN.md`). Keep a safe backup: losing it means re-enrolling every admin.
2. Run `python tests/browser/admin_totp_test.py` locally; try enrolment with a real authenticator app (not exercised here).
3. Enrol each admin, rehearse `scripts/reset_admin_totp.py` on a copy of the database, **then** set `ADMIN_TOTP_REQUIRED=1`. Do not set it before.
4. Apply migration 0007 to PostgreSQL (the app migrates on start) and run `tests.backend.test_admin_totp` against a throwaway `DATABASE_URL` (never print it).
5. Still pending from before: PostgreSQL run of `test_listings_retention`, `test_moderation_messaging`, `test_listing_lifecycle`; Google OAuth, Resend, Vercel checks; pin the remaining `PIN ME` packages from your tested environment (`openai-agents`, `openai`, `google-auth`, `requests`, `psycopg`, `cryptography`, `ruff`, `bandit`, `pip-audit`, `playwright`, `argon2-cffi`); run `pip-audit`, `npm audit`, `ruff check`, `bandit -r backend`, Lighthouse (accessibility >= 95), ZAP baseline; rotate any previously exposed Gemini/OpenAI keys. I did **not** run any of those, nor GitHub Actions. `offline_wheels/` and `.local/` were added to `.gitignore` / `.vercelignore`.

## Deferred / blockers
* Priority B fallback tasks were not needed. Strict-CSP asset hardening (Tesseract/PDF.js/fonts self-hosting + SRI, `/chatbot-demo` policy) remains open.
* `docs/LISTING_DELETION_PROPOSAL.md` still needs an explicit owner decision; message retention stays off (`MESSAGE_RETENTION_DAYS=0`); the 730-day report default is not approved policy.
* Agents SDK (Part 10) gated on pins, key rotation and offline fake-provider tests.
* No TOTP recovery codes or hardware keys. (Correction: `HEALTH_DETAIL_TOKEN` was already retired in an earlier session; `/health/detail` requires an admin session, and an older note saying otherwise was stale and is fixed.)

## Later in session 16 (same session, after the TOTP package)
* Verified `/health/detail` already needs an admin session; fixed the stale doc line.
* Strict-CSP asset hardening (B1) **not done**: needs downloads; inventory and exact owner steps are in `docs/KNOWN_ISSUES.md` ("Third-party asset inventory").
* Fallback B3 done: `tests/backend/test_ci_config.py` (6 static tests; found that the new `admin_totp_test` was missing from the CI browser loop, now added). **GitHub Actions has not run**; `bandit`, `pip-audit`, `ruff` are not installed here so the audit job is unproven and may fail on baseline findings.
* Totals: `npm run test:all` = **119 JS + 194 Python** pass.

## Next-session plan
1. Owner feedback after trying TOTP with a real app and PostgreSQL; fix what surfaces. 2. Strict-CSP asset hardening (priority B1) on a machine with network. 4. Pin dependencies and run the audits/linters in your environment, then CI. 5. Part 10 only after pins and key rotation.

---

# (Earlier hand-off follows)

## Session 15 result
**Gate (Phase 1) FAILED, so no TOTP code was written.** `python3 -c "import pyotp"` -> `ModuleNotFoundError: No module named 'pyotp'`; `pip download --no-deps pyotp` -> `No matching distribution found for pyotp` (PyPI blocked by the sandbox proxy). Fallback taken: Phase 2.
**Baseline:** `npm run test:all` = 119 JS + 157 Python pass. **After:** **119 JS + 164 Python** pass (7 new in `tests/backend/test_listing_lifecycle.py`).

### Implemented (Phase 2: My Listings lifecycle)
* `MessagingService.update_listing` / `set_listing_status`; routes `POST /api/v1/listings/<ref>/edit {title, area}` and `/status {status: active|closed}` (CSRF + rate limit; `/listings/` already covered by the CSRF regex).
* Owner-only; non-owner and unknown ref get the identical 404. Only title (3..120) and area (2..80) are editable (control chars removed, whitespace collapsed); `ref`, `id`, `seller_id`, `status`, `verified` in the body are ignored. Banned/inactive sellers get 403 on create, edit and reopen (service-level guard plus the session guard).
* Closed listings: gone from browse, `contactable:false`, no new conversations (404), sends in existing ones 409; existing conversations/messages/reports preserved and readable. Reopen restores.
* UI (`/listings`, My listings): Edit (inline form, Esc cancels and restores focus, validation, Saving/Saved/error via `aria-live`), Close/Reopen buttons, plain-text rendering, no `prompt()`/`confirm()`. Playwright `tests/browser/listing_lifecycle_test.py` passes and also fails on any native dialog or console error.
* **No hard delete** (test asserts DELETE/PUT/PATCH on a listing are not routed). Soft-delete proposal and retention implications: `docs/LISTING_DELETION_PROPOSAL.md`. `docs/MESSAGING.md`, `docs/API.md`, `docs/KNOWN_ISSUES.md` updated/reconciled.

### Added after the lifecycle slice (Phase 6, not run on GitHub)
`.github/workflows/ci.yml` (test, browser, bandit + pip-audit jobs), `.github/dependabot.yml` (pip, actions; model-locked packages excluded from grouping), `SECURITY.md` (owner must add a contact address), `CHANGELOG.md` (reconstructed from this file), `docs/ADMIN.md`, `docs/DEPLOYMENT.md`, `docs/adr/0001-0003`. YAML parses; the workflow has never executed, so expect small first-run fixes (the audit job will fail until PIN ME/unpinned deps are resolved). Actions use major tags, not SHAs.

### Verification actually run
`npm run test:all` (119 + 164); Playwright: `listing_lifecycle_test.py`, `listings_test.py`, `csp_test.py`, `messaging_test.py` all OK; `ruff check --select F,E9` on changed files (one pre-existing unused import in `api/messages.py`, left alone).
**Not run:** PostgreSQL, Google/Resend live, Vercel, Lighthouse, ZAP, `pip-audit`, `npm audit`, `bandit`, full-config `ruff` (about 1,100 baseline findings), live AI, camera/OCR/PDF under strict CSP, cookies/login/smoke/prefs browser tests (not re-run this session).

### Security/privacy
No secrets read or printed. IDOR covered by tests; messaging privacy unchanged (no bodies logged, nothing to AI). `MESSAGE_RETENTION_DAYS=0` kept; 730-day report default still NOT approved policy.

### Deferred (Phases 1, 3-6; blocked by sandbox or owner)
TOTP (needs `pyotp` + declare `cryptography`); self-host/pin Tesseract, PDF.js, fonts + SRI; `/chatbot-demo` CSP; dependency pins and scans (`PIN ME`); PostgreSQL run of `test_listings_retention`, `test_moderation_messaging`, `test_listing_lifecycle`; first real CI run; Agents SDK stays gated; rotate previously exposed Gemini/OpenAI keys.

### Your actions
Locally: `python scripts/install_deps.py --dev`, confirm `python -c "import pyotp"`, pin `PIN ME` ranges, run audits, run the three Postgres-sensitive tests, decide retention periods and the delete/grace policy.

### Next-session plan
1. TOTP once `pyotp` imports. 2. Decide soft delete (see proposal). 3. CSP asset pinning. 4. Pins + scans. 5. PostgreSQL run. 6. Fix first CI run.

---

# Hand-off: KPT upgrade (status after session 14: strict style CSP on every page)

## Session 14 result (continues session 13; `pyotp` gate re-checked implicitly: still not installable here, no TOTP code written)
**Verified now:** `npm run test:all` = **119 JS + 157 Python** pass (session 13: 113 + 157). Playwright (local server, throwaway DB) all OK: `csp_test.py` (extended), `messaging_test.py`, `cookies_test.py`, `login_test.py`, `smoke.py`, `listings_test.py`, `prefs_test.py`.
**Not run:** PostgreSQL, Google/Resend live, Vercel, Lighthouse, ZAP, `pip-audit`, `npm audit`, `ruff`, `bandit`, live AI, camera/OCR/PDF flows under the strict policy (no CDN access in the sandbox).

### Done: the main app page is strict too
* Migrated all 96 inline styles in JS templates: 85 static -> `u-*` classes (`css/utilities.css`, `!important`), tone colours -> `tone-*`, widths/photos -> `data-w`/`data-bg` applied by `ui/dataStyle.js` through the CSSOM. `index.html` links `utilities.css` last; `main.js` calls `initDataStyles()`.
* `STRICT_STYLE_PATHS` now includes `/` and `/index.html`: **no HTML page is served with `style-src 'unsafe-inline'`** (only `/chatbot-demo` keeps it). Tests: `strictStyles.test.js` (index graph, every `u-*`/`tone-*`/`bg-*` class used is defined), `dataStyle.test.js`, `StrictStyleTests`, `csp_test.py` (home, detail, verify, owner-verification and document views load with zero violations; migrated styles still apply).
* Bug found by a screenshot check and fixed: `url()` in a CSS custom property resolved against `/css/`, so photos would have 404ed. `resolveUrl` makes them absolute; covered by a unit test and a browser test.
* Caveat: the demo photos are not in the supplied archive (`Property Images` folder missing), so the hero shows only its gradient in the sandbox; this is unchanged from before. Please confirm on your machine that the hero and card photos appear.

### Not claimed
Strict CSP is complete for styles on every page, but not "done": Tesseract.js `@5` unpinned, PDF.js/Tesseract/fonts not self-hosted or integrity-pinned, camera/OCR/PDF flows unexercised under the policy, `/chatbot-demo` permissive. See `docs/KNOWN_ISSUES.md`.

### Your actions
1. Open the site locally, check property photos, the verify-document flow (camera, upload, OCR, PDF) and owner verification with DevTools console open; report any "Refused to apply inline style" or other CSP lines.
2. Run `python tests/browser/csp_test.py`. Earlier items: install deps and pin `PIN ME` ranges, audits/Lighthouse, PostgreSQL run of `test_listings_retention` and `test_moderation_messaging`, rotate exposed keys.

### Next-session plan
1. TOTP once `pyotp` imports (Fernet key `TOTP_ENCRYPTION_KEY`, step-up bound to session + action, audit, `admin_001` recovery tested first). 2. Pin/self-host Tesseract.js, PDF.js and fonts with SRI. 3. Dependency pins + scans. 4. PostgreSQL run. 5. My Listings edit/close/delete design with tests. 6. CI/Dependabot.

---

# Hand-off: KPT upgrade (status after session 13)

## Session 13 result
**`pyotp` gate: FAILED again, so no TOTP code was written.** Run in this sandbox: `python3 -c "import pyotp"` -> `ModuleNotFoundError: No module named 'pyotp'`; `pip download pyotp==2.9.0 -d /tmp/pp --no-deps` -> `No matching distribution found for pyotp==2.9.0 (from versions: none)` (no network). `cryptography` 46.0.6 imports here (so Fernet is available once `pyotp` is). No git metadata in the archive (`git status` -> not a git repository), so changes are tracked only by this file. All `PIN ME` entries in `pyproject.toml` are still unpinned (openai-agents, openai, google-auth, requests, psycopg, pyotp, ruff, bandit, pip-audit, playwright, argon2-cffi); none was pinned because none could be installed and tested here.

**Baseline before edits:** `npm run test:all` = 103 JS + 155 Python pass (matches session 12). **After edits:** `npm run test:all` = **113 JS + 157 Python** pass.
**Browser (Playwright, local server, throwaway DB), all OK:** `csp_test.py` (**new**, 25+ checks), `messaging_test.py`, `cookies_test.py`, `login_test.py`, `smoke.py`, `listings_test.py`, `prefs_test.py`.
**Not run:** PostgreSQL, Google/Resend live, Vercel, Lighthouse, ZAP, `pip-audit`, `npm audit`, `ruff`, `bandit` (tools/network unavailable here), live AI.

### Done: strict-CSP slice (Phase 2A fallback)
* Inventory written to `docs/KNOWN_ISSUES.md` (96 static `style=` uses in 5 JS template files, ~12 computed, 9 CSSOM writes that CSP allows, 2 HTML attributes).
* Migrated the 2 HTML inline styles to classes (`404.html` -> `.notfound` in `auth.css`; chat close button in `index.html` -> `.icon-btn-soft` in `overlays.css`).
* `backend/security/headers.py`: `STRICT_STYLE_PATHS` (login, signup, admin, privacy, messages, listings, nice-try) and HTML 404s are served with `style-src 'self' https://fonts.googleapis.com https://accounts.google.com/gsi/style`, i.e. **without `'unsafe-inline'`**. `/` still has it (JS templates). Other directives unchanged (`script-src-attr 'none'`, hash allowance for inline scripts kept; there are none today).
* Tests: `tests/frontend/strictStyles.test.js` (import-graph scan of each strict page, scanner self-test, path coverage), `StrictStyleTests` in `tests/backend/test_api.py`, `tests/browser/csp_test.py` (every strict page loads with zero `securitypolicyviolation`, an injected inline style IS blocked, `/` still allowed).
* **Strict CSP is NOT complete:** the main app page still needs `'unsafe-inline'`. Sequence in `docs/KNOWN_ISSUES.md`.

### Owner decisions / risks carried forward
* `MESSAGE_RETENTION_DAYS` stays `0`; the 730-day resolved-report default is not an approved policy.
* Seller-created listings stay labelled unverified. Rotate the previously exposed Gemini/OpenAI keys before any live AI work.
* Agents SDK remains gated (versions not installed/pinned, no live keys, no API inspection). Nothing was started.

### Your actions
1. On your machine: `python scripts/install_deps.py --dev` (review it first: it installs every declared group), then `python -c "import pyotp; print(pyotp.__version__)"`, `npm run test:all`, and pin each `PIN ME` with the `pip freeze` version that passed.
2. Run `python tests/browser/csp_test.py` locally once, then with a PostgreSQL `DATABASE_URL`: `python -m unittest tests.backend.test_listings_retention tests.backend.test_moderation_messaging`.
3. Run `pip-audit`, `npm audit`, `ruff check`, `bandit -r backend`, Lighthouse (accessibility >= 95) and report the real output. Rotate exposed keys.

### Next-session plan
1. If `pyotp` imports: Phase 1 TOTP (pending secret, Fernet-encrypted with `TOTP_ENCRYPTION_KEY`, step-up bound to session + action, one-time use, audited, `admin_001` recovery documented and tested before enforcement). 2. Strict-CSP steps 1-4 from `docs/KNOWN_ISSUES.md`. 3. Dependency pins + scans. 4. PostgreSQL run. 5. My Listings edit/close/delete design with tests. 6. CI/Dependabot after reading the real checkout.

---

# Hand-off: KPT upgrade (status after session 12)

## Session 12 result
**TOTP/step-up is STILL BLOCKED; no TOTP code was written.** Checks run now: `python -c "import pyotp"` -> `ModuleNotFoundError`; `pip download pyotp` -> `No matching distribution found` (no network in this sandbox). No project virtualenv exists in the archive, `scripts/install_deps.py` was not run (it installs every declared package). No Git metadata in the archive, so no diff was reviewed.

**Baseline run now (before edits):** `npm run test:all` = **99 JS + 154 Python** pass (Flask is present in this environment, so the "Flask absent" note in the session 12 prompt did not apply here).
**Final run (this session):** `npm run test:all` = **102 JS + 155 Python** pass. Browser tests run and passing: `listings_test.py`, `messaging_test.py`, `cookies_test.py`, `login_test.py`, `smoke.py`, `prefs_test.py`. Everything above in "Still open" was NOT run.

### Done: per-message report selection (the small independent slice)
- The report dialog now has a "What are you reporting?" menu: "The whole conversation" (default) or one of the **other person's** 20 most recent messages, shown as single-line plain-text previews (built with `textContent`). The chosen id is sent as `message_id`.
- Server rules (unchanged, now covered by tests): `message_id` must belong to the same conversation, else `400 invalid_message`; non-participants get 404; malformed ids are 400.
- Admin: the thread response marks the reported message (`reported: true`) and the admin view prefixes that line with `>> REPORTED MESSAGE >>`. Messages from other conversations never appear.
- Files: `frontend/js/features/reportTargets.js` (new, pure), `frontend/js/messages-page.js`, `frontend/messages.html`, `backend/services/messaging_service.py` (`report_thread`), `frontend/js/admin/admin.js`, `docs/MESSAGING.md`.
- Tests added: `tests/frontend/reportTargets.test.js` (3), `test_moderation_messaging.test_report_can_target_one_message_and_never_one_from_another_conversation`, and a real-browser check in `tests/browser/listings_test.py` (menu content, chosen id sent, default sends no id). No migration, no new endpoint, no new env var.

### Done after the first report: consent banner placement
`frontend/js/features/consent.js` + `frontend/css/consent.css`: while the banner is open the page reserves its height (`body.has-consent`, `--consent-h`, ResizeObserver with a resize fallback), the banner is capped at 70% of the viewport and scrolls internally, and the space is released on every choice. Accept/Reject remain equal. Tests: source check in `tests/frontend/reportTargets.test.js`; `tests/browser/cookies_test.py` now asserts reserved space, equal button size, no overflow at 360x640 with "Customise" open, and release after the choice.
**Latest run (after this change):** `npm run test:all` = **103 JS + 155 Python** pass; browser tests `listings_test`, `messaging_test`, `cookies_test`, `login_test`, `smoke`, `prefs_test` all pass.

### Still open
| Item | State | Next concrete action |
|---|---|---|
| **Admin TOTP + step-up** | BLOCKED (`pyotp` missing, no network) | networked machine, project venv: read `scripts/install_deps.py`, run `python scripts/install_deps.py --dev`, confirm `python -c "import pyotp; print(pyotp.__version__)"` in the interpreter that runs tests, then build per the session 12 prompt section 3 (`TOTP_ENCRYPTION_KEY` via Fernet; not mandatory until `admin_001` recovery is tested) |
| `PIN ME` ranges (openai-agents, openai, google-auth, requests, psycopg, pyotp, ruff, bandit, pip-audit, playwright, argon2-cffi) | NOT DONE | pin each only after install + tests pass |
| `pip-audit`, `npm audit`, `ruff`, `bandit`, Lighthouse, ZAP | NOT RUN | not installed / no network |
| PostgreSQL run of `test_listings_retention` + `test_moderation_messaging` | NOT RUN | throwaway `DATABASE_URL`, never print it |
| Google OAuth, Resend, Vercel env | NOT RUN | owner-configured live checks |
| Consent banner covering the page bottom | DONE (continuation of session 12) | page bottom is reserved while open; see `docs/COOKIES.md` |
| Agents SDK | GATED | pins, SDK API check, rotated keys, fake-provider tests first |
| Strict CSP (`style-src 'unsafe-inline'` still in `backend/security/headers.py`) | OPEN | inventory inline styles first, then remove with regression tests |
| CI/Dependabot, SECURITY/ADMIN/DEPLOYMENT/CHANGELOG/ADRs | NOT PRESENT | small slice after checking the real checkout (no `.github` in the archive) |
| My listings edit/close/delete | NOT BUILT on purpose | needs a separate design (ownership + status transitions) |

### Owner actions (names only)
1. Networked environment + project venv for the dependency install.
2. Rotate the exposed Gemini/OpenAI keys before any live AI work.
3. Approve message and resolved-report retention (default report age 730 days is NOT an approved policy); keep `MESSAGE_RETENTION_DAYS=0`; schedule `scripts/purge_messages.py` only after approval (dry-run first).
4. Variables: `DATABASE_URL`, `ADMIN_001_PASSWORD`, `IP_HASH_SALT`, Upstash vars, `GOOGLE_CLIENT_ID`, `RESEND_API_KEY`, `MAIL_FROM`, `APP_BASE_URL`; planned: `TOTP_ENCRYPTION_KEY`.

### Next session plan
1. TOTP/step-up once `pyotp` imports. 2. Pin dependencies and run audits/lint/Lighthouse. 3. PostgreSQL run of the two modules. 4. Consent-banner placement. 5. Strict-CSP inventory.

# Hand-off: KPT upgrade (status after session 11)

## Session 11 result
**TOTP/step-up is STILL BLOCKED. Nothing was written for it.** Checks run this session: `python -c "import pyotp"` -> `ModuleNotFoundError`; `pip install "pyotp>=2.9,<3"` -> refused by the system Python (PEP 668); earlier `pip download pyotp` -> "No matching distribution" (no network); `curl https://pypi.org` returned nothing. `scripts/install_deps.py` was reviewed but NOT run (it installs every package in `pyproject.toml`). `cryptography` 46.0.6 is installed. No Git metadata in the archive, so no diff was reviewed.

**Verified now:** `npm run test:all` = **99 JS + 154 Python** pass (baseline this session 99 + 153). Browser tests pass: `listings_test.py` (run twice), `messaging_test.py`, `cookies_test.py`, `login_test.py`, `smoke.py`, `prefs_test.py`.
**JS count note:** 99 is the real current count (the 93/95 figures in older handoffs are stale).

### Done this session (the one small independent item)
- **My listings pagination** (was capped at 200 with no paging): `GET /api/v1/listings/mine?page=&per_page=` now returns `{listings, total, page, per_page}` (`per_page` clamped 1..50, default 20, bad `page` -> 1). The UI shows 10 per page with Previous/Next, a status line and disabled-at-the-ends buttons; deleting the last item on a page steps back one page.
  Files: `backend/services/messaging_service.py` (`list_mine`), `backend/api/messages.py`, `frontend/listings.html`, `frontend/js/listings-page.js`, `frontend/css/listings.css`, `docs/API.md`, `docs/MESSAGING.md`.
  Tests: `test_listings_retention.test_my_listings_are_paginated_bounded_and_owner_only` (pages, no duplicates, clamping, owner-only), plus a browser check in `listings_test.py`.
- Found while testing: an existing assertion in `listings_test.py` raced the list refresh; it now waits for the row. In-page string evaluation (`wait_for_function`) is blocked by the strict CSP, so tests use selectors instead.

### Still open (unchanged unless noted)
| Item | State | Next concrete action |
|---|---|---|
| **Admin TOTP + step-up** | BLOCKED (`pyotp` missing, no network) | on a networked machine: `python scripts/install_deps.py --dev` (read it first), confirm `python -c "import pyotp; print(pyotp.__version__)"`, run `npm run test:all`, pin the version, then build TOTP |
| `PIN ME` dependency ranges (openai-agents, openai, google-auth, requests, psycopg, pyotp, ruff, bandit, pip-audit, playwright, argon2-cffi) | NOT DONE | pin each only after it installs and tests pass |
| `pip-audit`, `npm audit`, `ruff`, `bandit`, Lighthouse, ZAP | NOT RUN | tools/network unavailable here |
| PostgreSQL run of `tests.backend.test_listings_retention tests.backend.test_moderation_messaging` | NOT RUN | set a throwaway `DATABASE_URL`, run both modules |
| Google OAuth, Resend, Vercel env checks | NOT RUN | owner-configured live checks |
| Agents SDK | NOT STARTED, gated | needs pins, SDK API check, rotated keys, fake-provider tests |
| Consent banner covers the page bottom until a choice | OPEN | contained placement change keeping Accept/Reject equal |
| Report dialog: no per-message selection (API supports `message_id`) | OPEN | add selection limited to the reporter's own conversation, with tests |
| My listings edit / close / delete | NOT BUILT on purpose | needs server-side ownership + status-transition design and tests |
| Strict CSP, chatbot parity/streaming, UX audit/design system, CI/Dependabot, SECURITY/ADMIN/DEPLOYMENT/CHANGELOG/ADRs | NOT VERIFIED/STARTED | check `HANDOFF.md` and the code first; do small tested slices |

### Owner actions (names only, no values)
1. Provide a networked environment, install deps, send back any failures.
2. Rotate the exposed Gemini/OpenAI keys before any live AI work.
3. Approve message/resolved-report retention periods; keep `MESSAGE_RETENTION_DAYS=0` until then; schedule `scripts/purge_messages.py` (Vercel Cron or similar) only after approval.
4. Vercel/env variables: `DATABASE_URL`, `ADMIN_001_PASSWORD`, `IP_HASH_SALT`, Upstash vars, `GOOGLE_CLIENT_ID`, `RESEND_API_KEY`, `MAIL_FROM`, `APP_BASE_URL`. Planned for TOTP: `TOTP_ENCRYPTION_KEY` (not yet defined anywhere).

### Next session plan
1. TOTP + step-up (once `pyotp` imports): enrolment with re-auth, Fernet-encrypted secret, step-up for ban/unban, role change and CSV export bound to session + action + expiry, one-time use, rate limits, audit, documented `admin_001` recovery; not mandatory until recovery is tested.
2. Pin dependencies; run pip-audit, npm audit, ruff, bandit, Lighthouse.
3. Postgres run of the two test modules.
4. Banner placement, per-message report selection.

---

# Hand-off: KPT upgrade (status after session 10)

## Session 10 result
**Verified now (this environment, offline):** `npm run test:all` = **99 JS + 153 Python** pass (started at 95 + 153). Browser tests all pass against a throwaway local server: `listings_test.py`, `messaging_test.py`, `cookies_test.py`, `login_test.py`, `smoke.py`, and the new `prefs_test.py`.
**Count discrepancy resolved:** the real baseline was **95 JS** (the "93 JS" figure in the session 9 handoff was stale).

| Item | State | Where |
|---|---|---|
| Home area/type/sort remembered in `kpt_prefs` (Preferences consent only; tampered values ignored; search text never stored; "Largest" has no cookie code) | DONE, unit + browser tested | `frontend/js/features/homePrefs.js`, `home.js`, `main.js`, `tests/frontend/homePrefs.test.js`, `tests/browser/prefs_test.py` |
| Bug found by the new test: a non-string `sort` could index the code table (`['newest']` coerced to a key) | FIXED | `homePrefs.js` |
| Dismissed hints stay in `sessionStorage` (decision: session-scoped, not persistent; moving to a 6-month cookie would change behaviour) | DECIDED, documented | `docs/COOKIES.md` |
| **Admin TOTP + step-up (Priority 1)** | **BLOCKED, not started** | `pyotp` not installed and pip cannot download it (no network). No speculative code written. Next action on your machine: `python scripts/install_deps.py --dev`, confirm `import pyotp`, then start session 11 with TOTP. |
| Dependency pins (`PIN ME` in `pyproject.toml`: openai-agents, openai, google-auth, requests, psycopg, pyotp, ruff, bandit, pip-audit, playwright, argon2-cffi) | NOT DONE | needs network + a passing install; do not pin from guesses |
| `pip-audit`, `npm audit`, `ruff`, `bandit` | NOT RUN | tools not installed; `npm audit` needs a lockfile/network |
| Lighthouse | NOT RUN | no Lighthouse in this environment |
| Real Postgres run of `tests.backend.test_listings_retention` and `test_moderation_messaging` | NOT RUN (owner action) | set `DATABASE_URL` to a throwaway database and run them |
| Agents SDK (Part 10) | NOT STARTED, gated | `openai-agents`/`openai`/`google-genai` not verifiable offline; keys must be rotated first |
| Consent banner covers the page bottom until a choice is made | OPEN | not changed this session |
| Saved/compare controls, `lang` selector | NOT BUILT on purpose | no such UI exists; do not add inert controls |

### Your actions
1. `python scripts/install_deps.py --dev` on a networked machine; then `npm run test:all` and the browser tests; pin the tested versions (replace each `PIN ME`).
2. Run `pip-audit`, `npm audit`, `ruff check`, `bandit -r backend` and record the output.
3. Run the two Postgres-only test modules against a throwaway database.
4. Rotate the previously exposed Gemini/OpenAI keys before any live AI work. Set variable *names* only in Vercel: `DATABASE_URL`, `ADMIN_001_PASSWORD`, `IP_HASH_SALT`, Upstash vars, `GOOGLE_CLIENT_ID`, `RESEND_API_KEY`, `MAIL_FROM`, `APP_BASE_URL`, `MESSAGE_RETENTION_DAYS` (keep 0 until the policy is approved).
5. Schedule `scripts/purge_messages.py` (Vercel Cron or similar) only after retention periods are approved.

### Next session plan (priority order)
1. Admin TOTP + step-up (needs `pyotp`): enrolment with re-auth, secret encrypted with `TOTP_ENCRYPTION_KEY` (cryptography is installed), step-up for ban/unban, role change and CSV export bound to session + action + expiry, one-time use, rate limits, audit, documented `admin_001` recovery; do not make it mandatory until recovery is tested.
2. Pin dependencies and run the audits/lint/Lighthouse.
3. Consent-banner placement, report-dialog per-message selection, My-listings pagination.
4. Agents SDK slice (only after the gate in the session 10 prompt passes).

---

# Hand-off: KPT upgrade (status after session 9: listings UI, messaging dialogs, retention)

## Session 9 result
**Verified:** `npm run test:all` = **93 JS + 153 Python** pass (session 8: 93 + 137). Playwright against a local server with a throwaway DB: **new** `tests/browser/listings_test.py` OK; `messaging_test.py` OK. Not run: Postgres, live Google/Resend, Lighthouse, any security scan, `cookies_test.py`/`login_test.py` this session (their pages were not changed).

### Phase 1 (admin TOTP + step-up): BLOCKED, deliberately not started
`pyotp` is not installed and cannot be installed here (no network: `pip download pyotp==2.9.0` -> "No matching distribution"). The plan forbids hand-rolled TOTP crypto or speculative APIs, so nothing was written and the `PIN ME` marker on `pyotp` in `pyproject.toml` is unchanged. Concrete local steps: (1) `pip install "pyotp>=2.9,<3"` and `python -c "import pyotp; print(pyotp.__version__)"`; (2) decide the secret-at-rest key: `cryptography` 46.0.6 is installed here, so use `cryptography.fernet` with a new env var (e.g. `TOTP_ENCRYPTION_KEY`, generated with `Fernet.generate_key()`, documented rotation = re-enrol); (3) start from Phase 1 of `KPT_upgrade_prompt_v6.md`. `admin_001` recovery must stay documented before TOTP is made mandatory.

### Done (Phases 2 and 3)
| Item | State | Where |
|---|---|---|
| Seller flow: Create listing, My listings, public browse (paginated), detail with "Chat with seller", labelled "Seller-submitted, unverified"; double-submit guard, loading/success/error text, plain-text rendering | DONE | `frontend/listings.html`, `js/listings-page.js`, `css/listings.css`, `/listings` route, sitemap |
| APIs: `GET /listings` (public, active listings of active sellers, no seller identity), `GET /listings/mine` (owner-only); `POST /listings` ignores client `seller_id`/`ref`/`status` | DONE | `api/messages.py`, `services/messaging_service.py` |
| Banned/disabled sellers vanish from browse and cannot be contacted; banned users cannot create | DONE + tested | `tests/backend/test_listings_retention.py` |
| Report / Block / **Unblock** in accessible in-page `<dialog>`s (no `prompt()`/`confirm()`), report reason validated 3 to 500 chars inside the dialog, Esc cancels, effect explained; `blocked_by_me` flag (own block only) | DONE | `messages.html`, `js/messages-page.js`, `css/messages.css` |
| Retention: `RetentionService` + `scripts/purge_messages.py` (dry run by default, `--apply`, `--batch`), **disabled until `MESSAGE_RETENTION_DAYS` > 0**; open reports/referenced messages protected; idempotent, bounded, counts only | DONE (SQLite-tested) | `services/retention_service.py`, `docs/MESSAGING.md` |
| Docs/env: `MESSAGING.md` (listings + retention), `API.md`, `DEVELOPMENT.md`, `.env.example` | DONE | |
| Browser test: seller creates listing -> buyer finds it -> chat -> report/block/unblock dialogs | DONE | `tests/browser/listings_test.py` |

### Decisions / assumptions to approve
* **Retention periods are NOT decided.** Defaults: messages off (0), resolved reports 730 days. Pick real values (legal review) before setting `MESSAGE_RETENTION_DAYS` in production. No scheduler is configured; the script must be run by Vercel Cron or similar.
* Seller listings are a **separate path** from the CSV property pages (no price/photos/ownership); integrating them with CSV data needs an ownership-verification design.
* The report dialog does not offer per-message selection (API still supports `message_id`).

### Added after the first package (same session)
* **Recently viewed** (Phase 4, first piece): opening a CSV listing (`/#/plot/<id>`) records its id in `kpt_prefs.recent` (max 20, newest first, de-duplicated; cookie only with Preferences consent, otherwise this visit only) via `addRecent` in `core/cookies.js`. The chat's "Continue with …" chip now works for returning visitors (verified in `tests/browser/cookies_test.py`). Demo properties p1..p8 are not recorded (the chat chip resolves CSV ids only). JS tests: 95.
* Still open in Phase 4: filters, sort, saved/compare (no such UI exists), `lang` (no translations), dismissed hints (still `sessionStorage`), consent banner placement.

### Not done / open
* Admin TOTP + step-up (blocked above); no edit/delete/close for listings; no pagination UI for My listings (max 200); no automatic message purge schedule.
* Phase 4 (preferences: filters/sort/recent/saved/`lang`/dismissed hints into `kpt_prefs`; consent banner covering the page bottom) not started.
* Phase 5 (pin `PIN ME` ranges, `pip-audit`, `npm audit`, live Postgres/Google/Resend checks) and Phase 6 (Agents SDK) remain gated on your machine.
* Retention SQL and the new listing queries were only run on SQLite.

### Your actions
1. `python tests/browser/listings_test.py` locally once; try the flow by hand (sign up, `/listings`, create, second account, chat).
2. Run `python -m unittest tests.backend.test_listings_retention tests.backend.test_moderation_messaging` against a real Postgres `DATABASE_URL`.
3. Decide retention periods; then `MESSAGE_RETENTION_DAYS=<n> python scripts/purge_messages.py` (dry run) and review counts before `--apply`.
4. Install `pyotp` locally (see above) so the next session can do Phase 1. Earlier items still stand (Postgres, Google, Resend, pins, audits, rotate exposed keys).

### Next-session plan
1. Phase 1 TOTP + step-up (after `pyotp` is installable). 2. Phase 4 preference wiring. 3. Phase 5 dependency pins/audits. 4. Part 10 only after your checks. 5. CSP/UX/CI sessions.

---

# (Earlier hand-off: session 8)

## Session 8 result
**Verified:** `npm run test:all` = **93 JS + 137 Python** pass (session 7: 87 + 114). Playwright (local server, throwaway DB):
`tests/browser/messaging_test.py` (**new**, 10 checks), `cookies_test.py`, `login_test.py`, `smoke.py` all OK.
Not run: Postgres, live Google/Resend, Lighthouse, any security scan. The new SQL was only run on SQLite.

| Item | State | Where |
|---|---|---|
| Ban / suspend (temporary with expiry, permanent) + Reinstate, reason required, central enforcement (session, password, Google, remember-me), sessions + remember tokens revoked at once, lazy expiry, history table | DONE | `services/moderation_service.py`, `api/admin.py`, migration 0006 |
| Protections: self-ban, `admin_001` (no disable/ban/demote), admins must be demoted before ban, last-active-admin guard | DONE | `api/admin.py` `_protect` |
| Admin users: search, status/role filter, sort, pagination, ban info; login events: filter + pagination, newest first, hashed IP only | DONE | `api/admin.py`, `frontend/admin.html`, `js/admin/admin.js` |
| Audit-log view, CSV export (users, login events; audited, formula-safe), `HEALTH_DETAIL_TOKEN` retired (admin session instead) | DONE | `api/admin.py`, `api/health.py` |
| Messaging: listings, conversations, messages, unread, polling, block, report, audited admin report review, retention on account deletion | DONE | `services/messaging_service.py`, `api/messages.py`, `docs/MESSAGING.md` |
| UI: `/messages` page (inbox + thread, plain-text rendering), "Chat with seller" on property detail, login return path | DONE | `messages.html`, `js/messages-page.js`, `features/sellerChat.js` |
| Demo data: `scripts/seed_demo_listings.py` (local only, password from `DEMO_SELLER_PASSWORD`) | DONE | |
| Docs: `MESSAGING.md`, `API.md`, `AUTH.md`, `DEVELOPMENT.md` updated | DONE | |

### Decisions you should know about
* Demo properties are static and have no seller account, so messaging uses a new `listings` table. Until a listing row exists for a
  property (seed script, or `POST /listings`), "Chat with seller" says messaging is not available. No UI to create listings yet.
* "Contact Seller" still opens the AI assistant; "Chat with seller" is the real seller message flow.
* Reason is required for ban, unban and report resolution; for plain Disable/Enable it is optional (stored in the audit detail).
* Ban state lives in `users.status = 'banned'`; a banned user's login looks like a wrong password (reason recorded in login events).
* Bans never delete messages. Account deletion deletes messages except conversations with an open report.

### Not done / still open (tracked, not hidden)
* **TOTP / second factor for admins:** not started (needs `pyotp`, which is not installed here, plus enrolment UI). Next: add pinned `pyotp`, `admin_totp` table, enrol + verify on sensitive actions.
* No automatic purge for old messages/resolved reports; no "unblock" button in the UI (endpoint exists); block/report use `prompt/confirm` dialogs.
* No attachments (v1 text only). No push/real-time: polling every 6 s.
* No listing-creation UI; no per-IP view for admins (hashed IPs only by design).
* The consent banner covers the bottom of the page until a choice is made (the browser tests dismiss it first).
* Part 10 (Agents SDK dual engines) deferred as required by the prompt: needs network + keys; start only after your checks below.
* Everything under session 7's "Not done" (filters/sort/recent written to `kpt_prefs`, `lang` UI, dismissed hints) still applies, as do sections A-E below.

### Your actions
1. Run `python tests/browser/messaging_test.py` locally once (Playwright + Chromium); then try the flow by hand: `DEMO_SELLER_PASSWORD=... python scripts/seed_demo_listings.py`, sign up, open a property, "Chat with seller".
2. Run `python -m unittest tests.backend.test_moderation_messaging` against a real Postgres `DATABASE_URL` (migration 0006 and the lazy ban expiry were only run on SQLite).
3. Set `MESSAGE_RATE_LIMIT_PER_MIN` if the default 20/min is wrong for you. Earlier open items still stand: Postgres test, Google OAuth + Resend live tests, pin remaining `PIN ME` ranges and run `pip-audit`/`npm audit`, Vercel env vars, **rotate previously exposed keys**, Lighthouse (accessibility >= 95).

### Next-session plan
1. Admin TOTP + step-up for ban/role changes. 2. Listing-creation UI and unblock/report dialogs without `prompt()`. 3. Message retention job + docs. 4. Part 10 once the dependency pins and live keys are verified on your machine. 5. CSP/UX/CI sessions from the old outline.

---

# Hand-off: KPT upgrade (status after session 7)

## Session 7 result: Part 2B is complete (frontend finished)
**Verified:** `npm run test:all` = **87 JS + 114 Python** pass (session 6: 76 + 111). Playwright, run against a local server with a throwaway DB: `tests/browser/cookies_test.py` (**new**), `login_test.py`, `smoke.py` all OK. Not run: Postgres, live Google/Resend, Lighthouse.

| Part 2B item | State | Where |
|---|---|---|
| `core/cookies.js` (safe get/set/remove, consent-aware, memory fallback) + `core/prefs.js` (twin of `services/prefs.py`, shared cases `tests/shared/prefs_cases.json`) | DONE | `frontend/js/core/`, `tests/frontend/cookies.test.js` |
| Consent banner (Essential / Preferences / Analytics, equal-weight Reject and Accept, version check) on index, login, admin, privacy | DONE | `features/consent.js`, `consent-banner.js`, `css/consent.css` |
| `/privacy` page: toggles, cookie table (test keeps it equal to `docs/COOKIES.md`), Forget me, devices list + remove, log out everywhere, delete my data | DONE | `frontend/privacy.html`, `js/privacy-page.js`, `css/privacy.css` |
| "Remember me" checkbox on login (password + Google), `remember_note` shown | DONE | `login.html`, `auth-page.js` |
| Theme via `kpt_prefs` (no `localStorage`); `theme-init.js` is an external script, so **no inline script remains on any page** (CSP hash no longer needed; legacy inline redirect in `orv.html` removed) | DONE | `theme-init.js`, `features/theme.js`, `index.html` |
| Prefs merged into account on login | DONE | `services/accountApi.js` |
| Chat continuity: session restore + welcome-back, no `session_id` when `continuity`, Start over clears the stored chat | DONE | `features/chat.js`, `services/chatApi.js` |
| Footer link "Privacy & cookies" (index, login) | DONE | |

Bug found by the browser test and fixed: the new checkbox crashed the login form's field-error code (the checkbox no longer has a `name`; error loop skips checkboxes).

### Not done / still open
- **Filters, sort, recently viewed, compare/saved ids in `kpt_prefs`:** the cookie layer, validators and merge exist and are tested, but the UI features that would *write* them (property filters, sort, recently viewed, saved/compare) are not wired; only `theme` is written today. The chat "last viewed" chip needs `recent` to be written when a listing opens (`writePrefs({recent: [...]})` in `features/listing.js` / detail view).
- Language (`lang`) has no UI yet. Dismissed hints (`promo`, etc.) still use `sessionStorage` (`features/promo.js`), not the cookie.
- Banner covers the bottom of the page until the visitor chooses (documented).
- Part 10 (Agents SDK dual engines): **not started** (needs network + keys; do on your machine).
- Everything under "Not done" in sections A/B/C/D/E below still applies except Part 2B and Google/forgot-password (done).

### Your actions (new)
1. Run `python tests/browser/cookies_test.py` and `login_test.py` locally once (they need Playwright + Chromium).
2. Try the banner at `/privacy` on your Vercel preview over https: names should carry the `__Host-` prefix there (not exercised in the sandbox, which is http).

---


## Session 6 result (this is what actually got done)
**Verified: `npm run test:all` = 76 JS + 111 Python tests pass** (84 + 27 new in `tests/backend/test_cookies.py`). Not run: Playwright, Postgres, live Google/Resend. Sandbox has scikit-learn 1.8.0, not the pinned 1.9.1 (tests still pass).

| Part 2B piece | State | Where |
|---|---|---|
| Migration 0005 (`remember_tokens`, `user_prefs`, `chat_sessions`) | DONE | `backend/db/migrations/0005_*.sql` |
| Consent record parser (`kpt_consent` = `v=1&p=0/1&a=0/1`, version-checked) | DONE | `backend/security/consent.py` |
| Remember-me: selector+validator, hashed validator, rotation, replay revokes all (10 s race grace), admins never get one, password change/reset/disable revokes all | DONE | `services/remember_service.py`, `security/guards.py`, `api/auth.py`, `session_service.py` |
| `remember: true` on password + Google login (needs Preferences consent; body says `remembered` / `remember_note`) | DONE (API only) | `api/auth.py` |
| Devices list/revoke, logout-all, per-device logout, forget-device, account prefs GET/PUT, delete-account (password re-auth) | DONE (API only) | `api/account.py`, `AuthService.delete_account` |
| Prefs validator (codes/ids only, clamped, merge on login) | DONE (Python) | `services/prefs.py` |
| Chat cookie `__Host-kpt_chat` (only with consent), DB-persisted conversation, `GET /chat/session`, welcome-back (first name only when signed in; anonymous gets last-viewed chip), Start over clears stored chat | DONE (API only) | `api/chat.py`, `services/chat_store.py`, `chat_service.py` |
| `/privacy` route, `docs/COOKIES.md`, `.env.example` (`REMEMBER_DAYS`, `CHAT_COOKIE_DAYS`) | route + docs DONE, **page itself not built** | `web.py`, `docs/` |

### (Session 6 list, now DONE in session 7)
1. `frontend/js/core/cookies.js` (safe get/set/remove, consent-aware) + `core/prefs.js` (JS twin of `services/prefs.py`; reuse `PrefsTests.CASES`) + `tests/frontend/cookies.test.js`.
2. Consent banner (Essential / Preferences / Analytics, "Reject non-essential" equal to "Accept all") on index, login, admin; writes `kpt_consent`.
3. `frontend/privacy.html` + JS/CSS: toggles, cookie table (from docs/COOKIES.md), signed-in devices list, "Forget me on this device" (call `/auth/forget-device`, clear `kpt_prefs`/`kpt_consent`), "Log out of all devices", "Delete my data".
4. "Remember me" checkbox on login.html/auth-page.js (send `remember`, show `remember_note`).
5. Replace theme `localStorage` (inline script in `index.html`, `theme-init.js`, `features/theme.js`) with `kpt_prefs`; apply prefs before first paint; merge cookie prefs into account via `PUT /auth/prefs` on login. CSP hash of the inline script recomputes automatically.
6. Chat UI: call `GET /api/v1/chat/session` on open, render history + welcome; send no `session_id` when `continuity` is true. Add the Playwright test for banner choices and remember-me round trip.
7. Docs: update `API.md` (new endpoints, `continuity` field), `AUTH.md`, `DEVELOPMENT.md` env table.

### Part 10 was NOT started
`openai-agents` is not installable in this sandbox (no network), and the plan requires verifying the installed SDK API. Do it on your machine/coding tool after pinning dependencies.

---

## Original plan and status table (from session 5; Part 2B backend is now done)


## 1. State of every part

| Part | State | Notes |
|---|---|---|
| Sanitised public CSVs, server-side owner check (`POST /verification/check`, login required) | DONE | session 1-2 |
| Security headers/CSP, pluggable rate limiter (Upstash), `X-Forwarded-For` handling | DONE | `style-src 'unsafe-inline'` still open (see 4) |
| DB facade (SQLite local, Postgres prod), migrations 0001-0004 | DONE, **Postgres never run live** | tables: users, sessions, login_events, audit_log, chat_feedback, google, password_resets |
| scrypt passwords, server sessions, CSRF, signup/login/logout/me/change-password, lockout, `admin_001`, `/nice-try` | DONE | |
| Admin page: users, login feed, sessions, disable/enable, role change (re-auth + audit), force logout | DONE | |
| Part 1A login/sign-up rebuilt to reference design, Playwright test committed | DONE | Poppins 600 renders as 700; Lighthouse not run |
| Google sign-in (GIS + server verification, link-by-verified-email, `ADMIN_EMAILS` Google-only) | DONE, **not run against live Google** | |
| Forgot / reset password, Resend mailer | DONE, **not run against live Resend** | |
| Part 11: merged `pyproject.toml`, `install_deps.py --dev/--extra`, `docs/DEPENDENCIES.md`, `test_dependencies.py` | PARTIAL | `PIN ME` ranges still unpinned (see 3) |
| Chatbot: router, advisor, memory, plot cards, deep links, structured response, feedback, hand-off buttons | DONE (rule-based; Gemini path untested live) | |
| Inline `onclick` migration, robots.txt, sitemap.xml, 404 | DONE per the v2 prompt | verify: `grep -c "data-on" frontend/index.html`, and check no `onclick=` remains; an inline `<script>` is still at the top of `index.html` |
| **Part 2B cookies** (consent, `kpt_prefs`, remember-me, chat cookie, privacy page) | **TODO** | `backend/security/cookies.py` is only a name/flag helper |
| **Part 10 dual AI engines (Agents SDK)** | **TODO** | `backend/services/ai/` does not exist; `gemini_engine.py` still calls `google-genai` directly |
| Admin extras: TOTP, CSV export, chat analytics, audit-log page, retire `HEALTH_DETAIL_TOKEN` | TODO | token still in `config.py` |
| CSP remainder: inline styles, pin/self-host Tesseract (`@5` still unpinned) and PDF.js, fonts | TODO | |
| Chatbot leftovers: widget parity (shared render module, safe `md()`), streaming, idle nudge, saved plots/history, first-name greeting | TODO | |
| Part 7 UX audit, design system, a11y, performance, Lighthouse, committed smoke tests | TODO | `tokens.css` exists (login only) |
| Docs still missing: `SECURITY`, `COOKIES`, `ADMIN`, `AI`, `DESIGN_SYSTEM`, `UX_AUDIT`, `DEPLOYMENT`, `CHANGELOG`, `adr/` | TODO | existing: API, ARCHITECTURE, AUTH, CHATBOT, DEPENDENCIES, DEVELOPMENT, KNOWN_ISSUES, MIGRATION |
| CI (GitHub Actions), Dependabot, ruff, bandit, pip-audit, npm audit, ZAP, headers grade | TODO, **no scans ever run** | no `.github/` folder yet |

Corrections to the v2 prompt's status table: Part 1A, Google sign-in, forgot-password and most of Part 11 are
done, not TODO. `vercel.json` already has a `headers` block for `/assets/*`.

---

## 2. Your actions (outside the coding tool)

1. **Step 0, Postgres:** create a Neon or Supabase database, set `DATABASE_URL`, run
   `python -m unittest tests.backend.test_auth` against it. Send the first failures to the next session.
2. **Pin dependencies:** `python scripts/install_deps.py --dev && npm run test:all`, then replace each `PIN ME` range in
   `pyproject.toml` with the `pip freeze` version that passed (openai-agents, openai, google-auth, requests,
   psycopg, pyotp, ruff, bandit, pip-audit, playwright; google-genai too if not exact). Remove the comments.
3. **Google client:** create the OAuth Web client (steps in `docs/AUTH.md`), add each origin you use plus the Vercel
   domain, set `GOOGLE_CLIENT_ID`. Try the login locally once.
4. **Resend:** set `RESEND_API_KEY`, `MAIL_FROM`, `APP_BASE_URL`; test forgot-password locally once.
5. **Vercel env vars:** `DATABASE_URL`, `ADMIN_001_PASSWORD` (14+ chars), `IP_HASH_SALT`, Upstash vars,
   `ADMIN_EMAILS`, `GOOGLE_CLIENT_ID`, mail vars. Safari on `http://localhost` needs `COOKIE_SECURE=0`.
6. **Secrets hygiene:** old CSVs with owner names are in git history; earlier archives contained `.env` files with
   Gemini/OpenAI key entries. Treat those keys as compromised and rotate them.
7. Run Lighthouse on the login page and record the numbers (target Accessibility >= 95).

---

## 3. Session 6 plan

**Goal:** returning visitors are remembered (Part 2B) and the chatbot runs on the Agents SDK with failover (Part 10 core).
Admin extras, CSP and UX stay for later sessions so each session stays reviewable.

### Phase 6.0: baseline (15 min)
- Run `npm run test:all`; expect 76 JS + 84 Python. If you did Step 0 / pins, fold the fixes in first.
- Confirm the inline-handler migration (grep) so the CSP assumptions hold.

### Phase 6.1: Part 2B cookies
Build in this order, each with tests:
1. **Server:** extend `security/cookies.py`; new `services/remember_service.py` + migration 0005 (`remember_tokens`: selector,
   validator_hash, user_id, device_label, created, last_used, expires) and `user_prefs` (JSON, for merge on login).
   `__Host-kpt_remember` selector+validator, rotate on use, reuse of an old validator revokes all of that user's tokens.
   "Remember me" checkbox on login (password + Google). Re-auth for sensitive actions; `admin_001` never gets a long token.
2. **Chat cookie:** `__Host-kpt_chat` (random id only, 7 days); `services/memory.py` keyed by it; "Start over" endpoint.
3. **Frontend:** `js/core/cookies.js` (safe get/set/remove, consent-aware, never throws, clamps/validates on read);
   `kpt_prefs` (theme, language, filters, sort, recently viewed max 20, compare/saved IDs, dismissed hints; short codes only, < 4 KB);
   replace `core/storage.js` UI-preference use; `kpt_consent` with version; banner with Essential / Preferences / Analytics,
   "Reject non-essential" equal weight to "Accept all"; Privacy & cookies page (`/privacy`) with per-cookie table, "Forget me on this
   device", "Delete my data"; "Signed-in devices" list with revoke.
4. **Greeting:** "Welcome back, <first name>" for signed-in users; chip for last viewed property / search for anonymous.
5. **Docs/tests:** `docs/COOKIES.md` (table kept in sync), tests from the prompt: flags on every Set-Cookie, nothing optional before consent,
   reject removes optional cookies, rotation and reuse revocation, tampered/expired `kpt_prefs` ignored, "Forget me" clears all,
   no PII in cookie values (grep test), saved theme/filters on return, chat context survives refresh.

**Exit criteria:** `npm run test:all` green; Playwright test for banner choices and remember-me round trip; `docs/COOKIES.md` matches the code.

### Phase 6.2: Part 10 core (Agents SDK)
Pre-checks: confirm `openai-agents` is pinned and installed; read its installed API (do not rely on memory); check install size vs the Vercel limit.
1. `backend/config.py`: `AI_MODE`, `AI_ORDER`, `GEMINI_*`, `OPENAI_*`, `AI_MAX_TURNS`, `AI_MAX_OUTPUT_TOKENS`, `AGENTS_TRACING` (default off); update `.env.example` and the DEVELOPMENT table.
2. `backend/services/ai/`: `providers.py`, `tools.py` (wrap existing guarded read-only tools with `@function_tool`; `web_lookup` over existing grounding),
   `agents_factory.py` (`build_agents(provider)`: triage + the 7 specialists, Chat Completions shape for both providers),
   `guardrails.py`, `runner.py` (order, timeout, failover **between turns only**, our own `{role,text}` history, map result to the existing response shape), `status.py`.
3. Structured output `ChatAnswer`; ids validated against the store; server builds cards/actions/links. Fallback chain: structured, JSON parse, plain text.
4. Hybrid routing: keep `router.py`/`advisor.py` as the free first pass; model hand-offs override only when the rule router is unsure.
5. Migration 0006 `chat_events` (engine, model, latency, outcome/failover reason, intent, specialist, tool used).
6. Tests with a fake model, no network: provider order and `AI_MODE`, failover on 429/5xx/timeout/auth, missing key, tracing off, tools read-only,
   guardrails (owner data, injection), hand-off name mapping, response shape, legacy `/api/chat`, regression test for Gemini rejecting SDK fields (`store`/`metadata`).
   `scripts/live_ai_smoke.py` (never in CI).
7. Defer to session 7: SSE streaming via `run_streamed`, admin analytics UI for engines.

**Exit criteria:** with no keys the offline engine still gives Part 5 behaviour; with fake providers failover is proven; `docs/AI.md` written; Vercel size/duration noted in `docs/DEPLOYMENT.md`.

### Risks and decisions to settle early
- **SDK vs Gemini compatibility** is the biggest unknown; budget time for the first live call (needs your keys, locally).
- **Cookie consent vs remember-me:** remember-me cookie is set on explicit login action; treat it as a user-requested function, but document the category choice in `COOKIES.md`.
- **Vercel size/cold start:** `openai-agents` + `openai` + `google-genai` + scikit stack may approach the limit; keep imports lazy; measure first.
- **Session length:** if 6.2 does not fit, stop after providers + factory + runner + tests and move guardrails/structured output to session 7.

---

## 4. Later sessions (outline)

- **Session 7:** admin extras (TOTP, CSV export, audit-log page, retire `HEALTH_DETAIL_TOKEN`, chat/engine analytics), SSE streaming, widget parity via shared render module, `md()` escape fix, XSS tests.
- **Session 8:** CSP remainder (inline styles, pin/self-host Tesseract + PDF.js + fonts with SRI, remove `style-src 'unsafe-inline'`, move the inline script), UX audit, design system, accessibility pass, image optimisation, Lighthouse before/after, Playwright smoke tests.
- **Session 9:** remaining docs (`SECURITY`, `ADMIN`, `DESIGN_SYSTEM`, `DEPLOYMENT`, `CHANGELOG`, ADRs), GitHub Actions CI, Dependabot, ruff, bandit, `pip-audit`, `npm audit`, ZAP baseline, headers grade, Security Checklist.

---

## 5. Known limitations (carry forward)

- Postgres adapter, Upstash store, Google sign-in and Resend were never run against live services.
- Sign-up reveals whether an email exists (409) until email verification exists (rate limited and logged).
- No "my sessions" page yet (arrives with Part 2B "Signed-in devices").
- Anyone can lock their own IP out of `admin_001` by guessing; many IPs can hit the per-account ceiling (documented in `docs/AUTH.md`).
- `TRUSTED_PROXY_HOPS` assumes exactly one proxy.
- Document verification is indicative only (Phase B: OCR 17/29, PDF 28/28 and zero false positives, locked in `tests/frontend/pipeline.test.js`; rule tests in `tests/frontend/verificationRules.test.js`; synthetic documents only, no real-scan validation); do not regress.
- `/nice-try` and the admin page have no committed browser test beyond the login test's redirect checks.
- No security scan has ever been run.

---

## 6. Kickoff prompt for session 6 (paste into the coding tool with the repo open)

> Read `HANDOFF.md` first, then `docs/ARCHITECTURE.md`, `docs/AUTH.md`, `docs/API.md`, `docs/DEVELOPMENT.md`, and `KPT_upgrade_prompt.md` Parts 2B and 10.
> Run `npm run test:all` and confirm 76 JS + 84 Python pass before changing anything. Then do Phase 6.1 (Part 2B cookies), then Phase 6.2 (Part 10 core),
> exactly as written in section 3 of `HANDOFF.md`. Rules: follow the existing layering; never hard-code secrets; never disable a security control to pass a test;
> verify the installed `openai-agents` API instead of relying on memory; run the tests after each phase and report what ran and what passed or could not run.
> At the end, update `HANDOFF.md` (status table, your actions, next plan) and the docs touched.

<!-- ===== PART D ===== -->

## PART D - previous docs/HANDOFF_NEXT.md (verbatim)

# HANDOFF FOR THE NEXT AI SESSION — read this first, in this order

You are continuing the Karachi Property Trust (KPT) project from an archive. Do NOT start over and do NOT re-audit from scratch: the audit is done (`docs/PROJECT_PHASE_AUDIT.md`). Use this file as the starting state.

## 0. Token-safety rule (do this FIRST)
1. Within your first few tool calls, confirm the archive opens and the baseline commands below still give the numbers in section 3.
2. Work in small slices. After EVERY slice: run the tests, update `CHANGELOG.md`, and refresh the zip.
3. When you estimate ~70% of your context/tokens are used: STOP new work, run the tests, update this file's section 4 ("State when you stopped"), build the zip, and give the owner a summary. Never end a session without delivering the zip + summary.
4. Never claim a test passed unless you ran it. Never print, copy or guess secrets (`.env` is not in the archive; do not create one with real values).

## 1. Project in one paragraph
Flask 3.1 backend (`backend/`, Python 3.12, SQLite locally / PostgreSQL in production on Vercel) + static ES-module frontend (`frontend/`, `public/`, no build step). Features: signup/login/Google sign-in, admin dashboard + optional TOTP, listings, messaging, chatbot (offline + Gemini + Agents SDK), cookie consent, and "Verify Your Document" (OCR/PDF text -> `frontend/js/domain/extraction.js` -> `documentVerification.js` -> `views.js`; runs in the browser, advisory only).

## 2. Owner decisions already made (do not re-ask)
- The login page's **"Skip login (dev only)" button and `admin__01`** are a deliberate feature: any attempt goes to `/nice-try`, except username `admin__01` + the password in `DEV_ADMIN_PASSWORD`, which opens `/admin`. It is restored (`backend/services/dev_skip.py`, `/auth/dev-skip`, login button, `tests/backend/test_dev_skip.py`). Keep its limits: 404 in production, local SQLite only, empty password never matches. NEVER remove it as a "bypass", never weaken it, never set `DEV_ADMIN_PASSWORD` on Vercel.
- The 8 sample records in `frontend/js/data/properties.js` are fictional demo data.
- Work in phases, test after each phase, report honestly what was not verified.

## 3. Verified state (commands and real results at hand-off)
| Command | Result |
|---|---|
| `npm test` | 199 tests, 199 pass |
| `python -m unittest discover -s tests/backend -t .` | 262 run, 261 pass, 1 error = `test_admin_totp` (`pyotp` not installable offline; environment, not code) |
| `node scripts/manifest-report.mjs` | OCR 18/29 (anchored lane), PDF 28/28 (all fixtures SYNTHETIC; the app's free-search lane is 17/29, locked by `tests/frontend/pipeline.test.js`) |
| `python tests/browser/login_test.py`, `csp_test.py`, `smoke.py` | pass (Chromium via Playwright 1.56.0). 15 of 16 browser tests passed in the earlier audit; `admin_totp_test.py` blocked by `pyotp` |
Not run anywhere: PostgreSQL tests, live Google/Resend/Gemini/OpenAI, `pip-audit`, `bandit`, `ruff`, Lighthouse, TOTP tests.
Running the manifest report rewrites `tests/.results/manifest_results.json` (generated file); running backend tests creates `.local/` and `__pycache__/` — delete these before zipping.

## 4. State when you stopped (UPDATE THIS before ending every session)
- Last completed: dev-skip restored and tested; Phase B.1 changes present but **awaiting owner authorization** (see `CHANGELOG.md`).
- In progress: nothing.
- Next unfinished item: first item of section 5.

## 5. Remaining work, in priority order (checkpoint rule: report to the owner before large changes)
1. **Owner decision pending:** authorize or reject Phase B.1 (changes listed in `CHANGELOG.md`; files: `extraction.js`, `documentVerification.js`, `resultPrivacy.js`, `views.js`, `store.js`, `tests/frontend/phaseB1.test.js`). If rejected, revert those files from the original `kpt-phaseB-verification-fix.zip`.
2. **S4 (security/architecture):** move document verification to the server (`POST /api/v1/verify-document` taking only extracted fields, returning status + generic reasons, rate-limited) and remove `owner`/`cnic` from `properties.js`. Needs the owner's design approval first.
3. Verification decisions: V3 (Power of Attorney with an unconfirmed attorney can still end `verified`; recommended: `unable_to_verify`), V4 (`suspicious` is a fourth status: document it or merge), V5 (area units not converted), V7 (free-search may match the wrong record).
4. On a networked machine: install `pyotp==2.10.0`, `google-auth`, `psycopg`, `openai`, `openai-agents`; run TOTP tests, the 4 PostgreSQL modules, `pip-audit`, `bandit`, `ruff`; then replace the 9 "PIN ME" ranges in `pyproject.toml` with the versions that passed.
5. Live checks the owner must do (credentials needed): real Google OAuth sign-in, Resend email, Gemini/OpenAI. Rotate any key ever exposed in an earlier archive.
6. Supply chain: vendor Tesseract.js (currently floating `@5`) and PDF.js with SRI (`scripts/vendor_assets.py`), then tighten the CSP.
7. Housekeeping: compress `public/assets/Property Images` (~96 MB) and `samples` (~77 MB); move old session logs (`HANDOFF.md`, `AI_WORKLOG.md`, `REPAIR_REPORT.md`, merge reports) to `docs/history/`.

## 6. Hard rules
- Inspect before editing; small reviewable changes; add tests for every change; do not rewrite working features.
- Do not weaken CSP, CSRF, rate limits, or privacy (no owner/CNIC in public responses, logs, cookies or AI prompts).
- Do not enable mandatory TOTP (`ADMIN_TOTP_REQUIRED`) until enrolment and recovery have been tested.
- Do not deploy, push to GitHub, or touch a live database without explicit authorization.
- Packaging: exclude `.local/`, `__pycache__/`, `node_modules/`, `.env*`, virtualenvs; keep one `kpt/` root; verify with `unzip -t` and a file listing; never overwrite the owner's original ZIPs.

## 7. Where things are
`docs/PROJECT_PHASE_AUDIT.md` (audit + fixes), `docs/AUTH.md` (auth + dev-skip), `docs/KNOWN_ISSUES.md`, `docs/DEVELOPMENT.md` (how to run tests), `CHANGELOG.md` (newest first), `HANDOFF.md` (old session history, long).

<!-- ===== PART E ===== -->

## PART E - CURRENT STATE section of `kpt-session26-T4.zip` (the other AI's T1-T4 checkpoint), HANDOFF.md lines 1-32, verbatim

## CURRENT STATE (Session 26 checkpoint + T1-T4) - read this first

**Tree = Phase B.1 + Session 26 scanner fixes + T1 + T2 + T3 + T4.** Next task: **T5 (cookie consent after login)**. T6 (Google OAuth) after that. Plan and T4 details: `work.md` section 9b.

**T4 (done, verified):** login-first routing and the Guest experience.
* Server: `web.py` `private_page()`: anonymous `/`, `/index.html`, `/listings`, `/listings.html` -> 302 `/login` (`?next=/listings`); user/guest/admin served with `Cache-Control: private, no-cache`.
* UI: Continue as Guest button (`auth-page.js`), guests see the login forms, Guest badge in the header, guest-restricted listings page / seller chat / owner check / privacy page. New helper `frontend/js/services/sessionUser.js`.
* Files: see `work.md` 9b. New tests: `tests/backend/test_login_first.py` (16), `tests/frontend/guestEntry.test.js` (7), `tests/browser/guest_entry_test.py` (28 checks, in CI), `tests/browser/support/session_entry.py`.
* **Results (this run, Linux sandbox):** `npm test` 206/206. `python -m unittest discover` 318 run, 317 ok, 1 error = `tests.backend.test_admin_totp` (`pyotp` missing, baseline). Browser: 17/17 pass (smoke, login, developer_login, csp, cookies, a11y_basics, camera_upload, creators, featured, listing_lifecycle, listings, login_busy, messaging, prefs, property_images, signup_single_click, guest_entry). **Not run:** `admin_totp_test` (needs `pyotp`), PostgreSQL, live Google, live Vercel routing.
* Regression found and fixed during T4: guest header overflowed at 375 px (see `work.md` 9b). Existing browser tests now enter via the Guest button; browser test servers use `GUEST_MAX_ACTIVE_PER_IP=1000` (product default 10 unchanged).
* Open points for the owner: confirm guest scope (in-browser document analysis stays available), guest-then-login leaves the old guest row until idle expiry, production routing of `/` on Vercel is unverified.
* **Exact next action:** T5. `consent.js`/`consent-banner.js`/`main.js` currently show the banner at page load on every page including `/login`, `/developer-login`, `/nice-try`. Skip it there; show it on the first page after login, Google login or guest entry when no choice is recorded; then update `cookies_test.py` (its step 1 currently asserts the banner on the first-visit page, which is now `/login`).

## Previous state (T1-T3)

**Tree = Phase B.1 + Session 26 scanner fixes + T1 + T2 + T3.** Do not apply `kpt-T3-patch.zip`: T3 was re-implemented natively on this tree (it would overwrite `admin.py`/`app.py`).

**T1/T2 (done earlier):** `POST /auth/developer-login`, `/developer-login` page + Developer link, `import os` fix in `backend/app.py`.

**T3 (done this run, verified):** restricted guest sessions, backend only (no UI yet).
* New: `backend/services/guest_service.py` (`GuestService.create/cleanup/discard`), `tests/backend/test_guest.py` (16 tests incl. route-authorization matrix).
* Changed: `backend/security/guards.py` (`login_required(..., allow_guest=False)`: guest -> `403 guest_not_allowed`), `backend/api/auth.py` (`POST /auth/guest`, logout discards guest row, `/auth/features` has `guest: true`), `backend/services/session_service.py` (guest lifetimes; admin session view hides guests), `backend/config.py` (`guest_session_idle_s` 900, `guest_session_absolute_s` 7200, `guest_max_active_per_ip` 10, `guest_cleanup_batch` 200; env `GUEST_SESSION_IDLE_S`, `GUEST_SESSION_ABSOLUTE_S`, `GUEST_MAX_ACTIVE_PER_IP`), `backend/app.py` (`guests()` accessor), `backend/api/admin.py` (user list/CSV exclude guests; `_target` 404 for guests), `backend/api/messages.py` (`by-ref` treats guest as anonymous), `backend/api/chat.py` (no first-name greeting), `backend/web.py` (`/messages` redirects guests to `/login`), `docs/AUTH.md`, `CHANGELOG.md`, `work.md`.
* No DB migration needed (`users.role` is plain TEXT, `email`/`username` nullable).
* Tests run: `test_guest` 16/16. Backend full: 302 run, 1 error = `test_admin_totp` (`pyotp` missing). `npm test` 199/199. Browser: login, csp, cookies, developer_login, smoke, messaging, listings, listing_lifecycle, prefs all OK.
* The matrix asserts: every route that answers anonymous requests with 401 answers a guest with 403 `guest_not_allowed`; every admin route answers guest/user 403 and admin not 401/403 (GET); no route 5xx for guests.
* NOT verified: PostgreSQL (the cleanup `NOT EXISTS` / `IN (...)` SQL uses only `?` placeholders but ran on SQLite only), UI, remaining browser tests (CP1), `admin_totp_test`, ruff/bandit/pip-audit (the new f-string SQL carries `noqa S608`/`nosec B608`, only `?` markers interpolated).
* Assumption still awaiting owner confirmation: guests may browse listings and use the chatbot; nothing else.

**Not done:** T4-T7, Session 26 leftovers (Priority 6 revalidation, ruff F401 in `chat.py`/`messages.py`, pin `cryptography`).

**EXACT NEXT ACTION: T4** - "Continue as guest" button on `login.html`/`auth-page.js` calling `/auth/guest` (CSRF via `fetchJson`; handle 429 `guest_limit`); login-first gating: anonymous `GET /` (and `/listings`) -> 302 `/login`, user/guest/admin -> 200 (edit `backend/web.py`, keep `/privacy`, `/nice-try`, `/login`, `/developer-login`, static assets public); restricted guest UI (hide messaging/listing/verification entry points for `role == 'guest'` using `/auth/me`; header shows "Guest"); update existing browser tests that open `/` unauthenticated (smoke, listings, a11y, csp, etc.) to enter as guest first; tests: Flask redirect tests + new browser test. Then T5 (cookie consent after login).


<!-- ===== PART F ===== -->

## PART F - HANDOFF_NEXT.md of the compact T4 snapshot (`kpt-session26-T4-wip.zip`), verbatim

# HANDOFF_NEXT - how to resume (short; full previous version is in `docs/HANDOFF_ARCHIVE.md`, Part D)

## Reading rule (do this first)
1. Read `HANDOFF.md` (about 55 lines) and the T4 rows/subtask table of `work.md` (`grep -n "T4" work.md`, then `sed -n`). Nothing else is needed to start.
2. Do NOT read `docs/HANDOFF_ARCHIVE.md` unless you need a specific old detail. Never print whole handoff, archive, work, log or source files; use `grep -n` and `sed -n 'a,bp'`.
3. Verify the actual tree before trusting any status (the T4 edits in the tree are unverified).
4. One subtask per run. After each: run its focused tests, update `work.md` status, `HANDOFF.md`, `CHANGELOG.md`; stop. Deliver zip + summary before running out of context (at about 70% stop new work).

## Project in one line
Karachi Property Trust: Flask 3.1 backend + static ES-module frontend (no build step), SQLite local / PostgreSQL on Vercel; listings, messaging, chatbot, admin dashboard, document verification, cookie consent.

## Owner decisions (do not re-ask)
* `admin__01` + `DEV_ADMIN_PASSWORD` shortcut (`/auth/dev-skip`) is a deliberate feature: 404 in production, local SQLite only, empty password never matches. Never remove or weaken it; never set `DEV_ADMIN_PASSWORD` on Vercel.
* The 8 sample records in `frontend/js/data/properties.js` are fictional demo data.
* Work in phases, test after each, report honestly what was not verified.
* Target behaviour: login page first for visitors without a session; Developer Login on a separate page (valid admin -> `/admin`, else `/nice-try`); Continue as Guest = restricted session; Google login; cookie consent after login; backend-enforced permissions.

## Hard rules
* Inspect before editing; small reviewable changes; tests for every change; do not rewrite working features.
* Do not weaken CSP, CSRF, rate limits or privacy (no owner/CNIC in public responses, logs, cookies or AI prompts).
* Do not enable `ADMIN_TOTP_REQUIRED` before enrolment/recovery are tested. Do not deploy, push or touch a live database without authorization.
* Packaging: exclude `.env*`, `.local/`, `__pycache__/`, `node_modules/`, virtualenvs; one `kpt/` root; verify with `unzip -t` and a listing; never overwrite the owner's original ZIPs.
* Never claim a test passed unless you ran it.

## Where things are
`work.md` (goal, plan, T4a-T4d), `HANDOFF.md` (current state), `docs/AUTH.md` (auth, guest, developer login, dev-skip), `docs/KNOWN_ISSUES.md`, `docs/DEVELOPMENT.md` (running tests), `CHANGELOG.md`, `docs/HANDOFF_ARCHIVE.md` (history).
