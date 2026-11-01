# Dependencies

`pyproject.toml` is the single source of truth (Vercel installs from it; `python scripts/install_deps.py [--dev]` reads it).
`tests/backend/test_dependencies.py` fails if code imports an undeclared package or a declared one is unused.

**Status legend:** `pinned` = exact `==` version verified by `npm run test:all`. `PIN ME` = still a range; install it, run the
tests, then replace the range with the exact version (`pip freeze | grep -i <name>`). Licences below are from memory of each
project's published licence; confirm with `pip-licenses` before shipping to a client.

## Production (`[project].dependencies`)

| Package | Version | Status | Purpose | Imported by | Licence |
|---|---|---|---|---|---|
| Flask | 3.1.3 | pinned | HTTP app, blueprints | `backend/app.py`, `backend/api/*` | BSD-3 |
| python-dotenv | 1.2.2 | pinned | loads `.env` locally | `backend/config.py` | BSD-3 |
| openai-agents | >=0.23,<1 | PIN ME | Agents SDK; opt-in chat engine (`AI_ENGINE=agents`), lazy import, falls back when absent | `backend/services/ai/agents_engine.py` | MIT |
| openai | >=3,<4 | PIN ME | `AsyncOpenAI` for OpenAI and for Gemini's OpenAI-compatible endpoint (range matches `pyproject.toml`) | `backend/services/ai/agents_engine.py` (lazy import) | Apache-2.0 |
| google-genai | >=2.14,<3 | range | Gemini native client, Google Search grounding only | `backend/services/gemini_engine.py` | Apache-2.0 |
| google-auth | >=2.30,<3 | PIN ME | verify Google ID tokens server-side | `backend/services/google_oauth.py` (lazy import) | Apache-2.0 |
| requests | >=2.32,<3 | PIN ME | HTTP transport google-auth needs for Google's public certs | planned (via google-auth) | Apache-2.0 |
| psycopg[binary] | >=3.2,<4 | PIN ME | PostgreSQL driver (Neon/Supabase) | `backend/db/connection.py` | LGPL-3.0 |
| pyotp | ==2.10.0 | pinned (installed from the supplied wheel and tested) | TOTP codes for admin two-factor | `backend/services/totp_service.py` | MIT |
| cryptography | >=50 | **PIN ME, unverified.** Previously ==46.0.6 (9 pip-audit findings). Install, run TOTP/Fernet tests + pip_audit, then pin the exact version that passed | Fernet encryption of TOTP secrets at rest | `backend/services/totp_service.py` | Apache-2.0 / BSD |
| pandas | 3.0.2 | pinned (model) | price model + data | `backend/records`, `backend/ml` | BSD-3 |
| numpy | 2.4.4 | pinned (model) | numeric arrays | `backend/ml` | BSD-3 |
| scikit-learn | 1.9.1 | pinned (model) | must match the version that wrote `price_model.joblib` | `backend/ml` | BSD-3 |
| scipy | 1.17.1 | pinned (model) | scikit-learn dependency | transitive | BSD-3 |
| joblib | 1.5.3 | pinned (model) | loads the serialised model | `backend/ml` | BSD-3 |
| threadpoolctl | 3.6.0 | pinned (model) | scikit-learn dependency | transitive | BSD-3 |

"planned" rows are declared before the code that imports them exists; the dependency test lists them explicitly
(`PLANNED`) and fails when one becomes used so the list shrinks as the features land.

## Dev only (`[project.optional-dependencies].dev`, never installed on Vercel)

| Package | Version | Status | Purpose | Licence |
|---|---|---|---|---|
| ruff | >=0.6 | PIN ME | lint + format (Python) | MIT |
| bandit | >=1.7 | PIN ME | static security scan (`bandit -r backend`) | Apache-2.0 |
| pip-audit | >=2.7 | PIN ME | known-vulnerability scan | Apache-2.0 |
| playwright | ==1.56.0 | pinned (session 17: Python 3.12.3 + Chromium, all `tests/browser/*.py` passed) | browser smoke tests (`tests/browser/smoke.py`) | Apache-2.0 |

Optional extra `argon2` (`argon2-cffi`) exists only if password hashing is switched from stdlib scrypt to argon2id.

## Node tooling

`package.json` declares no dependencies: tests use Node's built-in test runner (Node >= 20). Nothing is built or bundled.

## Notes

- psycopg is LGPL-3.0; using it unmodified as a library is fine for a closed deployment, but note it in client hand-over.
- Do not bump the model-locked pins without running `npm run test:all`.
- Installed size of `openai-agents` + `openai` against Vercel's function size limit has **not** been measured yet (Part 10.6).

## npm (session 19 decision)
`package.json` declares **no `dependencies` and no `devDependencies`** (the frontend has no build step; tests use Node's built-in runner). There is therefore nothing to lock or audit with npm, so no `package-lock.json` was created and `npm audit` was not run (it needs a lockfile and the registry; neither is meaningful here). If an npm package is ever added, run `npm install` once on a networked machine, review and commit the lockfile, add the `npm` ecosystem to `.github/dependabot.yml` and run `npm audit`. Third-party browser assets are tracked separately via `scripts/vendor_assets.py` and `tests/backend/test_external_assets.py`.
