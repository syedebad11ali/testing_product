# Session 22: reference-archive comparison and merge report

Master project: `kpt-fixed-session22-ui.zip`. Donor: `karachi-property-trust__see_from_here_1.rar` (RAR5, 16,466 entries, 13,466 files, 422 MB unpacked) plus `Login_Page.zip` (the login design). Nothing in Session 22 was deleted or replaced; every change is an addition or a minimal in-place edit.

## How the reference was inspected
No RAR tool exists in the build sandbox, so the archive was read with a purpose-written pure-Python RAR5 reader/decompressor (headers, LZ decoder, delta/E8/ARM filters). Every extracted file was verified against the CRC32 stored in the archive (296 files extracted, 0 failures). The remaining files were classified by path, size and CRC32 without extraction.

## What the reference contains
| Reference area | Files | Verdict |
|---|---|---|
| `Chatbot/Login Page/node_modules` | 12,995 | Not imported (third-party packages of an older Node login project) |
| `Chatbot/Login Page/{src,server,...}` | ~20 | Not imported: React + Express + JWT + JSON user file, superseded by Session 22's Flask auth (scrypt, sessions, CSRF, TOTP, Google with server-side verification). Its design is already ported (see Login). `server/users.json` and the `.env` files were never read or extracted |
| `Chatbot/*.py/js/css` (old monolith bot) | ~12 | Compared by function: 49 of its 60 functions exist by name in Session 22's backend (345 defs). Two behaviours were genuinely missing and were added (see Chatbot). `OpenAIEngine` is NOT imported: it needs the `openai` package and rotated keys (gated) |
| `public/assets/Property Images` | 51 | **Added** (16 referenced by `properties.js`, previously 404) |
| `public/assets/samples` | 57 | **Added** (`SAMPLES_URL` in `config.js`; the document-verification sample picker fetches them) |
| `testpack/documents_*` | 57 | Not added: byte-identical duplicates of `samples` (Session 22 dropped them on purpose) |
| `public/assets/Dataset/*.csv` | 11 | Not imported: older data **with owner names** (Session 22 sanitises them); not even extracted |
| `tests/fixtures`, `README.md`, `pyproject.toml`, `vercel.json`, `.gitignore`, `.vercelignore`, root `index.html`/`orv.html`, `css/`, `js/` | ~70 | Same path, older/different content: Session 22 kept (newer, restructured) |
| `.git` (162 files), `Chatbot/.env`, `Chatbot/Login Page/.env` | | Not imported. **The `.env` files exist in the reference archive and may hold live keys: rotate them** |

## Login page
The uploaded design (React/Vite) and Session 22's `frontend/login.html` + `css/login.css` were compared rule by rule: 101 selectors in the upload, 120 in Session 22. Session 22 already has the design (nav, hero, pill inputs, eye toggle, hexagon photo with ribbons, feature badges, mobile reordering) wired to the real backend (password, signup, remember-me, forgot/reset, Google, forced password change). Remaining differences were reviewed: colours via tokens (intentional), responsive `<img>` instead of a CSS background (intentional), the later `.features` grid override (kept), dead `.nav nav` rules (not used by the markup), and the dev-only "Skip login" button (deliberately NOT imported: it would bypass authentication). **Added:** the design's busy state: while a request is in flight the Google button/box is disabled (`auth-page.js`, `login.css`).

## Chatbot
Probing Session 22's offline bot found "help / what can you do" answered with the off-topic reply and "how many houses...", "summary of the dataset", "what areas do you cover" not answered. Added two deterministic intents from the reference bot's `_help` / `_stats_answer` / `_summary_answer` behaviour: `help` and `dataset_overview` (counts, areas, price statistics straight from the store; no model call; same response shape). Existing intents are unchanged (router tests pin `average price of houses in DHA`, `which area is cheapest`, `help me log in`, etc.).

## Files
Added: `public/assets/Property Images/*` (51), `public/assets/samples/*` (57), `tests/frontend/assetsPresent.test.js`, `tests/browser/property_images_test.py`, `tests/browser/login_busy_test.py`, `docs/MERGE_REPORT_SESSION22.md`.
Modified: `backend/services/router.py`, `backend/services/chat_service.py`, `frontend/js/auth-page.js`, `frontend/css/login.css`, `tests/backend/test_chat.py`, `.github/workflows/ci.yml`, `CHANGELOG.md`, `HANDOFF.md`, `docs/KNOWN_ISSUES.md`, `docs/DEPLOYMENT.md`.

## Tests (sandbox: Python 3.12.3, no real `pyotp`, no network)
`npm run test:all`: 125 JS pass / 0 fail (122 before + 3 new); Python 207 run, 1 error = `tests.backend.test_admin_totp` cannot import without the real `pyotp` (passes only where it is installed; not claimed here). Browser, all OK: smoke, login, login_busy, csp, a11y_basics, camera_upload, cookies, messaging, listings, listing_lifecycle, prefs, property_images. `admin_totp_test` not run (needs `pyotp`). Not run: PostgreSQL, live Google/Resend, Lighthouse, pip-audit/bandit/ruff.

## Not done / still open
Everything in the earlier handoff stays open (real `pyotp`/PostgreSQL runs, vendoring Tesseract.js/PDF.js, pins and scans, first CI run, TOTP enforcement, retention approval, Agents SDK). New: optimise the 175 MB of images; rotate any keys in the reference `.env` files.
