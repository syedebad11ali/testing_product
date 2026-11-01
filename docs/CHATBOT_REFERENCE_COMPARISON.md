# Chatbot: reference vs Session 22 (complete review)

The reference `Chatbot/` files were decoded from `Chatbot.rar` with a purpose-built RAR5 decoder; **every file matched its stored CRC32**. The two `.env` files were never read.
Each file below was read in full and compared with Session 22 (CRLF-normalised).

| Reference file | Session 22 counterpart | Result |
|---|---|---|
| `price_prediction_pipeline.py` | `backend/ml/price_prediction_pipeline.py` | Identical except two comment lines (module path). Nothing to port. |
| `chatbot.css` | `frontend/widget/chatbot.css` | **Byte-identical after line-ending normalisation** (including the Google Fonts `@import`). An earlier version of this report said they differed by that import; that was wrong. |
| `index.html` (demo) | `frontend/widget/demo.html` + `css/widget-demo.css` | Same page; the inline `<style>` was moved to a stylesheet for the strict CSP. |
| `chatbot.js` | `frontend/widget/chatbot.js` | Reference was better in four places: ported (timeout, tolerant parsing, offline label, subtitle typo). |
| `chatbot_core.py` `Store` | `backend/records/store.py` | Same logic line for line (S22 adds constructor paths + an owner-privacy docstring). Nothing to port. |
| `chatbot_core.py` `classify_error`, `GeminiEngine.status`, `NO_LIVE_NOTE` | (missing) | Ported: `services/ai/errors.py`, `GeminiEngine.status()/last_error`, note added to the Agents engine. |
| `chatbot_core.py` `OpenAIEngine` | (missing) | Replaced by the Agents SDK engine (not a copy: SDK-based, with handoffs and a guardrail). |
| `chatbot_core.py` `OfflineEngine` | `services/offline_engine.py` | S22's was weaker in 4 ways: ported (targeted clarifying questions, sorted-by-label stat answers, no `None`/`0 rooms` in rows, block follow-ups via `Memory`). S22's router + advisor + memory already cover the reference's `slots` for area/type/budget. |
| `chatbot_core.py` greetings, `needs_search_grounding` | `greetings.py`, `grounding.py` | Equivalent (S22's grounding also treats "forecast"/"today" as live questions, deliberately). |
| `chatbot_core.py` `ChatService.reply` | `services/chat_service.py` | S22 is a superset (specialists, memory, cards, chips, persistence, feedback). Ported: engine order (`AI_ORDER`) with fall-through between engines, and the failure `reason`. |
| `app.py` | `backend/app.py`, `api/chat.py`, `middleware.py`, `web.py`, `errors.py` | S22 already has everything: CORS from `ALLOWED_ORIGINS`, a global unhandled-error handler, the same public widget URLs (`/chatbot-demo`, `/static/chatbot.js|css`), `.env` loading, a pluggable rate limiter, stricter input validation, consent-gated chat cookie. The reference's public `/api/health` (key presence, last error) was **not** copied; S22 keeps that admin-only. |

## What was added to Session 22
* `Memory.block`: after a price question, `block 10` or a bare `10` re-runs the estimate for that block; a different area clears it. History keeps the text the user typed.
* Offline answers: targeted questions ("Which area is the plot in?"), "Cheapest / Most expensive … by median price" labels, rows without `None` or "0 rooms", friendlier no-match text.
* `AI_ORDER` (default `agents,gemini`), `reason` in the chat response, `GeminiEngine.status()`, admin health `gemini_status` (the legacy boolean `gemini` key is unchanged).
* **Agents SDK** (`services/ai/agents_engine.py`): `AGENTS_MODE=handoffs` (default): front-desk agent handing off to Price Estimator / Market Analyst / Property Finder with scoped tools; `single` mode kept. Owner-privacy guardrail (`services/ai/guardrails.py`), model fallback list, retry-once-when-busy, stop on auth errors, redacted `last_error`, tracing off.

## What the Agents SDK can and cannot cover here
Used for: the answer engine, specialist routing (handoffs) and the input guardrail. **Not** suited to, and so not rewritten with it: `Store`, price model, deterministic offline answers, Flask routes, rate limiting, widget code. Those are data/HTTP/UI code with no model call. Session persistence stays on S22's own `chat_store` (not the SDK's session classes).

## Verification status (honest)
* Verified here: Python 253 tests (252 ok + the known `pyotp` import error), frontend 144/144, behaviour probed against the real store and price model.
* **Not verified:** the real `openai-agents` / `openai` packages (not installable in the sandbox, no network). Tests inject a *fake* SDK, so they prove KPT's wiring only. Unconfirmed against the real package: `function_tool(strict_mode=False)`, `Agent(handoffs=…, handoff_description=…, input_guardrails=…)`, `@input_guardrail` / `GuardrailFunctionOutput` / `InputGuardrailTripwireTriggered`, `OpenAIChatCompletionsModel`, `Runner.run(max_turns=…)`, `result.last_agent`, Gemini's OpenAI-compatible endpoint, and live-provider behaviour. The guardrail builder fails soft and the Python pre-check refuses owner questions regardless.
* Not browser-tested: the widget changes.
