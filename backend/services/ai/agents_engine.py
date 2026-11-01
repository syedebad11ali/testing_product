"""OpenAI Agents SDK answer engine (opt-in: AI_ENGINE=agents).

Same contract as ``GeminiEngine`` so ``ChatService`` can use either: ``enabled`` and
``answer(store, history, message) -> (text, tool_names_used)``. It reuses the existing, owner-safe
``make_tools`` functions as SDK function tools and the existing ``SYSTEM_PROMPT``. Provider is OpenAI, or
Gemini through its OpenAI-compatible endpoint, both via ``AsyncOpenAI``.

Resilience (adapted from the reference project's OpenAIEngine): a model list is tried in order; a "busy" error is
retried once; an auth error stops at once (no point trying other models); the last error is kept, redacted, for the
admin-only health detail. ``agents`` / ``openai`` are imported lazily: when missing, or no key is set, ``enabled`` is
False and the chat keeps using Gemini / offline. Tracing is disabled so chat text is not uploaded anywhere.
"""
from __future__ import annotations

import asyncio
import logging
import time

from backend.services.ai.errors import classify_error, redact
from backend.services.ai.guardrails import OWNER_REFUSAL, asks_for_owner_details
from backend.services.prompts import SYSTEM_PROMPT
from backend.services.tools import make_tools

log = logging.getLogger("chatbot")

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
HISTORY_TURNS = 12
# This path has no web search (live questions are routed to native Gemini before reaching it), so the model must not invent live data.
NO_LIVE_NOTE = ("\n16. You have no live web access. For live questions (weather, news, today's market) say you cannot check "
                "live data and answer only what you can from the property tools or general knowledge.")


# Specialist agents for AGENTS_MODE=handoffs: (name, when-to-hand-off description, tools it may use, role instructions).
# They map onto the router's specialists (Price Estimator / Market Analyst / Property Finder); each only gets the tools it needs.
SPECIALIST_AGENTS = (
    ("Price Estimator", "Estimates a property price or a price forecast from area, property type, block and rooms.",
     ("predict_price", "market_stats"),
     "You are the Price Estimator. Use predict_price for any estimate and market_stats for supporting figures. "
     "If the area or property type is missing, ask for it instead of guessing."),
    ("Market Analyst", "Compares areas or property types and reports dataset statistics: medians, averages, counts, coverage.",
     ("market_stats", "dataset_overview"),
     "You are the Market Analyst. Use market_stats for comparisons and rankings and dataset_overview for counts and coverage."),
    ("Property Finder", "Searches listings by area, type, block, budget or rooms, or looks up one property by its ID.",
     ("search_properties", "get_property"),
     "You are the Property Finder. Use search_properties to find listings and get_property for an ID. Show at most five results."),
)
TRIAGE_NAME = "KPT Property Assistant"
TRIAGE_NOTE = ("\n\nYou are the front desk. Answer simple questions yourself (dataset_overview covers what data exists). "
               "Hand a price estimate to Price Estimator, comparisons and statistics to Market Analyst, and finding listings or "
               "looking up an ID to Property Finder.")


def to_input(history, message) -> list[dict]:
    """Session history (roles 'user'/'model', key 'text') -> Agents SDK input items (roles 'user'/'assistant')."""
    items = []
    for h in list(history)[-HISTORY_TURNS:]:
        text = h.get("text") if isinstance(h, dict) else None
        if not text:
            continue
        items.append({"role": "assistant" if h.get("role") == "model" else "user", "content": str(text)})
    items.append({"role": "user", "content": message})
    return items


