# Development guide

## Setup
```bash
python -m venv .venv && source .venv/bin/activate     # Python 3.12 (.python-version)
python scripts/install_deps.py                         # pinned deps from pyproject.toml
cp .env.example .env
npm start                                              # http://localhost:5000
```
Node ≥ 20 is only needed for the tests (no npm packages are installed).
Serve over HTTP — ES modules and the sample-document loader do not work from `file://`.

## Configuration (environment variables)
All optional. Read only in `backend/config.py`. Local: `.env` in the repo root. Vercel: Project Settings → Environment Variables. **Never commit `.env`.**

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | – | Enables Gemini; otherwise the offline engine answers |
| `GEMINI_MODEL` | `gemini-3-flash-preview,gemini-2.5-flash` | Models tried in order |
| `GEMINI_TIMEOUT_MS` | `20000` | Per-call timeout |
| `PORT` | `5000` | Local server port |
| `RATE_LIMIT_PER_MIN` | `20` | Per-IP chat requests per minute |
| `MAX_MESSAGE_LEN` | `1000` | Max chat message length |
| `ALLOWED_ORIGINS` | empty | CORS allow-list (comma-separated or `*`) |
| `VERIFY_RATE_LIMIT_PER_MIN` | `10` | Per-IP owner-name checks per minute |
| `TRUSTED_PROXY_HOPS` | `1` on Vercel, else `0` | Number of proxies whose `X-Forwarded-For` entry is trusted (sets the real client IP) |
| `KPT_HOST` | `127.0.0.1` | Bind address of the local dev server (`python -m backend.app`). `0.0.0.0` only to test from another device |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | empty | Shared rate-limit counters (Upstash Redis REST). Empty = per-process memory (fine locally, NOT shared on Vercel) |
| `CONTACT_WHATSAPP` / `CONTACT_EMAIL` | empty | Enable hand-off buttons ("talk to an agent") prefilled with a chat summary. Empty = the bot says contact channels are not configured |
| `MESSAGE_RATE_LIMIT_PER_MIN` | 20 | Per user and per IP limit for message / listing writes |
| `APP_ENV` | `development` (`production` on Vercel) | Production enables Secure cookies, refuses a weak `admin_001` password and requires `DATABASE_URL` |
| `DATABASE_URL` | empty | Postgres URL. Empty locally = SQLite at `.local/kpt.sqlite3`. In production, empty = accounts return 503 |
| `ADMIN_001_PASSWORD` | empty | Seeds `admin_001` (hash only stored). Empty = account disabled; wrong/weak-in-production = not created |
| `RESEND_API_KEY` | empty | Email provider key (secret). With `MAIL_FROM`, enables password-reset emails. Empty = disabled |
| `MAIL_FROM` | empty | Sender, e.g. `Karachi Property Trust <no-reply@yourdomain>` (domain must be verified at the provider) |
| `APP_BASE_URL` | `VERCEL_URL` or `http://localhost:5000` | Public base URL placed in emailed links |
| `GOOGLE_CLIENT_ID` | empty | Public OAuth Web client id. Empty = Google sign-in disabled (button says "not configured", `POST /auth/google` returns 503) |
| `ADMIN_EMAILS` | empty | Comma-separated emails promoted to `admin` **only** when they sign in with Google (verified email). Never applied to password sign-ups |
| `IP_HASH_SALT` | dev-only value | HMAC key for the truncated IP hash in `login_events`/`audit_log`. Set a secret in production |
| `SESSION_IDLE_S` / `SESSION_ABSOLUTE_S` | 1800 / 43200 | Session idle and absolute lifetime (admins: 900 / 7200, fixed in config) |
| `LOGIN_RATE_LIMIT_PER_MIN` | 10 | Per-IP limit on signup/login (fail-closed when Upstash is configured) |
| `LOCKOUT_THRESHOLD` | 5 | Failed logins per (account, IP) within 15 min before lockout; per-account ceiling is 4x |
| `COOKIE_SECURE` | on in production | `1/0` override. Secure cookies use `__Host-` names |
| `DATA_DIR`, `MODEL_PATH` | `backend/datasets`, `backend/ml/price_model.joblib` | Overrides |

Frontend: `window.KPT_CONFIG = { chatApiUrl, chatTimeoutMs }` before `js/main.js` loads (see `js/config.js`).

