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
Public `health` returns only `{"status":"ok"}`. `health/detail` (Bearer `HEALTH_DETAIL_TOKEN`) returns model, record counts and real startup errors; without the token it is a 404.

## Headers on every response
`X-Request-ID` (also in every error body as `request_id`), CSP, HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP. `/api/*` is `Cache-Control: no-store`. `429` carries `Retry-After`.

## Adding an endpoint
1. Create `backend/api/<resource>.py` with `bp = Blueprint("<resource>", __name__)`.
2. Add the module to `RESOURCES` in `backend/api/__init__.py` (it is mounted at both prefixes).
3. Put logic in `backend/services/`; raise `ApiError(message, status, code)` for expected failures.
4. Add a test in `tests/backend/test_api.py`.
