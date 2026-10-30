"""Application factory.

* Local:   ``python -m backend.app``  (serves the site + API on http://localhost:5000)
* Vercel:  entrypoint ``backend.app:app`` (see pyproject.toml)
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field

from dotenv import load_dotenv
from flask import Flask

from backend.api import register_api
from backend.config import ROOT_DIR, Settings
from backend.errors import ApiError, register_error_handlers
from backend.middleware import RateLimiter, build_store, register_cors
from backend.security.csrf import register_csrf
from backend.security.guards import register_session_cookies
from backend.security.headers import register_security_headers
from werkzeug.middleware.proxy_fix import ProxyFix
from backend.web import register_web


@dataclass
class Container:
    """Holds app-wide singletons. The chat service is built lazily (first request / health
    check) so importing the app never touches the model, the CSVs or Gemini."""

    settings: Settings
    rate_limiter: RateLimiter
    verify_limiter: RateLimiter
    auth_limiter: RateLimiter
    _service: object = None
    _verification: object = None
    _db: object = None
    _audit: object = None
    _sessions: object = None
    _auth: object = None
    _google: object = None
    _reset: object = None
    _remember: object = None
    _guests: object = None
    _prefs: object = None
    _moderation: object = None
    _messaging: object = None
    _msg_limiter: object = None
    mail_sender: object = None  # tests inject a fake send(to, subject, text) -> bool
    google_verifier: object = None  # tests inject a fake; None = real google-auth
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def chat_service(self):
        if self._service is None:
            with self._lock:
                if self._service is None:
                    from backend.services.chat_service import ChatService
                    self._service = ChatService(self.settings)
        return self._service

    def database(self):
        """Lazy DB (migrations + admin_001 seed on first use). Production without DATABASE_URL = auth unavailable."""
        if self._db is None:
            with self._lock:
                if self._db is None:
                    if self.settings.is_production and not self.settings.database_url:
                        raise ApiError("Accounts are temporarily unavailable.", 503, "auth_unavailable")
                    from backend.db import open_database
                    from backend.db.seed import seed_admin
                    db = open_database(self.settings.database_url, local_path=self.settings.local_db_path)
                    seed_admin(db, self.settings)
                    self._db = db
        return self._db

    def audit(self):
        if self._audit is None:
            from backend.services.audit_service import AuditService
            self._audit = AuditService(self.database(), self.settings.ip_hash_salt)
        return self._audit

    def sessions(self):
        if self._sessions is None:
            from backend.services.session_service import SessionService
            self._sessions = SessionService(self.database(), self.settings)
        return self._sessions

    def auth(self):
        if self._auth is None:
            from backend.services.auth_service import AuthService
            self._auth = AuthService(self.database(), self.settings, self.sessions(), self.audit())
        return self._auth

    def remember(self):
        if self._remember is None:
            from backend.services.remember_service import RememberService
            self._remember = RememberService(self.database(), self.settings, self.audit())
        return self._remember

    def guests(self):
        if self._guests is None:
            from backend.services.guest_service import GuestService
            self._guests = GuestService(self.database(), self.settings, self.sessions())
        return self._guests

    def moderation(self):
        if self._moderation is None:
            from backend.services.moderation_service import ModerationService
            self._moderation = ModerationService(self.database(), self.sessions(), self.audit())
        return self._moderation

    def messaging(self):
        if self._messaging is None:
            from backend.services.messaging_service import MessagingService
            self._messaging = MessagingService(self.database())
        return self._messaging

    def message_limiter(self):
        """Per-user / per-IP limiter for message and listing writes (fail-closed store in production)."""
        if self._msg_limiter is None:
            self._msg_limiter = RateLimiter(self.settings.message_rate_limit_per_min, store=build_store(self.settings, fail_closed=True), name="msg")
        return self._msg_limiter

    def totp(self):
        if getattr(self, "_totp", None) is None:
            from backend.services.totp_service import TotpService
            self._totp = TotpService(self.database(), self.settings.totp_encryption_key, self.settings.totp_issuer, self.settings.stepup_ttl_s)
        return self._totp

    def totp_limiter(self):
        """Failed-code limiter (fail-closed store): 8 attempts / 5 min per admin across enrol, step-up and disable."""
        if getattr(self, "_totp_limiter", None) is None:
            self._totp_limiter = RateLimiter(8, window_s=300, store=build_store(self.settings, fail_closed=True), name="totp")
        return self._totp_limiter

    def prefs(self):
        if self._prefs is None:
            from backend.services.prefs import PrefsService
            self._prefs = PrefsService(self.database())
        return self._prefs

    def chat_store(self):
        """DB-backed chat persistence, or ``None`` when no database is available (chat keeps working)."""
        try:
            from backend.services.chat_store import DbChatStore
            svc = self.chat_service()
            if not hasattr(svc, "chat_store"):
                svc.attach_store(DbChatStore(self.database(), self.settings.chat_cookie_days * 86400))
            return svc.chat_store
        except ApiError:
            return None

    def password_reset(self):
        if self._reset is None:
            from backend.services.mailer import Mailer
            from backend.services.password_reset import PasswordResetService
            mailer = Mailer(self.settings)
            send = lambda to, subj, text: (self.mail_sender or mailer.send)(to, subj, text)  # noqa: E731
            self._reset = PasswordResetService(self.database(), self.settings, self.sessions(), self.audit(), send,
                                               mail_enabled=bool(self.mail_sender) or mailer.enabled)
        return self._reset

    def google(self):
        if self._google is None:
            from backend.services.google_oauth import GoogleOAuth
            # Resolve the verifier per call so a test (or later config) can swap it after construction.
            self._google = GoogleOAuth(self.database(), self.settings, lambda c, i: (self.google_verifier or _real_google_verifier())(c, i))
        return self._google

    def verification_service(self):
        if self._verification is None:
            with self._lock:
                if self._verification is None:
                    from backend.services.verification_service import VerificationService
                    self._verification = VerificationService(self.settings.data_dir)
        return self._verification


def _real_google_verifier():
    from backend.services.google_oauth import _default_verifier
    return _default_verifier


def create_app(settings: Settings | None = None) -> Flask:
    # Local development only: ./.env. On Vercel the variables come from Project Settings.
    load_dotenv(ROOT_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    settings = settings or Settings.from_env()

    app = Flask(__name__, static_folder=None)
    if settings.trusted_proxy_hops:  # make request.remote_addr the real client behind Vercel's proxy
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=settings.trusted_proxy_hops, x_proto=settings.trusted_proxy_hops)
    store = build_store(settings)
    app.extensions["kpt"] = Container(settings, RateLimiter(settings.rate_limit_per_min, store=store, name="chat"),
                                      RateLimiter(settings.verify_rate_limit_per_min, store=store, name="verify"),
                                      RateLimiter(settings.login_rate_limit_per_min, store=build_store(settings, fail_closed=True), name="auth"))
    register_security_headers(app, settings)
    register_error_handlers(app)
    register_csrf(app, settings)
    register_session_cookies(app)
    register_cors(app, settings)
    register_api(app)
    register_web(app, settings)
    return app


app = create_app()

if __name__ == "__main__":
    # Local development server only (production uses the platform WSGI server). Loopback by default, so the
    # dev server is not reachable from the LAN; set KPT_HOST=0.0.0.0 on purpose to test from a phone.
    app.run(host=os.getenv("KPT_HOST", "127.0.0.1"), port=app.extensions["kpt"].settings.port, debug=False)
