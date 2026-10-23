# Migration guide (old layout → new)

## Files
| Old | New |
|---|---|
| `js/app.js` (2,261 lines) | split across `frontend/js/{app,core,data,domain,features,services,state,ui}` + `main.js` |
| `js/extraction.js`, `js/owner_verification.js` | `frontend/js/domain/extraction.js`, `ownerVerification.js` (now ES modules) |
| `css/styles.css` | `frontend/css/*.css` (same order, same rules; 9 dead lines removed) |
| `index.html`, `orv.html` | `frontend/index.html`; `frontend/orv.html` is now a 5-line redirect |
| `Chatbot/app.py` | `backend/app.py` (+ `config.py`, `errors.py`, `middleware.py`, `web.py`, `api/`) |
| `Chatbot/chatbot_core.py` | `backend/records/{store,text}.py`, `backend/services/*.py` |
| `Chatbot/price_prediction_pipeline.py`, `price_model.joblib`, `*.csv` | `backend/ml/…`, `backend/datasets/…` |
| `Chatbot/chatbot.js/.css`, `Chatbot/index.html` | `frontend/widget/chatbot.js/.css`, `demo.html` (public URLs unchanged) |
| `tests/*.test.js` | `tests/frontend/*.test.js` (ESM, `node:test`) |
| `testpack/` | `tests/manual/` (documents were duplicates of `public/assets/samples/`) |
| `public/assets/Dataset/*.ipynb, *.xlsx` | `notebooks/`, `data-source/` |

## Deleted (verified duplicates or dead)
- Root `price_prediction_pipeline.py` (shim), stale copies of the pipeline and `price_model.joblib` in `public/assets/Dataset/`
- `testpack/documents_png|pdf` (byte-identical to `public/assets/samples`)
- ~230 dead lines of `orv.html`; the embedded 20 KB base64 logo (byte-identical to `assets/logo-icon.png`); dead FAQ-accordion CSS; committed `tests/manifest_results.json` (now generated into git-ignored `tests/.results/`)

## Behaviour changes (everything that is not a pure move)
1. **ES modules:** the site must be served over HTTP; opening `index.html` via `file://` no longer works.
2. **Config location:** `.env` now lives in the repo root (was `Chatbot/.env`). Deployment entrypoint is `backend.app:app` and the function key in `vercel.json` is `backend/app.py` — update Vercel settings if you override them.
3. **API:** `/api/v1/{chat,health}` added; `/api/{chat,health}` still work. Frontend now calls `/api/v1/chat` (override with `window.KPT_CONFIG.chatApiUrl`; legacy `window.KPT_CHAT_API_URL` still honoured).
4. **Errors:** unexpected 500s return a generic message + `error_id` instead of `ExceptionType: message`. All API errors carry a `code`. Non-object / non-string chat payloads return 400.
5. **Rate limiter:** now thread-safe and prunes idle IPs.
6. **Frontend robustness:** render error boundary, unknown-view fallback, global error toast, safe storage, 30 s chat timeout with friendlier network error text.
7. **Security fix:** the home search box value is now HTML-escaped (was injected raw into an attribute).
8. **Handlers:** five inline handlers that assigned to globals (`state.search=…`, `ownerVerificationId=…`) are now named functions (`setSearch`, `setOwnerPropertyId`, …).

Verified identical: backend answers on 20 queries + stats/predict/search/overview vs the original; rendered HTML for 59 screen/state combinations vs the original `app.js` (after accounting for items 7–8 and the logo URL).

## Phase 1–3 changes (security)
| Change | Detail |
|---|---|
| Public CSVs | `public/assets/Dataset/*.csv` no longer contain `Owner ID`, `Owner Name`, `Property Owner`, `Previous Owner`. Regenerate with `python scripts/sync_datasets.py`. |
| Owner Verification screen | No longer displays owner names/IDs. It has a "Check an owner name" form backed by `POST /api/v1/verification/check`. |
| `domain/ownerVerification.js` records | `ownerId`, `ownerName`, `listedOwner`, `previousOwner` removed from parsed records. |
| `GET /api/v1/health` | Now `{"status":"ok"}` only. Old detail moved to `/health/detail` (token). |
| Rate limiter | `RateLimiter(limit, window, store, name)`; 429 message is "Too many requests…" and includes `Retry-After`. |
| Error bodies | Every error JSON now has `request_id`. |
| New routes | `/nice-try`, `/nice-try.html` (static page, `frontend/nice-try.html`). |
