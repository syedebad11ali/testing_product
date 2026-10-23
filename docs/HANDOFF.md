# Hand-off: KPT upgrade (status after session 1)

Source of requirements: `KPT_upgrade_prompt.md`. Order follows its "Working rules".
Verified in this session: `npm run test:all` → **66 JS + 33 Python tests pass** (baseline was 65 + 22; document-verification baselines OCR 16/29, PDF 26/28 untouched).
Also loaded `/` and `/nice-try` in headless Chromium: no CSP violations reported (fonts/CDN scripts could not load in the sandbox because it has no network, so Tesseract/PDF.js flows were **not** exercised).

## Done

| Phase | Item | Where |
|---|---|---|
| 1 | Public CSVs sanitised (owner id/name/property owner/previous owner removed); `sync_datasets.py` generates them, `--check` compares against sanitised source | `scripts/sync_datasets.py`, `public/assets/Dataset/` |
| 1 | Server-side owner check returning only `match / mismatch / unable_to_verify`; previous owner never loaded; name never logged; own rate limit; audit log line | `backend/records/ownership.py`, `services/verification_service.py`, `api/verification.py` |
| 1 | Owner Verification screen no longer shows owner data; new "Check an owner name" form | `frontend/js/features/ownerVerification.js`, `services/verificationApi.js` |
| 1 | Tests: public CSV headers, parsed records, no owner names in any public/frontend file or chat reply, verdicts, validation, rate limit | `tests/frontend/ownerVerification.test.js`, `tests/backend/test_api.py` |
| 3 | Security headers via one `after_request` (CSP with auto-computed hash for the inline theme script, HSTS, nosniff, frame DENY, Referrer, Permissions-Policy camera=self, COOP/CORP), `no-store` on `/api/*` | `backend/security/headers.py` |
| 3 | `vercel.json` `headers` block for CDN-served `/assets/*` | `vercel.json` |
| 3 | Pluggable rate limiter (memory / Upstash Redis REST, stdlib only), `Retry-After`, trusted proxy hops (`ProxyFix`) | `backend/security/ratelimit_store.py`, `middleware.py`, `app.py` |
| 3 | Request ID on every response and error body; public health = `{"status":"ok"}`, detail behind `HEALTH_DETAIL_TOKEN` | `errors.py`, `api/health.py` |
| 4 | `/nice-try` page: exact text, bold/huge, right-aligned, animated gradient, 3D extrusion + noise, pointer tilt, reduced-motion safe, dog image (JPG + WebP), "Back to login" | `frontend/nice-try.html`, `css/nice-try.css`, `js/nice-try.js`, `public/assets/images/dog-nose.*` |
| docs | `.env.example`, `DEVELOPMENT.md` config table, `API.md`, `KNOWN_ISSUES.md`, `MIGRATION.md` updated | `docs/` |

## Your actions now
1. Create an **Upstash Redis** database (free tier) and set `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` in Vercel. Without it, rate limits are per instance.
2. Optional: set `HEALTH_DETAIL_TOKEN` (long random string) to read `/api/v1/health/detail`.
3. After deploy, redeploy so the sanitised CSVs replace the old public ones. **The old CSVs with owner names remain in your git history**: if the data ever becomes real, rewrite history (`git filter-repo`) and treat names as leaked. I could not scan git history (no `.git` in the zip).
4. Run `python scripts/sync_datasets.py` whenever you edit `backend/datasets/*.csv`.

## Not done (in priority order)

### A. Phase 2: CSP prerequisites (blocks a truly strict CSP)
- [ ] Replace ~91 inline `onclick/oninput/onsubmit` with `data-action` + one delegated listener (`ui/actions.js` becomes the dispatcher; rewrite `handlers.test.js` to scan for `data-action` names). Arguments with `${}` need `data-*` attributes.
- [ ] Move inline styles to classes; then delete `'unsafe-inline'` from `script-src-attr` and `style-src` in `backend/security/headers.py` (marked TEMPORARY).
- [ ] Pin Tesseract (`@5` → exact version) + SRI, or self-host Tesseract/PDF.js/fonts; lazy-load them only when the verify flow opens; tighten `connect-src`.

