# KPT Session 21b — Repair Report

Environment for every result below: **Linux sandbox**, Python 3.12.3, Node 22.22.2, Playwright 1.56.0. **Nothing was run on Windows.** No `.git` metadata exists in the RAR, so `git status` / `git diff` were not possible.

## Sources
* `kpt_full_Check_needed.rar` (RAR5; `.venv312`, caches skipped on extraction; 333 project files; no `.git`).
* Nested `kpt-windows-path-fix-patch.zip` and `kpt-session21-patch.zip` (both inspected, unpacked to scratch, no script executed). The `kpt-session19d-patch.zip` named in the Session 21 handoff is not in the RAR; the two ZIPs present are the only patch sets. The zero-byte `git` file is not inside the Session 21 ZIP as supplied, and nothing named `git` is in the output.
* Archive `HANDOFF.md` (84,320 B) is older than the nested one (101,312 B, identical to the uploaded `HANDOFF.md`).

## Discrepancies
1. **Missing from the archive and from both patches:** `tests/backend/test_network_config.py`. The handoff says Session 20 added it, with `KPT_HOST`, Upstash URL validation and narrow `nosec` comments. The archive code has none of these (`backend/app.py` line 202 still uses `host="0.0.0.0"`; `ratelimit_store.py` has no scheme check). Not reconstructed (would be fabrication). The Windows folder may already have them; archive is older than that checkout.
2. Archive lacked `scripts/check_installed_versions.py`, `tests/browser/camera_upload_test.py`, `tests/frontend/portablePaths.test.js`, `.gitattributes` (all supplied by patches).
3. Both patches contain `HANDOFF.md` and the checker; the Session 21 versions are newer and were used.
4. `.editorconfig` is mentioned in the handoff but exists nowhere supplied.

## Changes made
* From Windows patch: `.github/workflows/ci.yml` (adds `camera_upload_test`), `tests/browser/camera_upload_test.py`, `tests/frontend/portablePaths.test.js`, `tests/frontend/strictStyles.test.js` (`fileURLToPath`).
* From Session 21 patch: `.gitattributes`, `CHANGELOG.md`, `docs/DEVELOPMENT.md`, `HANDOFF.md` (reconciliation note added at top), `scripts/check_installed_versions.py`, `tests/backend/test_check_installed_versions.py`, `test_gitattributes.py`, `test_text_encoding.py`.
* `subprocess_encoding.diff` applied by hand: `tests/backend/test_records.py`, `tests/backend/test_totp_missing_library.py` (`encoding="utf-8", errors="replace"`).
* New in this session: `encoding="utf-8"` added to 12 bare text-file calls that the Session 21 guard flagged in this older tree: `tests/browser/admin_totp_test.py:69`, `test_dependencies.py:44,88`, `test_vendor_assets.py:67,71`, `test_cookies.py:41`, `test_moderation_messaging.py:337`, `test_api.py:237`, `test_ci_config.py:32,37,50`, `scripts/install_deps.py:21`.
* Not touched: `pyproject.toml`, `package.json`, dependency versions, security code.

## Tests actually run (Linux sandbox)
| Check | Result |
|---|---|
| `node --test strictStyles + portablePaths` | PASS 15/15 |
| `npm test` (JS) | PASS 122/122 |
| `unittest discover tests/backend` | 203 run, **1 error**: `test_admin_totp` import (`pyotp` not installed here). All other 202 pass, including text-encoding guard, checker (8), gitattributes (4), ci_config. Not an all-pass run. |
| Browser: smoke, csp_test, a11y_basics_test, login_test, cookies_test, messaging_test | PASS |
| Browser: camera_upload_test | PASS for validation/graceful-failure only; OCR engine could not load (offline). **OCR/PDF extraction NOT proven.** |
| `check_installed_versions.py --dev` | Runs; reports 10 problems about the *sandbox* env (missing pyotp, psycopg, openai, etc.; scikit-learn 1.8.0 vs ==1.9.1). Says nothing about your `.venv312`. |

## Not run / blocked
Windows tests; `admin_totp_test` and `test_admin_totp` (need real `pyotp`); PostgreSQL modules; listings/lifecycle/prefs browser tests; vendor downloads, real OCR/PDF; ruff, bandit, pip-audit, Lighthouse, ZAP; GitHub Actions run; live Google, Resend, Upstash, Neon, Vercel, AI. `git add --renormalize` not advised until you review `git status` first.

## Security checks
Credential-pattern scan of the final tree: no hits (patterns only, values never printed). No `.env`, databases, caches or venv in the archive. Still rotate Gemini/OpenAI keys exposed in earlier archives; keep `ADMIN_TOTP_REQUIRED=0`, `MESSAGE_RETENTION_DAYS=0`.

## First Windows step
Extract the ZIP into a **new** folder, then in your original folder check for `tests\backend\test_network_config.py` (see discrepancy 1).

## Addendum: Session 22 UI polish (Linux sandbox)
Changed: `frontend/index.html`, `frontend/js/features/home.js`, `frontend/css/layout.css`, `login.css`, `utilities.css`, `CHANGELOG.md`.
Checks run: `npm test` 122/122; Python 203 run, only `test_admin_totp` errors (no `pyotp` here); browser smoke, csp_test, a11y_basics, login, cookies, messaging, camera_upload, listings, prefs all pass. Admin check: `admin_001` with a local `ADMIN_001_PASSWORD` reaches `/admin`; a wrong password goes to `/nice-try`.
Not verified: Windows run; Lighthouse; real property photos (folder `public/assets/Property Images/` is absent from the supplied RAR).
