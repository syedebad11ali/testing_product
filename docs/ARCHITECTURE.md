# Architecture

## Backend (`backend/`)

```
request ──► middleware (CORS, rate limit) ──► api/<resource>.py  (thin: validate, call service, jsonify)
                                                   │
                                                   ▼
                                         services/chat_service.py
                                  greeting? ─► Gemini (tools / search grounding) ─► offline engine
                                                   │                                   │
                                                   └────────────► records/store.py ◄───┘
                                                                  (CSV records + ml/price_model.joblib)
```

| Layer | Responsibility | Rule |
|---|---|---|
| `config.py` | Build a frozen `Settings` from the environment | Only module that calls `os.getenv`. Bad numbers fall back to defaults instead of crashing at import. |
| `api/` | HTTP in/out | No business logic. One module per resource, each exposes `bp`. Mounted at `/api/v1` and legacy `/api`. |
| `services/` | Chat orchestration and engines | No Flask imports. Receive `Settings`; testable without HTTP. |
| `records/` | Read-only data + model access | Owner names/ids are **never loaded**. |
| `ml/` | Price model pipeline | Keep the filename `price_prediction_pipeline.py`: the pickle references that module name. |
| `errors.py` | `ApiError` + handlers | Every error is `{"error", "code"}`. Unexpected errors are logged with an `error_id` and returned generically. |

`create_app(settings)` builds everything; the chat service is created lazily on first use so importing the app never loads the model.

## Frontend (`frontend/js/`)

Native ES modules, loaded by `main.js`. Dependencies point **downwards**:

```
features/ (screens + controllers)  ──►  domain/ (pure rules)  ──►  data/ (constants, demo records)
        │                                    ▲
        ├──► services/ (http, chatApi, ocr)  │ no DOM, no state, unit-tested
        ├──► state/store.js
        └──► core/ (html, storage, errors), config.js
```

- **`domain/`** — business logic with no DOM or global state: `extraction.js` (parse OCR/PDF text), `documentVerification.js` (matching + decision), `ownerVerification.js` (CSV parsing, lookup, forecast), `propertyStatus.js`.
- **`features/`** — each screen exports `render*` functions that return HTML strings plus the handlers its markup calls.
- **`state/store.js`** — a few exported slices (`state`, `ownerState`, `docState`, `docHistory`, `chatState`) plus reset/persist helpers. Slices are never reassigned. Rendering stays explicit (`render()`) because re-rendering on each keystroke would steal focus from form inputs.
- **`app/router.js`** — `nav()` + `render()` with an **error boundary**: unknown views fall back to home; a throwing screen shows a recovery card.
- **`ui/actions.js`** — the single list of functions published on `window` for inline `onclick="…"` attributes. `tests/frontend/handlers.test.js` fails if a template calls a handler that is not listed.

### Error handling

| Where | Behaviour |
|---|---|
| Storage | `core/storage.js` never throws (private mode, quota). |
| Network | `services/http.js` adds a timeout and typed `AppError`s (`timeout`, `network`); `chatApi.js` maps them to user-facing messages. |
| Rendering | Error boundary in `router.js`. |
| Anything uncaught | `installGlobalErrorHandlers()` logs it and shows a toast. |

### Runtime configuration
`js/config.js` is the only module reading `window.KPT_CONFIG` (`chatApiUrl`, `chatTimeoutMs`). Nothing secret may live in frontend code.

## Data duplication
`backend/datasets/*.csv` is the source of truth. The browser needs the same files as static assets, so `public/assets/Dataset/` holds copies. `python scripts/sync_datasets.py` copies; a test fails if they drift.