### B. Phase 3: database + sessions (needs your decision confirmed)
Recommended: **Neon or Supabase Postgres** (`psycopg[binary]`, pinned) for users/sessions/events/audit/chat feedback, Upstash (already wired) for rate limits. SQLite only for tests/local.
- [ ] `backend/db/` (connection, versioned SQL migrations, `seed.py`), tables: users, sessions, remember_tokens, login_events, audit_log, password_resets, chat_sessions, feedback, saved_items.
- [ ] Password hashing: `argon2-cffi` (pinned) or stdlib `hashlib.scrypt` if you want zero new deps; min 10 chars, common-password list.
- [ ] Server sessions (256-bit id, only the hash stored, `__Host-` cookie, idle 30 min / absolute 12 h, rotate on login), CSRF double-submit + Origin check, token handling added to `services/http.js`.
- [ ] Make the rate limiter fail-closed for login routes (`UpstashStore(fail_closed=True)`), key by IP **and** account, add lockout.

### C. Phase 4: auth, cookies, `admin_001`
- [ ] `login.html`, `signup.html`, `features/auth.js`, `css/auth.css`; Google OIDC (code + PKCE + state + nonce, server-side ID-token verification); forgot-password endpoints (provider env var + TODO).
- [ ] `admin_001` seeded from `ADMIN_001_PASSWORD` (hash only; production refuses weak/equal-to-username password and forces change). **Wrong password → server returns `{"redirect":"/nice-try"}` with identical timing/body every time, logs `login_events`, counts toward lockout, creates no session.** (`/nice-try` already exists.)
- [ ] Add `login_required` to `POST /api/v1/verification/check`.
- [ ] Part 2B cookies: `kpt_consent`, `kpt_prefs`, `__Host-kpt_remember` (selector+validator, rotate, reuse ⇒ revoke all), `__Host-kpt_chat`; `core/cookies.js`; consent banner; Privacy & cookies page; `docs/COOKIES.md`.

### D. Phase 5: admin
- [ ] `admin.html` + `/api/v1/admin/*` (users table, login feed, sessions revoke, disable/enable, role change, CSV export, chat analytics), TOTP, audit log, `Cache-Control: no-store` (already applied to `/admin*`). Replace `HEALTH_DETAIL_TOKEN` with the admin role.

### E. Phase 6–7 (chatbot, UI/UX)
- [ ] Prompt/answer rework with ranges and labelled sources, offline-engine parity, structured response `{reply, source, from_data, chips[], cards[], actions[]}`, session memory, feedback buttons, shared render module for `features/chat.js` and `widget/chatbot.js` (also fix `md()` → escape first).
- [ ] `services/router.py` intents + hand-off, plot cards built server-side from IDs, `/#/plot/<id>` deep link.
- [ ] `docs/UX_AUDIT.md` first, then `tokens.css`, components, a11y (WCAG 2.2 AA), image optimisation (WebP/AVIF), Lighthouse before/after, Playwright smoke tests (Playwright 1.56 is available in the sandbox).

### F. Phase 8–9
- [ ] SEO (`sitemap.xml`, `robots.txt` disallowing `/admin`, OG tags, 404 page), demo disclaimer, privacy/terms pages, data-deletion endpoint.
- [ ] Docs: `SECURITY.md` (checklist table), `AUTH.md`, `COOKIES.md`, `ADMIN.md`, `CHATBOT.md`, `DESIGN_SYSTEM.md`, `DEPLOYMENT.md`, `CHANGELOG.md`, `docs/adr/`.
- [ ] CI (GitHub Actions: `npm run test:all`, ruff, `node --check`, `pip-audit`, `npm audit`), Dependabot, `bandit`, ZAP baseline, headers grade check. **None of these scans were run yet.**

## Known limitations of what exists
- Verification endpoint has no login yet (rate limit + audit log only).
- Upstash store untested against a live Upstash instance (only the fail-open path is tested).
- `X-Forwarded-For` trust assumes exactly one proxy (Vercel); change `TRUSTED_PROXY_HOPS` otherwise.
- `property images`/`samples` were not in the code-only zip, so image optimisation was not touched.
