"""Google sign-in: server-issued nonces and server-side ID-token verification. No Flask imports.

The browser (Google Identity Services) only ever hands us a signed ID token. Nothing it says about
identity is trusted until ``verify`` has checked signature (via Google's public certs), audience,
issuer, expiry, the single-use nonce we issued, and ``email_verified``.

``verifier`` is injectable so tests run without network; the default one lazily imports ``google-auth``
(declared in pyproject.toml) so the rest of the app works when the package is not installed.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Callable

from backend.config import Settings
from backend.db import Database
from backend.errors import ApiError

ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
NONCE_TTL_S = 600


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str


def _default_verifier(credential: str, client_id: str) -> dict:
    """Signature + aud + exp check by google-auth (fetches Google's certs over HTTPS)."""
    try:
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token
    except ImportError as exc:  # package not installed in this environment
        raise ApiError("Google sign-in is temporarily unavailable.", 503, "google_unavailable") from exc
    return id_token.verify_oauth2_token(credential, g_requests.Request(), client_id)


class GoogleOAuth:
    def __init__(self, db: Database, settings: Settings, verifier: Callable[[str, str], dict] | None = None) -> None:
        self.db, self.s, self._verifier = db, settings, verifier or _default_verifier

    @property
    def configured(self) -> bool:
        return bool(self.s.google_client_id)

    @staticmethod
    def _hash(nonce: str) -> str:
        return hashlib.sha256(nonce.encode()).hexdigest()

    def issue_nonce(self) -> str:
        nonce = secrets.token_urlsafe(24)
        now = int(time.time())
        self.db.execute("DELETE FROM auth_nonces WHERE created_at < ?", (now - NONCE_TTL_S * 6,))  # housekeeping
        self.db.execute("INSERT INTO auth_nonces (id_hash, created_at) VALUES (?, ?)", (self._hash(nonce), now))
        return nonce

    def _consume_nonce(self, nonce: str) -> bool:
        """Single use, atomic: only the first caller within the TTL flips ``used_at``."""
        now = int(time.time())
        return self.db.execute("UPDATE auth_nonces SET used_at = ? WHERE id_hash = ? AND used_at IS NULL AND created_at > ?",
                               (now, self._hash(nonce), now - NONCE_TTL_S)) == 1

    def verify(self, credential: str) -> GoogleIdentity:
        if not self.configured:
            raise ApiError("Google sign-in is not configured.", 503, "google_not_configured")
        fail = ApiError("Google sign-in failed. Please try again.", 401, "google_invalid")
        try:
            claims = self._verifier(credential, self.s.google_client_id)
        except ApiError:
            raise
        except Exception:  # noqa: BLE001 - any verification failure is the same generic 401
            raise fail from None
        # Defence in depth: re-check what the library checked, plus nonce and email_verified.
        if not isinstance(claims, dict) or claims.get("aud") != self.s.google_client_id or claims.get("iss") not in ISSUERS:
            raise fail
        if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < time.time():
            raise fail
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or not self._consume_nonce(nonce):
            raise fail
        email, sub = claims.get("email"), claims.get("sub")
        if claims.get("email_verified") is not True or not isinstance(email, str) or not isinstance(sub, str) or not sub:
            raise ApiError("Your Google email address is not verified.", 401, "google_unverified")
        name = claims.get("name") if isinstance(claims.get("name"), str) and claims["name"].strip() else email.split("@")[0]
        return GoogleIdentity(sub=sub, email=email.strip().lower(), name=" ".join(name.split())[:80])
