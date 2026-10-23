"""Gemini-backed answer engine (tool calling + Google Search grounding) with model fallback."""
import logging

from backend.services.prompts import SEARCH_SYSTEM_PROMPT, SYSTEM_PROMPT
from backend.services.tools import make_tools

log = logging.getLogger("chatbot")


class GeminiEngine:
    def __init__(self, settings):
        self.key = settings.gemini_api_key
        self.models = list(settings.gemini_models)
        self.client = None
        if self.key:
            try:
                from google import genai
                from google.genai import types
                self.client = genai.Client(api_key=self.key, http_options=types.HttpOptions(timeout=settings.gemini_timeout_ms))
            except Exception as e:
                log.warning("Gemini unavailable: %s", e)

    @property
    def enabled(self):
        return self.client is not None

    @staticmethod
    def _contents(history, message):
        from google.genai import types
        contents = [types.Content(role=h["role"], parts=[types.Part(text=h["text"])]) for h in history[-12:]]
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
        return contents

    def _generate(self, contents, config):
        last = None
        for model in list(self.models):
            try:
                response = self.client.models.generate_content(model=model, contents=contents, config=config)
                if response.text:
                    self.models = [model] + [name for name in self.models if name != model]
                    return response
                last = RuntimeError(f"{model}: empty response")
            except Exception as e:
                last = e
                if "404" in str(e) or "NOT_FOUND" in str(e):
                    log.warning("Model %s not available, trying next", model)
                    continue
                raise
        if last:
            raise last
        raise RuntimeError("No Gemini models are configured")

    def answer(self, store, history, message):
        from google.genai import types
        tools, calls = make_tools(store)
        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT, tools=tools, temperature=0.2, max_output_tokens=2048,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=6))
        response = self._generate(self._contents(history, message), cfg)
        return response.text.strip(), list(calls)

    def answer_with_search(self, history, message):
        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=SEARCH_SYSTEM_PROMPT,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
            max_output_tokens=2048,
        )
        response = self._generate(self._contents(history, message), config)
        text = response.text.strip()
        sources = []
        for candidate in response.candidates or []:
            metadata = candidate.grounding_metadata
            for chunk in metadata.grounding_chunks if metadata else []:
                web = chunk.web
                if web and web.uri and web.uri not in sources:
                    sources.append(web.uri)
        if sources:
            text += "\n\nSources:\n" + "\n".join(f"- {url}" for url in sources[:5])
        return text

