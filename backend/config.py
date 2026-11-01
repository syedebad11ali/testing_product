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


def _choice(name: str, allowed: tuple[str, ...], default: str) -> str:
    """Env value restricted to a known set (case-insensitive); anything else falls back to the default."""
    value = (os.getenv(name) or default).strip().lower()
    return value if value in allowed else default


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
    # --- OpenAI Agents SDK engine (opt-in; default keeps the native Gemini engine) -------------
    ai_engine: str = "gemini"                 # "gemini" (default, unchanged) | "agents"
    agents_provider: str = "openai"           # "openai" | "gemini" (Gemini via its OpenAI-compatible endpoint)
    openai_api_key: str | None = None
    openai_models: tuple[str, ...] = ("gpt-4o-mini",)   # comma-separated in OPENAI_MODEL = fallback order
    agents_timeout_s: int = 20
    agents_max_turns: int = 6
    agents_mode: str = "handoffs"             # "handoffs" (triage + specialist agents) | "single" (one agent, all tools)
    ai_order: tuple[str, ...] = ("agents", "gemini")   # engines tried first-to-last; each is skipped unless enabled
    # --- http ---------------------------------------------------------------
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)
    rate_limit_per_min: int = 20
    max_message_len: int = 1000
    verify_rate_limit_per_min: int = 10
    port: int = 5000
    trusted_proxy_hops: int = 0
    redis_rest_url: str | None = None
    redis_rest_token: str | None = None
    contact_whatsapp: str | None = None
    contact_email: str | None = None
    totp_encryption_key: str | None = None   # Fernet key; missing/invalid => TOTP fails closed
    admin_totp_required: bool = False        # enforce only after recovery is set up and tested (docs/ADMIN.md)
    totp_issuer: str = "Karachi Property Trust"
    stepup_ttl_s: int = 120
    # --- auth / sessions (phase 3-4) ------------------------------------------
    app_env: str = "development"
    database_url: str | None = None          # postgresql://... in production; empty = local SQLite file
    local_db_path: str = str(ROOT_DIR / ".local" / "kpt.sqlite3")  # dev/test only; production uses DATABASE_URL
    cookie_secure: bool = False              # True => Secure + __Host- cookie names (production / https)
    admin_001_password: str | None = None    # seeds the built-in admin_001 account (hash only is stored)
    dev_admin_password: str | None = None    # DEV ONLY: password for the "Skip login" admin__01 shortcut; empty = shortcut can never open /admin
    ip_hash_salt: str = "dev-only-salt"      # HMAC key for the truncated IP hash stored in events
    session_idle_s: int = 1800
    session_absolute_s: int = 43200
    admin_session_idle_s: int = 900
    admin_session_absolute_s: int = 7200
    guest_session_idle_s: int = 900          # guests: short, non-renewable-by-remember sessions
    guest_session_absolute_s: int = 7200
    guest_max_active_per_ip: int = 10        # simultaneously valid guest sessions per (hashed) IP
    guest_cleanup_batch: int = 200           # max expired guest rows removed per cleanup call (bounded work)
    login_rate_limit_per_min: int = 10
    message_rate_limit_per_min: int = 20
    message_retention_days: int = 0   # 0 = retention disabled (no period approved yet)
    report_retention_days: int = 730
    lockout_threshold: int = 5               # failures per (account, IP) inside the window
    lockout_window_s: int = 900
    app_base_url: str = "http://localhost:5000"  # used in emailed links; set to the public https URL in production
    resend_api_key: str | None = None        # email provider (Resend). Empty = password-reset email disabled
    mail_from: str | None = None             # e.g. "Karachi Property Trust <no-reply@yourdomain>"
    google_client_id: str | None = None      # public OAuth Web client id; empty = Google sign-in disabled (503)
    admin_emails: tuple[str, ...] = field(default_factory=tuple)  # promoted to admin ONLY via Google-verified email
    remember_days: int = 30                  # lifetime of a 'Remember me' token (admins never get one)
    chat_cookie_days: int = 7                # lifetime of the anonymous chat-continuity cookie
    # --- static site --------------------------------------------------------
    frontend_dir: Path = ROOT_DIR / "frontend"
    assets_dir: Path = ROOT_DIR / "public" / "assets"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def dev_skip_enabled(self) -> bool:
        """The troll \"Skip login\" button exists only outside production (Vercel sets APP_ENV=production)."""
        return not self.is_production

    @classmethod
    def from_env(cls) -> "Settings":
        app_env = (os.getenv("APP_ENV") or ("production" if os.getenv("VERCEL") else "development")).lower()
        return cls(
            app_env=app_env,
            local_db_path=os.getenv("LOCAL_DB_PATH") or str(ROOT_DIR / ".local" / "kpt.sqlite3"),
            database_url=os.getenv("DATABASE_URL") or None,
            cookie_secure=(os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"}) if os.getenv("COOKIE_SECURE") else app_env == "production",
            admin_001_password=os.getenv("ADMIN_001_PASSWORD") or None,
            dev_admin_password=os.getenv("DEV_ADMIN_PASSWORD") or None,
            ip_hash_salt=os.getenv("IP_HASH_SALT") or "dev-only-salt",
            session_idle_s=_int("SESSION_IDLE_S", 1800),
            session_absolute_s=_int("SESSION_ABSOLUTE_S", 43200),
            guest_session_idle_s=_int("GUEST_SESSION_IDLE_S", 900),
            guest_session_absolute_s=_int("GUEST_SESSION_ABSOLUTE_S", 7200),
            guest_max_active_per_ip=_int("GUEST_MAX_ACTIVE_PER_IP", 10),
            login_rate_limit_per_min=_int("LOGIN_RATE_LIMIT_PER_MIN", 10),
            message_rate_limit_per_min=_int("MESSAGE_RATE_LIMIT_PER_MIN", 20),
            message_retention_days=_int("MESSAGE_RETENTION_DAYS", 0, minimum=0),
            report_retention_days=_int("REPORT_RETENTION_DAYS", 730, minimum=1),
            lockout_threshold=_int("LOCKOUT_THRESHOLD", 5),
            app_base_url=(os.getenv("APP_BASE_URL") or ("https://" + os.environ["VERCEL_URL"] if os.getenv("VERCEL_URL") else "http://localhost:5000")).rstrip("/"),
            resend_api_key=(os.getenv("RESEND_API_KEY") or "").strip() or None,
            mail_from=(os.getenv("MAIL_FROM") or "").strip() or None,
            google_client_id=(os.getenv("GOOGLE_CLIENT_ID") or "").strip().strip("\"'") or None,
            admin_emails=tuple(e.lower() for e in _list("ADMIN_EMAILS")),
            remember_days=_int("REMEMBER_DAYS", 30),
            chat_cookie_days=_int("CHAT_COOKIE_DAYS", 7),
            data_dir=Path(os.getenv("DATA_DIR") or BACKEND_DIR / "datasets"),
            model_path=Path(os.getenv("MODEL_PATH") or BACKEND_DIR / "ml" / "price_model.joblib"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None,
            gemini_models=_list("GEMINI_MODEL", DEFAULT_GEMINI_MODELS) or tuple(DEFAULT_GEMINI_MODELS.split(",")),
            gemini_timeout_ms=_int("GEMINI_TIMEOUT_MS", 20000),
            ai_engine=_choice("AI_ENGINE", ("gemini", "agents"), "gemini"),
            agents_provider=_choice("AGENTS_PROVIDER", ("openai", "gemini"), "openai"),
            openai_api_key=(os.getenv("OPENAI_API_KEY") or "").strip() or None,
            openai_models=_list("OPENAI_MODEL", "gpt-4o-mini") or ("gpt-4o-mini",),
            agents_timeout_s=_int("AGENTS_TIMEOUT_S", 20),
            agents_max_turns=_int("AGENTS_MAX_TURNS", 6),
            agents_mode=_choice("AGENTS_MODE", ("handoffs", "single"), "handoffs"),
            ai_order=tuple(n for n in _list("AI_ORDER", "agents,gemini") if n in ("agents", "gemini")) or ("agents", "gemini"),
            allowed_origins=_list("ALLOWED_ORIGINS"),
            rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 20),
            max_message_len=_int("MAX_MESSAGE_LEN", 1000),
            verify_rate_limit_per_min=_int("VERIFY_RATE_LIMIT_PER_MIN", 10),
            port=_int("PORT", 5000),
            # Vercel puts exactly one proxy in front of the function; locally there is none.
            trusted_proxy_hops=_int("TRUSTED_PROXY_HOPS", 1 if os.getenv("VERCEL") else 0, minimum=0),
            redis_rest_url=os.getenv("UPSTASH_REDIS_REST_URL") or None,
            redis_rest_token=os.getenv("UPSTASH_REDIS_REST_TOKEN") or None,
            contact_whatsapp=os.getenv("CONTACT_WHATSAPP") or None,
            contact_email=os.getenv("CONTACT_EMAIL") or None,
            totp_encryption_key=os.getenv("TOTP_ENCRYPTION_KEY") or None,
            admin_totp_required=os.getenv("ADMIN_TOTP_REQUIRED", "0").strip().lower() in ("1", "true", "yes"),
            totp_issuer=os.getenv("TOTP_ISSUER", "Karachi Property Trust")[:60],
            stepup_ttl_s=_int("STEPUP_TTL_S", 120),
        )
