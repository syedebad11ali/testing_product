# API

Canonical base path: **`/api/v1`**. The legacy `/api/...` paths are permanent aliases (existing embeds use them).

## `POST /api/v1/chat`
Request (JSON):
```json
{ "message": "price of a house in DHA", "session_id": "optional, ≤64 chars" }
```
Success `200`:
```json
{ "reply": "…", "source": "gemini|offline|greeting|…", "from_data": true }
```
`from_data` is true when the answer was grounded in the local records. The conversation is tracked server-side by the `session_id` you send (a new one is generated if omitted).

## `GET /api/v1/health`
`200` `{ "status": "ok", "gemini": bool, "models": [...], "records": 16000, "model": "…", "data_files": {...} }`
`503` `{ "status": "error", "code": "service_unavailable", "error": "<startup error>" }` — used to diagnose deploys.

## Errors
Always `{ "error": "<message>", "code": "<code>" }`.

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_json` / `invalid_message` / `empty_message` / `message_too_long` | bad request body |
| 404 | `not_found` | unknown `/api/…` path |
| 429 | `rate_limited` | more than `RATE_LIMIT_PER_MIN` requests per IP per minute |
| 500 | `internal_error` (+ `error_id`) | unexpected failure; details are only in the server log |

CORS: same-origin by default; set `ALLOWED_ORIGINS` to allow other sites.

## `POST /api/v1/verification/check`
Compares a claimed owner name with the registered owner **on the server**. Owner names are never returned.

Request: `{"property_id": "DEMO-KPT-8103", "owner_name": "Full Name"}` (both required text; id ≤ 40, name ≤ 120 chars).
Response: `{"result": "match" | "mismatch" | "unable_to_verify", "indicative": true, "note": "…"}`.
Errors: `400 invalid_json / invalid_property_id / invalid_owner_name`, `429 rate_limited` (see `VERIFY_RATE_LIMIT_PER_MIN`).
Auth: **none yet** (planned: logged-in users only, phase 4).

## `GET /api/v1/health` and `/health/detail`
Public `health` returns only `{"status":"ok"}`. `health/detail` (admin session only) returns model, record counts and real startup errors; for anyone else it is a 404.

## Headers on every response
`X-Request-ID` (also in every error body as `request_id`), CSP, HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP. `/api/*` is `Cache-Control: no-store`. `429` carries `Retry-After`.

## `POST /api/v1/chat` (extended) and `POST /api/v1/chat/feedback`
Request adds optional `"reset": true` (forget this session's memory). Response keeps `reply, source, from_data` and adds `intent, specialist, chips[], cards[], actions[], memory, message_id`; full schema in `docs/CHATBOT.md`.
Feedback: `{"message_id": "<from the reply>", "rating": "up"|"down"}` → `{"ok": true}`; `400 invalid_message_id / invalid_rating`; rate limited like chat. No login required.

## Cookies, devices and chat continuity (session 6)
All under `/api/v1/auth/` (CSRF protected): `GET /devices`, `POST /devices/revoke {id}`, `POST /logout-all`, `GET|PUT /prefs`, `POST /forget-device`, `POST /delete-account {password, confirm:"DELETE"}`.
`POST /auth/login` and `/auth/google` accept `"remember": true`; the response adds `remembered` and, when not remembered, `remember_note`.
`GET /chat/session` returns `{continuity, history[], memory, welcome}` for a returning visitor with Preferences consent. `POST /chat` returns `continuity: true` when the chat cookie identifies the conversation (the client then omits `session_id`); `reset: true` clears the stored conversation. See `docs/COOKIES.md`.

## Adding an endpoint
1. Create `backend/api/<resource>.py` with `bp = Blueprint("<resource>", __name__)`.
2. Add the module to `RESOURCES` in `backend/api/__init__.py` (it is mounted at both prefixes).
3. Put logic in `backend/services/`; raise `ApiError(message, status, code)` for expected failures.
4. Add a test in `tests/backend/test_api.py`.


## Auth and admin (v1 only, no legacy alias)
All non-GET routes below need the CSRF header: call `GET /api/v1/auth/csrf` first (sets the cookie, returns `{"csrf_token"}`) and send it as `X-CSRF-Token`. Failure: `403 csrf_failed`.

| Method + path | Auth | Request | Response |
|---|---|---|---|
| `GET /auth/csrf` | none | - | `{csrf_token}` |
| `POST /auth/signup` | none | `{name,email,password}` | `201 {ok,user,redirect}` + session cookie; `400 weak_password/invalid_email`, `409 signup_failed` |
| `POST /auth/login` | none | `{identifier,password}` | `200 {ok,user,redirect}` + cookie; `401 invalid_credentials`; for `admin_001` wrong password: `200 {"redirect":"/nice-try"}` |
| `POST /auth/logout` | any | `{}` | `{ok}`; revokes the session, clears the cookie |
| `GET /auth/me` | any | - | `{user: {id,name,role,must_change_password} | null}` |
| `GET /auth/features` | any | - | `{google, password_reset}` booleans so the UI can be honest about what is set up |
| `POST /auth/forgot` | any + CSRF | `{email}` | always `202 {ok,message}` (no enumeration); rate limited; emails a 15-minute single-use link if the account exists and email is configured |
| `POST /auth/reset` | any + CSRF | `{token,new_password}` | `{ok,redirect}`; 400 `reset_invalid` (unknown, used or expired, same body), 400 `weak_password` (token stays valid); signs the user out everywhere |
| `GET /auth/google/config` | any | - | `{configured:false}` or `{configured:true, client_id, nonce}`; the nonce is single use, valid 10 min, `no-store` |
| `POST /auth/google` | any + CSRF | `{credential}` (Google ID token) | `{ok,user,redirect}`; 503 `google_not_configured`, 401 `google_invalid` (any verification failure, same body), 401 `google_unverified` |
| `POST /auth/change-password` | user | `{current_password,new_password}` | `{ok}`; other sessions revoked |
| `POST /verification/check` | **user** | `{property_id,owner_name}` | `{result,indicative,note}`; `401 auth_required` |
| `GET /admin/users?q&page&per_page` | admin | - | `{users[],total,page,per_page}` |
| `GET /admin/login-events?limit` | admin | - | `{events[]}` |
| `GET /admin/sessions` | admin | - | `{sessions[]}` |
| `POST /admin/users/<id>/status` | admin | `{status: active\|disabled, password}` | `{ok}`; `403 reauth_failed`, `400 self_action` |
| `POST /admin/users/<id>/role` | admin | `{role: user\|admin, password}` | `{ok}` |
| `POST /admin/users/<id>/logout` | admin | `{}` | `{ok,revoked}` |

Errors: 401 `auth_required`, 403 `forbidden` / `password_change_required` / `csrf_failed`, 429 `rate_limited` (with `Retry-After`), 503 `auth_unavailable` (production without `DATABASE_URL`).


## Admin moderation (admin session, CSRF on POST, `no-store`)
| Endpoint | Notes |
|---|---|
| `GET /admin/users?q=&status=&role=&sort=&dir=&page=&per_page=` | `status`: active/disabled/banned; `sort`: created/last_login/name/role/status. Banned rows carry `ban` {kind, reason, actor, created_at, expires_at}. |
| `GET /admin/login-events?q=&outcome=&method=&page=&per_page=` | Newest first; hashed IP only, no user-agent. |
| `GET /admin/audit?page=` | Audit log with actor names. |
| `POST /admin/users/<id>/ban` | `{kind: temporary\|permanent, days (1-365), reason (3-300), password}`. Revokes sessions and remember tokens. |
| `POST /admin/users/<id>/unban` | `{reason, password}`. |
| `GET /admin/export/users.csv`, `/admin/export/login-events.csv` | Audited; formula-injection safe; no password/token fields. |
| `GET /admin/reports`, `GET /admin/reports/<id>/thread`, `POST /admin/reports/<id>/resolve` | See `docs/MESSAGING.md`. |

Error codes: `reason_required`, `already_banned`, `not_banned`, `protected_account` (admin_001, admins must be demoted before a ban),
`last_admin`, `self_action`, `banned`. Messaging endpoints: see `docs/MESSAGING.md`.

## Seller listings
`GET /listings?page=`, `GET /listings/mine?page=&per_page=`, `POST /listings {title, area}`, `GET /listings/by-ref/<ref>`, owner-only `POST /listings/<ref>/edit {title, area}` and `POST /listings/<ref>/status {status: active|closed}` (404 for non-owners; no delete route); conversation summaries gain `blocked_by_me`. Details and rules: `docs/MESSAGING.md`.

## Admin two-factor (session 16; admin role + CSRF on every route)
| Route | Body | Notes |
|---|---|---|
| `GET /admin/totp/status` | | `{status: none/pending/active, configured, required}` (never a secret) |
| `POST /admin/totp/enroll/start` | `{password}` | returns `{secret, otpauth_uri}` once; 503 `totp_unavailable` without a valid key; 409 if already active |
| `POST /admin/totp/enroll/confirm` | `{code}` | activates; 403 `invalid_code` |
| `POST /admin/totp/disable` | `{password, code}` | |
| `POST /admin/totp/stepup` | `{code, action}` | `action` in `moderation`, `role_change`, `csv_export`; returns `{proof, expires_in}`; 429 after 8 attempts / 5 min |
Sensitive routes (`users/<id>/ban|unban|status|role`, `POST export/<kind>.csv`) take `"stepup": "<proof>"` when TOTP is active; otherwise `403 stepup_required` (or `totp_enrollment_required` when `ADMIN_TOTP_REQUIRED=1`). `GET export/<kind>.csv` is refused with `stepup_required` once TOTP is active. See `docs/ADMIN.md`.
