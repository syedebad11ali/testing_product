# HANDOFF_NEXT - how to resume (short; previous versions are in `docs/HANDOFF_ARCHIVE.md`, Parts D and F)

## Reading rule (do this first)
1. Read `HANDOFF.md` (about 40 lines), then `grep -n "^## 10" work.md` and the T5 row of section 5. Nothing else is needed to start.
2. Do NOT read `docs/HANDOFF_ARCHIVE.md` unless you need a specific old detail. Never print whole handoff, archive, work, log or source files; use `grep -n` and `sed -n 'a,bp'`.
3. Verify the actual tree before trusting any status. One small task per run; run its focused tests; update `work.md`, `HANDOFF.md`, `CHANGELOG.md`; stop. Deliver the zip + summary before running out of context.

## Project in one line
Karachi Property Trust: Flask 3.1 backend + static ES-module frontend (no build step), SQLite local / PostgreSQL on Vercel; listings, messaging, chatbot, admin dashboard, document verification (in-browser), cookie consent, login-first with Developer Login and restricted Guest sessions.

## Owner decisions (do not re-ask)
* `admin__01` + `DEV_ADMIN_PASSWORD` shortcut (`/auth/dev-skip`) is deliberate: 404 in production, local SQLite only, empty password never matches. Never remove or weaken it; never set it on Vercel.
* The 8 sample records in `frontend/js/data/properties.js` are fictional demo data.
* Work in phases, test after each, report honestly what was not verified.
* Target behaviour: login page first for visitors without a session; Developer Login on a separate page (valid admin -> `/admin`, else `/nice-try`); Continue as Guest = restricted session; Google login; cookie consent after login; backend-enforced permissions.

## Hard rules
* Inspect before editing; small reviewable changes; tests for every change; do not rewrite working features.
* Do not weaken CSP, CSRF, rate limits or privacy (no owner/CNIC in public responses, logs, cookies or AI prompts; stored verification results keep CNIC masked).
* Do not enable `ADMIN_TOTP_REQUIRED` before enrolment/recovery are tested. Do not deploy, push or touch a live database without authorization.
* Test commands: `python -W ignore -m unittest discover -s tests/backend -t .`; `npm test`; `python tests/browser/<name>_test.py` one at a time with `timeout 90` (browser tests use their own server/DB; a tool call times out at 300 s, so batch them; background jobs do not survive between calls).
* Packaging: one `kpt/` root; exclude `.env`, `.local/`, `__pycache__/`, `node_modules/`, virtualenvs, SQLite files; KEEP `.env.example` (do not use an exclude pattern like `.env.*`); verify with `unzip -t` and a listing; never overwrite the owner's original ZIPs.

## Where things are
`work.md` (goal, plan, section 10 = consolidation record), `HANDOFF.md` (state), `docs/AUTH.md` (auth, guest, developer login, dev-skip), `docs/KNOWN_ISSUES.md`, `docs/DEVELOPMENT.md`, `CHANGELOG.md`, `docs/HANDOFF_ARCHIVE.md` (history).

## Update (post-consolidation verification)
Guest->account transition now implemented and tested (`tests/backend/test_guest_transition.py`); archive `karachi-property-trust-consolidated-v2.zip` contains it. **Before T5: owner decides the canonical tree** - this consolidated tree lacks the T5a/T5b/T6a/CP1 changes made in the earlier working tree (they would have to be ported, not re-invented). Then T5 (consent after login), T6 (Google readiness), CP1 regression, final ZIP. Do not start T5/T6 until that decision.

## Update (T5/T6a ported into v2)
v2 is the canonical tree. T5a/T5b and T6a are ported and tested (npm 221/221; backend 329 run, only the `pyotp` import error; 18/18 runnable browser tests). **Next: build/verify the final ZIP**, then the owner's live Google check (T6b, blocked on their OAuth setup). Optional: extend `camera_upload_test` through the document-type chooser.

## Update (Google button responsive fix)
The Google sign-in button now follows its container width (`googleButtonWidth` + `ResizeObserver` in `frontend/js/auth-page.js`, `.gbox` containment in `login.css`); new `tests/browser/google_button_responsive_test.py` (CI-registered) and `tests/frontend/googleButtonWidth.test.js`. `npm test` 224/224; focused browser tests OK; the full backend suite was not re-run (no backend change; last recorded 329 run, only the `pyotp` import error). Latest package: `karachi-property-trust-google-button-update.zip` (root `kpt/`). Open: **T6b** = owner live Google check (real client id, authorised origin, real phone); TOTP, PostgreSQL and real OCR/PDF remain unverified. See `work.md` section 14.
