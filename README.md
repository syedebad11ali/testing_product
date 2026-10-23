# Karachi Property Trust

A mobile-first property browsing and verification web app for Karachi, with an AI **Property Assistant** that answers questions from a 16,000-record dataset and a pre-trained price-estimation model.

- **Frontend** — plain HTML/CSS and native ES modules. No build step, no framework.
- **Backend** — one Flask app: chat API, health check, and static file serving.
- **Data** — five CSV files + a saved scikit-learn model (never retrained at runtime).

> The app and its data are **demo/test material** (`DEMO-KPT-…` ids, fictional owners). Document verification compares against available records only and is **not** proof of authenticity.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Python 3.12
python scripts/install_deps.py      # installs the pinned versions from pyproject.toml
cp .env.example .env            # optional: add GEMINI_API_KEY for Gemini answers
npm start                       # = python -m backend.app  ->  http://localhost:5000
```

Without a Gemini key the assistant still works using the built-in offline engine.
Open the site **through the server** (or any static HTTP server): ES modules do not load from `file://`.

## Tests

```bash
npm test          # frontend + domain logic (Node >= 20, zero dependencies)
npm run test:py   # backend (unittest, no network)
npm run test:all
```

## Repository layout

```
backend/            Flask app (see docs/ARCHITECTURE.md)
  app.py              app factory; Vercel entrypoint `backend.app:app`
  config.py           the only place environment variables are read
  errors.py           uniform JSON errors      middleware.py   CORS + rate limit
  api/                routes (chat, health) mounted at /api/v1 and legacy /api
  services/           chat orchestration, Gemini + offline engines, tools, prompts
  records/            CSV store + price model access, text helpers
  ml/                 price_prediction_pipeline.py + price_model.joblib
  datasets/           the 5 source CSVs (source of truth)
frontend/           served by Flask
  index.html  css/  js/  widget/ (embeddable chat widget)
  js/domain/          pure business logic (no DOM): extraction, verification rules, CSV store
  js/features/        screens (UI + controllers)     js/state/   state slices
  js/services/        HTTP, chat API, OCR            js/core/    storage, errors, html
public/assets/      images, logos, sample documents, browser copy of the CSVs (CDN-served)
tests/              frontend/  backend/  fixtures/  manual/
docs/               architecture, API, development, migration, known issues
scripts/            sync_datasets.py, manifest-report.mjs
notebooks/ data-source/   analysis material (not deployed)
```

## Documentation

| Doc | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | layers, data flow, state, error handling, design decisions |
| [docs/API.md](docs/API.md) | endpoints, request/response shapes, error codes |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | setup, configuration table, conventions, how to add a feature/endpoint, deploy |
| [docs/MIGRATION.md](docs/MIGRATION.md) | where every old file/function went, and every behaviour change |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | pre-existing problems found during the refactor |

## License

All rights reserved to **syedebad11ali** and **ctrl-shift-ali**
