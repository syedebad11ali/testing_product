"""Single place where environment variables are read.

Nothing else in the backend calls ``os.getenv``; every other module receives a
``Settings`` instance. Secrets (``GEMINI_API_KEY``) come only from the environment
(``.env`` locally, Project Settings on Vercel) and are never committed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent

DEFAULT_GEMINI_MODELS = "gemini-3-flash-preview,gemini-2.5-flash"


def _int(name: str, default: int, minimum: int = 1) -> int:
    """Read an int env var; fall back to the default on junk instead of crashing at import time."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _list(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(p.strip() for p in os.getenv(name, default).split(",") if p.strip())


@dataclass(frozen=True)
class Settings:
    # --- data / model -------------------------------------------------------
    data_dir: Path = BACKEND_DIR / "datasets"
    model_path: Path = BACKEND_DIR / "ml" / "price_model.joblib"
    # --- gemini -------------------------------------------------------------
    gemini_api_key: str | None = None
    gemini_models: tuple[str, ...] = tuple(DEFAULT_GEMINI_MODELS.split(","))
    gemini_timeout_ms: int = 20000
    # --- http ---------------------------------------------------------------
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)
    rate_limit_per_min: int = 20
    max_message_len: int = 1000
    verify_rate_limit_per_min: int = 10
    port: int = 5000
    trusted_proxy_hops: int = 0
    redis_rest_url: str | None = None
    redis_rest_token: str | None = None
    health_detail_token: str | None = None
    # --- static site --------------------------------------------------------
    frontend_dir: Path = ROOT_DIR / "frontend"
    assets_dir: Path = ROOT_DIR / "public" / "assets"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.getenv("DATA_DIR") or BACKEND_DIR / "datasets"),
            model_path=Path(os.getenv("MODEL_PATH") or BACKEND_DIR / "ml" / "price_model.joblib"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None,
            gemini_models=_list("GEMINI_MODEL", DEFAULT_GEMINI_MODELS) or tuple(DEFAULT_GEMINI_MODELS.split(",")),
            gemini_timeout_ms=_int("GEMINI_TIMEOUT_MS", 20000),
            allowed_origins=_list("ALLOWED_ORIGINS"),
            rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 20),
            max_message_len=_int("MAX_MESSAGE_LEN", 1000),
            verify_rate_limit_per_min=_int("VERIFY_RATE_LIMIT_PER_MIN", 10),
            port=_int("PORT", 5000),
            # Vercel puts exactly one proxy in front of the function; locally there is none.
            trusted_proxy_hops=_int("TRUSTED_PROXY_HOPS", 1 if os.getenv("VERCEL") else 0, minimum=0),
            redis_rest_url=os.getenv("UPSTASH_REDIS_REST_URL") or None,
            redis_rest_token=os.getenv("UPSTASH_REDIS_REST_TOKEN") or None,
            health_detail_token=os.getenv("HEALTH_DETAIL_TOKEN") or None,
        )
