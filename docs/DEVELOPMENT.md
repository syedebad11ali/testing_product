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
3. Any function called from an `onclick="…"` goes in `js/ui/actions.js` (the handler test will tell you if you forget).
4. Add styles in the matching `css/*.css` file (load order is in `index.html`).

## Data and model
- Edit CSVs in `backend/datasets/`, then `python scripts/sync_datasets.py`.
- Retrain: `python backend/ml/price_prediction_pipeline.py backend/datasets --save backend/ml/price_model.joblib`. The pinned scikit-learn version must match the one that wrote the file (see `pyproject.toml`).

## Testing
`npm run test:all`. Frontend tests cover the domain logic against recorded OCR fixtures, rendering of every screen, the handler registry, storage/HTTP failure paths. Backend tests cover the API contract, error shapes, rate limiting, CORS and store behaviour. `node scripts/manifest-report.mjs` prints the full document-verification report. Camera/OCR/browser behaviour is **not** covered by automated tests — check `tests/manual/README.txt`.

## Deploy (Vercel, one Flask app)
`pyproject.toml` → `[tool.vercel] entrypoint = "backend.app:app"`; `vercel.json` configures the function. `public/assets/` is served by the CDN; everything else by Flask. After deploying, open `/api/v1/health` — it returns the real startup error if the model or data failed to load.
Static-only hosting (e.g. GitHub Pages) serves the frontend but not the chat API: deploy the backend separately, set `window.KPT_CONFIG.chatApiUrl`, and set `ALLOWED_ORIGINS` on the backend.