class AgentsEngine:
    def __init__(self, settings):
        self.settings = settings
        self.provider = settings.agents_provider
        self.models: list[str] = []
        self.disabled_reason: str | None = None
        self.last_error: str | None = None
        self._sdk = None
        self._client = None
        self._key_present = False
        if settings.ai_engine != "agents":
            self.disabled_reason = "not_selected"
            return
        if self.provider == "gemini":
            key, base_url, models = settings.gemini_api_key, GEMINI_OPENAI_BASE_URL, list(settings.gemini_models)
        else:
            key, base_url, models = settings.openai_api_key, None, list(settings.openai_models)
        self._key_present = bool(key)
        if not key or not models:
            self.disabled_reason = "no_key"
            log.info("Agents engine off: no API key/model for provider %s", self.provider)
            return
        try:
            import agents  # noqa: PLC0415 - optional dependency, imported lazily
            from openai import AsyncOpenAI  # noqa: PLC0415

            self._client = AsyncOpenAI(api_key=key, base_url=base_url, timeout=settings.agents_timeout_s)
            agents.set_tracing_disabled(True)
            self._sdk, self.models = agents, models
        except Exception as e:  # noqa: BLE001 - missing package, bad version, bad config
            self.disabled_reason = "client_error"
            self.last_error = f"client_error: {type(e).__name__}: {redact(e)[:200]}"
            log.warning("Agents SDK unavailable: %s", redact(e))

    @property
    def enabled(self) -> bool:
        return self._sdk is not None and self._client is not None and bool(self.models)

    @property
    def model_name(self) -> str:
        return self.models[0] if self.models else ""

    def status(self) -> dict:
        """Safe for the admin-only health detail: never includes a key, and last_error is redacted."""
        return {"enabled": self.enabled, "provider": self.provider, "key_present": self._key_present,
                "models": list(self.models), "disabled_reason": self.disabled_reason, "last_error": self.last_error}

    def _tool(self, fn):
        try:
            return self._sdk.function_tool(fn, strict_mode=False)   # tool args have defaults; relaxed schema
        except TypeError:                                            # older SDKs without strict_mode
            return self._sdk.function_tool(fn)

    def _guardrails(self):
        """SDK-native input guardrail (runs alongside the model call on the first agent). Fails soft: the Python
        pre-check in ``answer`` already guarantees the refusal, and the store holds no owner data in the first place."""
        sdk = self._sdk
        try:
            @sdk.input_guardrail
            async def owner_privacy(ctx, agent, user_input):
                text = user_input if isinstance(user_input, str) else " ".join(
                    str(i.get("content", "")) for i in user_input if isinstance(i, dict) and i.get("role") == "user")
                hit = asks_for_owner_details(text)
                return sdk.GuardrailFunctionOutput(output_info={"owner_request": hit}, tripwire_triggered=hit)
            return [owner_privacy]
        except Exception as e:  # noqa: BLE001
            log.warning("Agents guardrail unavailable: %s", redact(e))
            return []

    def _build_agent(self, model, tools_by_name):
        sdk = self._sdk
        base = SYSTEM_PROMPT + NO_LIVE_NOTE
        common = {"model": model, "model_settings": sdk.ModelSettings(temperature=0.2, max_tokens=2048)}
        guards = self._guardrails()
        if self.settings.agents_mode != "handoffs":
            return sdk.Agent(name=TRIAGE_NAME, instructions=base, tools=list(tools_by_name.values()), input_guardrails=guards, **common)
        specialists = [sdk.Agent(name=name, handoff_description=desc, instructions=f"{base}\n\n{role}",
                                 tools=[tools_by_name[t] for t in tools if t in tools_by_name], **common)
                       for name, desc, tools, role in SPECIALIST_AGENTS]
        front_tools = [tools_by_name["dataset_overview"]] if "dataset_overview" in tools_by_name else []
        return sdk.Agent(name=TRIAGE_NAME, instructions=base + TRIAGE_NOTE, tools=front_tools, handoffs=specialists,
                         input_guardrails=guards, **common)

    def _run(self, model_name, store, history, message):
        sdk = self._sdk
        funcs, calls = make_tools(store)
        model = sdk.OpenAIChatCompletionsModel(model=model_name, openai_client=self._client)
        agent = self._build_agent(model, {f.__name__: self._tool(f) for f in funcs})
        # A fresh event loop per call: Flask serves requests on worker threads that have none.
        result = asyncio.run(sdk.Runner.run(agent, to_input(history, message), max_turns=self.settings.agents_max_turns))
        text = str(result.final_output or "").strip()
        if not text:
            raise RuntimeError(f"{model_name}: empty answer")
        last = getattr(getattr(result, "last_agent", None), "name", None)
        if last:
            log.info("Agents answered via %s (tools used: %s)", last, ", ".join(calls) or "none")
        return text, list(calls)

    def answer(self, store, history, message):
        if asks_for_owner_details(message):          # deterministic refusal, no model call
            return OWNER_REFUSAL, []
        tripwire = getattr(self._sdk, "InputGuardrailTripwireTriggered", None)
        last = None
        for model in list(self.models):
            for attempt in (1, 2):
                try:
                    out = self._run(model, store, history, message)
                    self.models = [model] + [m for m in self.models if m != model]   # remember the one that worked
                    self.last_error = None
                    return out
                except Exception as e:  # noqa: BLE001
                    if tripwire and isinstance(e, tripwire):      # the SDK guardrail stopped the request
                        return OWNER_REFUSAL, []
                    last, kind = e, classify_error(e)
                    self.last_error = f"{kind} ({model}): {type(e).__name__}: {redact(e)[:200]}"
                    log.warning("Agents call failed [%s] model=%s attempt=%d: %s", kind, model, attempt, redact(e))
                    if kind == "auth":
                        raise
                    if kind == "busy" and attempt == 1:
                        time.sleep(1.0)
                        continue
                    break
        raise last or RuntimeError("No models are configured")
