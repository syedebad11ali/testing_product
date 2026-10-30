# Authentication, sessions, CSRF and the admin_001 flow

## Overview
| Concern | Implementation | File |
|---|---|---|
| Password hashing | stdlib `hashlib.scrypt` (N=2^14, r=8, p=1), params stored in the hash, rehash-on-login | `backend/security/passwords.py` |
| Password policy | 10-128 chars, common-password list, not the email/username | same |
| Sessions | random 256-bit id in a `HttpOnly; Secure; SameSite=Lax; Path=/` cookie (`__Host-kpt_session` when Secure); only SHA-256 stored; idle 30 min / absolute 12 h (admin 15 min / 2 h); new id on every login | `services/session_service.py` |
| CSRF | Origin check + double-submit token (`X-CSRF-Token` = `__Host-kpt_csrf` cookie) on every non-GET under `/api/v1/auth`, `/admin`, `/verification`; `services/http.js` adds it automatically | `security/csrf.py`, `frontend/js/services/http.js` |
| Lockout | 5 failures per (account, IP) in 15 min, or 20 per account; locked logins still do the same hash work | `services/auth_service.py` |
| Rate limit | per-IP on signup/login (`LOGIN_RATE_LIMIT_PER_MIN`); Upstash store is fail-closed | `app.py`, `middleware.py` |
| Events | every login/sign-up outcome in `login_events`; admin actions in `audit_log`; IPs stored only as truncated HMAC | `services/audit_service.py` |
| Roles | `user`, `admin`, checked server-side by `role_required` | `security/guards.py` |

## admin_001
* The account is created by `backend/db/seed.py` from `ADMIN_001_PASSWORD` (set in `.env` locally, Vercel env vars in production). The plaintext is never in the repo; a test greps for it.
* Correct password: session + `{"redirect":"/admin"}` (or `/login?change=1` when a password change is forced).
* **Any wrong password** for `admin_001` (also when locked, disabled or not seeded): `200 {"redirect":"/nice-try"}`, identical body, same hashing work, no session, a `login_events` row, counts toward lockout. The browser only follows the redirect.
* Production: the account is **not created** unless the password is 14+ chars, has 3+ character types and does not contain the username; it is created with `must_change_password=1` and every route except change-password/logout/me returns 403 until changed.
* Trade-off: because the username is public, anyone can trigger the lockout for their own IP+admin pair (5 tries) and, with many IPs, the per-account ceiling (20). Use a strong password and Upstash.
* `/admin` is served only to a valid admin session (302 to `/login` otherwise); all `/api/v1/admin/*` routes return 401/403 otherwise. Disable/enable and role changes re-ask for the admin's password, revoke the target's sessions and are audit logged.

