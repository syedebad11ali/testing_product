"""Cross-cutting HTTP concerns: CORS and per-IP rate limiting."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from flask import Flask, request

from backend.config import Settings
from backend.errors import ApiError


class RateLimiter:
    """Sliding-window limiter, in-memory (per warm instance). Thread-safe and self-pruning."""

    def __init__(self, limit: int, window_s: int = 60):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise ApiError("Too many messages. Please wait a moment.", 429, "rate_limited")
            q.append(now)
            if len(self._hits) > 5000:  # drop idle keys so the dict cannot grow without bound
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]


def register_cors(app: Flask, settings: Settings) -> None:
    allowed = set(settings.allowed_origins)

    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin")
        if origin and ("*" in allowed or origin in allowed):
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
            resp.headers["Vary"] = "Origin"
        return resp
