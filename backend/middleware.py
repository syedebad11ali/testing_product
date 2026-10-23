"""Cross-cutting HTTP concerns: CORS and per-IP rate limiting."""
from __future__ import annotations

from flask import Flask, request

from backend.config import Settings
from backend.errors import ApiError
from backend.security.ratelimit_store import MemoryStore, Store, UpstashStore


def build_store(settings: Settings) -> Store:
    """Shared Redis store when configured (production), otherwise per-process memory."""
    if settings.redis_rest_url and settings.redis_rest_token:
        return UpstashStore(settings.redis_rest_url, settings.redis_rest_token)
    return MemoryStore()


class RateLimiter:
    """Fixed-window limiter on top of a pluggable counter store (memory or Upstash Redis)."""

    def __init__(self, limit: int, window_s: int = 60, store: Store | None = None, name: str = "rl"):
        self.limit, self.window, self.name = limit, window_s, name
        self.store = store or MemoryStore()

    def check(self, key: str) -> None:
        count, retry_after = self.store.hit(f"{self.name}:{key}", self.window)
        if count > self.limit:
            raise ApiError("Too many requests. Please wait a moment.", 429, "rate_limited",
                           headers={"Retry-After": str(retry_after)})


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
