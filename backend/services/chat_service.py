"""Orchestrates one chat turn: greeting -> Gemini (tools / search) -> offline fallback."""
import logging
import threading
from collections import OrderedDict

from backend.records.store import Store
from backend.services.gemini_engine import GeminiEngine
from backend.services.greetings import greeting_reply, is_greeting
from backend.services.grounding import needs_search_grounding
from backend.services.offline_engine import OfflineEngine

log = logging.getLogger("chatbot")

MAX_SESSIONS = 500          # oldest sessions are evicted beyond this
MAX_HISTORY_MESSAGES = 20   # per-session context kept in memory


class ChatService:
    def __init__(self, settings):
        self.store = Store(settings.data_dir, settings.model_path)
        self.gemini = GeminiEngine(settings)
        self.offline = OfflineEngine(self.store)
        self.sessions = OrderedDict()
        self.lock = threading.Lock()

    def _history(self, sid):
        with self.lock:
            h = self.sessions.setdefault(sid, [])
            self.sessions.move_to_end(sid)
            while len(self.sessions) > MAX_SESSIONS:
                self.sessions.popitem(last=False)
            return h

    def reply(self, sid, message):
        history = self._history(sid)
        if is_greeting(message):
            text, source, used = greeting_reply(message), "greeting", False
        else:
            try:
                if needs_search_grounding(self.store, message) and not self.gemini.enabled:
                    text = "Live answers and estimates for areas outside the property records require Gemini. Configure GEMINI_API_KEY in your hosting environment; I can still answer questions using the listed areas."
                    source, used = "offline", False
                elif not self.gemini.enabled:
                    raise RuntimeError("Gemini not configured")
                elif needs_search_grounding(self.store, message):
                    text = self.gemini.answer_with_search(history, message)
                    source, used = "gemini", False
                else:
                    text, calls = self.gemini.answer(self.store, history, message)
                    source, used = "gemini", bool(calls)
            except Exception as e:
                log.warning("Using offline engine: %s", e)
                text, source, used = self.offline.answer(message), "offline", True
        history += [{"role": "user", "text": message}, {"role": "model", "text": text}]
        del history[:-MAX_HISTORY_MESSAGES]
        return {"reply": text, "source": source, "from_data": used}
