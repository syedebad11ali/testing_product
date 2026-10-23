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

## Adding an endpoint
1. Create `backend/api/<resource>.py` with `bp = Blueprint("<resource>", __name__)`.
2. Add the module to `RESOURCES` in `backend/api/__init__.py` (it is mounted at both prefixes).
3. Put logic in `backend/services/`; raise `ApiError(message, status, code)` for expected failures.
4. Add a test in `tests/backend/test_api.py`.