## Developer Login page (`/developer-login`)
The **Developer** link on `/login` opens a separate page (`frontend/developer-login.html`, `frontend/js/developer-login.js`) that posts to `POST /api/v1/auth/developer-login`. Only an active **admin** account gets a session (`/admin`, or `/login?change=1` while a password change is pending). Every other attempt (unknown user, wrong password, a normal user's correct password, locked account) answers `200 {"redirect":"/nice-try"}` with no session cookie. It works in production for real admins, shares the login lockout, rate limit, CSRF and audit log (`login_events.method=developer`), and in development also accepts `admin__01` (below). Tests: `tests/backend/test_developer_login.py`, `tests/browser/developer_login_test.py`.

## Guest sessions (`POST /api/v1/auth/guest`)
"Continue as guest" creates a real server-side session for a throwaway `users` row (`role='guest'`, name "Guest", no email/username/password hash, `method='guest'`). The UI button is T4; the backend is in place.
* **Restricted by default:** `login_required` rejects guests with `403 guest_not_allowed` unless a route opts in with `allow_guest=True` (none does yet). So messaging, listing writes, document verification, preferences, devices, password change and every admin route are closed to guests; public browsing (listings, chatbot, search, static pages) stays open. `/messages` redirects guests to `/login`; the chatbot does not greet a guest by name; `listings/by-ref` treats a guest like an anonymous visitor.
* **Lifetimes:** idle 15 min, absolute 2 h (`GUEST_SESSION_IDLE_S`, `GUEST_SESSION_ABSOLUTE_S`); never a remember-me token; guest sessions cannot be upgraded to a user or admin session.
* **Abuse limits:** the auth per-IP rate limit, plus at most `GUEST_MAX_ACTIVE_PER_IP` (10) live guest sessions per hashed IP (`429 guest_limit`).
* **Cleanup:** logout deletes the guest row; every guest creation first removes up to `guest_cleanup_batch` (200) guests without a live session (bounded work, nothing else is touched).
* **Admin:** guests are excluded from the user list, CSV export and active-session view, and cannot be targeted by admin actions (404).
* Tests: `tests/backend/test_guest.py` (session, caps, cleanup, admin exclusion, and a route-authorization matrix over every API route x anonymous/user/guest/admin).

## Login first and the Guest experience (T4)
* `web.py` `private_page()`: `/`, `/index.html`, `/listings`, `/listings.html` need a valid server-side session (user, guest or admin) or answer 302 to `/login` (`?next=/listings` for listings). `/messages` and `/admin` keep their own checks (guests are redirected to login). Public: `/login`, `/signup`, `/developer-login`, `/nice-try`, `/privacy`, static assets, `robots.txt`, `sitemap.xml`, `/api/v1/auth/*` entry endpoints and the public listings/chat/health APIs.
* **Continue as Guest** (login page) calls `POST /api/v1/auth/guest` (CSRF token via `fetchJson`; 201 `{ok,user,redirect:"/"}`; 429 `guest_limit` when `GUEST_MAX_ACTIVE_PER_IP` live guests exist). The client only trusts a response whose `user.role` is `guest`, then goes to `/` (or `/listings` when that was the requested page).
* The UI hides what a guest cannot use (create listing, personal listings, Messages, owner-name check, device/account panel) and prompts to log in or sign up. This is convenience only: every one of those actions is refused by the server (`403 guest_not_allowed`).
* Not verified on a live deployment: that Vercel routes `/` to Flask (from `vercel.json` there are no static rewrites, so it should).

## Dev-only "Skip login" endpoint (troll) `POST /auth/dev-skip`
The old **Skip login (dev only)** toggle on `/login` was replaced by the Developer link; the endpoint is unchanged and still used by tests. Post any username and password:
* Everything ends at `/nice-try` (the dog page): `POST /api/v1/auth/dev-skip` answers `200 {"redirect":"/nice-try"}`, no session, no matter what was typed.
* The one exception: username `admin__01` (two underscores, not `admin_001`) with the password in `DEV_ADMIN_PASSWORD` starts an admin session and goes to `/admin`.
* `DEV_ADMIN_PASSWORD` ships **empty** in `.env.example`. You choose the value in your own `.env`. Empty or unset can never match, so the button stays a pure troll.
* Safety limits, all enforced on the server: the endpoint answers 404 when `APP_ENV=production` (Vercel sets it); the admin shortcut also refuses when `DATABASE_URL` is set (local SQLite only); the `admin__01` row has no password hash, so the normal login form can never sign into it; wrong guesses at `admin__01` are written to `login_events` (`method=dev_skip`); CSRF and the per-IP login limiter still apply.
* Tests: `tests/backend/test_dev_skip.py`. To remove the feature entirely, delete `backend/services/dev_skip.py`, the `/auth/dev-skip` route in `backend/api/auth.py`, and the `admin__01` branch in `developer_login`.

## Local quick start
```
cp .env.example .env      # set ADMIN_001_PASSWORD=<any throwaway value>
npm start                 # http://localhost:5000/login  (user: admin_001)
```
Migrations (`backend/db/migrations/*.sql`) and the admin seed run automatically on first use.

## Database choice
Neon or Supabase Postgres (`DATABASE_URL`). The Postgres adapter (`backend/db/connection.py`) needs `psycopg[binary]` pinned in `pyproject.toml` and **has not been run against a real Postgres yet**; local/test use SQLite. See KNOWN_ISSUES.

## Not implemented yet
Google sign-in, forgot-password and remember-me are built; admin TOTP/step-up is built (session 16, `docs/ADMIN.md`). `ADMIN_EMAILS` promotion must only apply to *Google-verified* emails: password sign-ups are unverified, so honouring it for them would let anyone claim admin.


## Login page (Part 1A)
`frontend/login.html` + `css/tokens.css` + `css/login.css` + `js/auth-page.js` follow `design-reference/login`
(navy/teal/blue, Poppins, pill inputs, hexagon photo). The login field accepts a username (`admin_001`) or an email.
Sign-up asks for full name, email, password and confirmation; the hint shows the real server policy (min 10 characters,
common passwords rejected). `?next=/path` is followed only for normal users and only for same-site paths
(`safeRedirect` rejects `//host` and `/\host`); admin, forced-password-change and `/nice-try` redirects always win.
The Google button shows "not configured" until server-side ID-token verification exists. Browser test:
`python tests/browser/login_test.py` (set `LOGIN_SHOTS=<dir>` to keep screenshots).


## Google sign-in
**Flow.** The login page asks `GET /api/v1/auth/google/config` for the public client id and a single-use nonce, loads
`https://accounts.google.com/gsi/client`, renders Google's official button (FedCM enabled) and POSTs the returned ID token
to `POST /api/v1/auth/google` (CSRF protected). The server (`services/google_oauth.py`) verifies, in this order: signature
through `google-auth` (`verify_oauth2_token`, which also checks `aud` and `exp`), then again in our code `aud == GOOGLE_CLIENT_ID`,
`iss`, `exp`, the **nonce** (we issued it, unused, < 10 min old, consumed atomically), and `email_verified is true`. Every failure returns
the same generic 401. Nothing the browser says about identity is trusted before that.

**Accounts.** Known `sub` -> sign in. Unknown `sub`, new email -> create a user (`method=google`, no password). Unknown `sub`,
email matches a password account -> **link**. Because sign-up has no email verification yet, that password account might belong
to someone who does not own the address (pre-hijacking), so linking **clears its password and revokes all its sessions**; the real
owner can set a new password later (forgot-password). `admin_001` (the seeded account with a username) is never linked or created via Google.
Disabled accounts are refused. `ADMIN_EMAILS` promotes a Google-verified email to `admin` (audit-logged); password sign-ups are never promoted.

**CSP / COOP.** Only `https://accounts.google.com/gsi/` is opened (script `client`, style `style`, frame, connect). `/login` and `/signup`
use `Cross-Origin-Opener-Policy: same-origin-allow-popups` (Google's popup needs `window.opener`); every other page keeps `same-origin`.

### Setting up the Google OAuth client (you do this once)
1. Google Cloud Console -> create/select a project -> **APIs & Services -> OAuth consent screen**: External, app name "Karachi Property Trust", your support email; add yourself as a test user while in Testing.
2. **Credentials -> Create credentials -> OAuth client ID -> Web application.** No client secret is used by this app.
3. **Authorized JavaScript origins** (Google rule: scheme + host + port only, no path, query, fragment or wildcard; `https` except for localhost; a non-default port must be written out). Add **exactly the origin shown in the browser's address bar**, one entry per origin you use:
   * local: `http://localhost:5000` and/or `http://127.0.0.1:5000` (they are two different origins; the dev server listens on `127.0.0.1`, port from `PORT`, default 5000 - change the entries if you use another port or `KPT_HOST`);
   * production: the exact public `https://` origin of the deployment. `https://karachi-property-trust-55s4.vercel.app` was recorded in earlier docs but **nothing in the code or config proves it is the real production domain**: confirm it in the Vercel project, and add any custom domain separately. Vercel preview URLs are different origins and are not covered.
   Leave **Authorized redirect URIs empty**: the page uses Google Identity Services and receives an ID token in a JavaScript callback (`POST /api/v1/auth/google`); the server never receives a redirect from Google.
4. Copy the client id (`...apps.googleusercontent.com`) into `GOOGLE_CLIENT_ID` (`.env` locally, Vercel Environment Variables in production). Origins can take a few minutes to propagate.
5. Optional: `ADMIN_EMAILS=you@gmail.com` to make your Google account an admin.
**Env names:** `GOOGLE_CLIENT_ID` (public client id, no client secret exists in this design), optional `ADMIN_EMAILS`, `APP_BASE_URL` (emailed links only), `PORT`. `google-auth` (+ `requests`) must be installed in the runtime (declared in `pyproject.toml` as ranges, still marked "PIN ME"); without it `/auth/google` answers `503 google_unavailable` and nobody is signed in.

**`Error 400: origin_mismatch`** means the origin of the page that rendered the Google button is not in the client's Authorized JavaScript origins (Google's own definition). Typical causes: `localhost` vs `127.0.0.1`, a different port, `http` vs `https`, the Vercel preview URL, or an origin typed with a path/trailing slash. Fix it in Cloud Console (changes can take minutes to hours), not in the app; the app's token checks are not involved.

**Checking the setup without exposing secrets:** `GET /api/v1/auth/features` -> `google:true` and `GET /api/v1/auth/google/config` -> `configured:true` prove only that `GOOGLE_CLIENT_ID` is set (the client id is public). The real proof is manual: open `/login` at an authorized origin, the official Google button renders, sign in with a Google account, land on `/`, then the cookie banner appears (T5). **Status: live Google sign-in has NOT been verified** (no network or owner Google project in the sandbox). Tests use a fake verifier: `tests/backend/test_auth.py` `GoogleTests` (11, incl. failure paths: no session on any failure, 400 on a missing credential, 503 without `google-auth`) and `tests/browser/cookies_test.py` section 6.


## Forgot password
`POST /auth/forgot` always answers `202` with the same body. If the email belongs to an active account (not `admin_001`), a 256-bit
token is created, **only its SHA-256 is stored** (`password_resets`, one live token per user), and `{APP_BASE_URL}/login?reset=<token>`
is emailed; it works once, for 15 minutes. `POST /auth/reset` consumes the token atomically, applies the password policy (a weak password
leaves the token usable), sets the password, and revokes every session of that user. The login page removes `?reset=` from the address bar
immediately. Google-only accounts can use this to add a password (they have proven they own the email).
Email is sent by `services/mailer.py` (Resend over HTTPS, stdlib only). **You must set `RESEND_API_KEY`, `MAIL_FROM`, `APP_BASE_URL`**; without
them the endpoints still work, no mail is sent, `/auth/features` reports `password_reset:false` and the page tells the visitor to contact the
administrator. In development the link is logged instead (never in production). Not exercised against the live provider (no network in the sandbox).
Known limit: the request path for an existing account does slightly more work than for an unknown one (an email send); rate limiting bounds probing.


## Bans and suspensions
`users.status` is `active`, `disabled` or `banned`; `user_bans` keeps the append-only history (kind, reason, actor, timestamps, lift reason).
Enforcement is central: `SessionService.lookup`, password login, Google login and remember-me redemption all deny any status other than
`active`, so no endpoint can forget it. A ban revokes every session and remember token immediately. A temporary ban that has expired is
reinstated lazily the next time the account is seen (history row closed with `lifted_by=system`, audit entry `ban_expired`).
Protected: `admin_001` can never be disabled, banned or demoted; admins must be demoted before they can be banned; the last active admin
cannot be removed; nobody can ban themselves. Ban/unban need a reason and the admin's password, and the audit row is written first, so an
audit failure aborts the action. A banned user who logs in with the right password sees the same generic failure as a wrong password
(the reason `banned` is recorded in the login events).

**Cookie consent timing (T5a):** `/login`, `/signup`, `/developer-login` and `/nice-try` do not load the consent banner. It appears on the first page after password login, sign-up, Google sign-in or Continue as guest, only when no current choice is recorded; a recorded choice is not asked again until the policy version changes. Consent is not authentication and grants nothing. On a first visit "Remember me" finds no Preferences consent, so no remember token is issued and the response carries `remember_note`. Google is covered with a fake verifier only (`tests/browser/cookies_test.py`, `tests/backend/test_auth.py`); live Google sign-in is unverified. See `docs/COOKIES.md`.