## Conventions
- **Python:** `snake_case` modules/functions, `PascalCase` classes, type hints on new code, `log = logging.getLogger("chatbot")`. No `os.getenv` outside `config.py`; no Flask imports in `services/` or `records/`.
- **JavaScript:** `camelCase` functions/variables, `UPPER_SNAKE` constants, file names in `camelCase.js`. `render*` returns an HTML string; `docX`/`ownerX` prefixes belong to the feature that owns them. Escape every interpolated value with `escapeHtml`.
- **Layering:** `domain/` must not touch `document`, `window`, state or `fetch`. If you need those, it belongs in `features/` or `services/`.
- **Errors:** raise `ApiError` (backend) / `AppError` (frontend) for expected failures; use `reportError` in catches that cannot recover. Do not swallow errors silently.
- **State:** add fields to an existing slice in `state/store.js`; mutate slices in place, never reassign.

## Adding a frontend feature
1. Create `js/features/<name>.js` exporting `render<Name>()` and its handlers; put rules in `js/domain/`.
2. Register the view in `VIEWS` in `js/app/router.js`.
3. Any function called from a `data-onclick="…"` (or `data-oninput/onchange/onsubmit`) goes in `ACTIONS` in `js/ui/actions.js` (the handler test will tell you if you forget). Never write inline `onclick=` (the CSP forbids it).
4. Browser check before release: `python tests/browser/smoke.py` (needs Playwright + Chromium).
4. Add styles in the matching `css/*.css` file (load order is in `index.html`).

## Data and model
- Edit CSVs in `backend/datasets/`, then `python scripts/sync_datasets.py`.
- Retrain: `python backend/ml/price_prediction_pipeline.py backend/datasets --save backend/ml/price_model.joblib`. The pinned scikit-learn version must match the one that wrote the file (see `pyproject.toml`).

## Testing
`npm run test:all`. Frontend tests cover the domain logic against recorded OCR fixtures, rendering of every screen, the handler registry, storage/HTTP failure paths. Backend tests cover the API contract, error shapes, rate limiting, CORS and store behaviour. `node scripts/manifest-report.mjs` prints the full document-verification report. Camera/OCR/browser behaviour is **not** covered by automated tests — check `tests/manual/README.txt`.

## Deploy (Vercel, one Flask app)
`pyproject.toml` → `[tool.vercel] entrypoint = "backend.app:app"`; `vercel.json` configures the function. `public/assets/` is served by the CDN; everything else by Flask. After deploying, open `/api/v1/health` — it returns the real startup error if the model or data failed to load.
Static-only hosting (e.g. GitHub Pages) serves the frontend but not the chat API: deploy the backend separately, set `window.KPT_CONFIG.chatApiUrl`, and set `ALLOWED_ORIGINS` on the backend.

| `MESSAGE_RETENTION_DAYS` / `REPORT_RETENTION_DAYS` | `0` (off) / `730` | Retention periods for `scripts/purge_messages.py`; `0` disables purging. Needs owner approval before production use |
| `TOTP_ENCRYPTION_KEY` | empty | Fernet key that encrypts admin TOTP secrets; empty/invalid = two-factor unavailable (fail closed). Secret: never commit |
| `ADMIN_TOTP_REQUIRED` | `0` | `1` = admins must have TOTP for sensitive actions (enable only after recovery is rehearsed) |
| `TOTP_ISSUER` / `STEPUP_TTL_S` | `Karachi Property Trust` / `120` | Name shown in authenticator apps; lifetime of a step-up proof in seconds |

## Windows notes (line endings and encodings)
* `.gitattributes` normalises all text to LF (`* text=auto eol=lf`) and marks `public/assets/vendor/**` and binary types as untouchable. Reason: Git for Windows defaults to `core.autocrlf=true`; a plain clone would rewrite text files to CRLF, which changes byte hashes (SRI / SHA-256 of vendored Tesseract.js and PDF.js, fixture checks). `tests/backend/test_gitattributes.py` fails if a new binary type is added without being declared.
* If you already have a Windows clone made before this file existed, run `git add --renormalize .` and review `git status` before committing; do not commit a mass line-ending change you did not expect.
* Text-mode file reads/writes and `subprocess(..., text=True)` calls must pass `encoding="utf-8"` (guarded by `tests/backend/test_text_encoding.py`); JS tests must convert `import.meta.url` with `fileURLToPath` (guarded by `tests/frontend/portablePaths.test.js`).
