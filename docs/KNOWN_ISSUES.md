# Known issues (found during the refactor, not changed)

These pre-date the refactor. Behaviour was preserved on purpose; each needs a product decision.

1. **Verification false positives.** On the recorded fixtures the free-search pipeline reports *Verified* for documents that should fail: `power_of_attorney_mismatch` (OCR and PDF) and `altered_multiple_mismatch` (PDF). OCR also fails to verify five valid documents (`sale_deed`, `allotment`, `transfer_order`, `power_of_attorney` matching, `ocr_challenge`). Baseline: OCR 16/29, PDF 26/28 — locked in `tests/frontend/pipeline.test.js`. Treat results as indicative, never as proof.
2. **Owner names are downloadable.** The frontend's owner-verification feature fetches the full CSVs, including `Owner Name` / `Previous Owner`, from `/assets/Dataset/` for every visitor. Fine for the current fictional `DEMO-KPT-…` data; with real data this would be a privacy leak. Fix: add a server endpoint that answers one lookup and stop shipping owner columns to the browser.
3. **Heavy images.** `public/assets/Property Images` (~100 MB, files up to 8 MB) and `samples/` (~75 MB) are unoptimised; resize/convert to WebP for a faster first load.
4. **Two chat UIs.** The in-app assistant (`features/chat.js`) and the embeddable widget (`frontend/widget/chatbot.js`) are separate implementations of the same API. The widget must stay a standalone script for third-party embedding.
5. **Rate limit is per warm instance** (in memory), and behind a proxy `remote_addr` may be the proxy's address. Use a shared store / `X-Forwarded-For` handling for real protection.
6. **Inline `onclick` handlers** remain (published via `ui/actions.js`). Migration path: `data-action` attributes + one delegated listener.
7. **Browser behaviour is untested.** Camera, Tesseract OCR and PDF.js flows need a manual run (`tests/manual/README.txt`); the automated tests render HTML in Node with a DOM stub.
8. **Dataset is stored twice** (`backend/datasets` and `public/assets/Dataset`) because the browser needs static copies; `scripts/sync_datasets.py` + a test guard drift.
