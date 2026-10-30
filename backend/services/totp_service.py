"""Admin TOTP (RFC 6238 via ``pyotp``) and step-up proofs.

* Secrets are encrypted at rest with Fernet using ``TOTP_ENCRYPTION_KEY``. Missing or invalid key => every TOTP
  operation fails closed (503 ``totp_unavailable``). There is no fallback key and no plaintext storage.
* A secret is ``pending`` until a correct code is confirmed; only ``active`` secrets count.
* Replay protection: the last accepted 30 s time step is stored and a code is accepted only for a strictly newer step
  (compare-and-set in SQL, so two parallel requests cannot both succeed).
* A step-up proof is a random token (only its SHA-256 is stored) bound to the admin, the exact session and an action
  class; it expires quickly and is consumed by the first sensitive action that uses it.
* Secrets, codes and proofs are never logged and never returned by status endpoints.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Callable

try:  # a missing package must disable TOTP (fail closed, 503), not take the whole app (and login) down at import time
    import pyotp
except ImportError:  # pragma: no cover - exercised by tests through ``totp_service.pyotp = None``
    pyotp = None
from cryptography.fernet import Fernet, InvalidToken

from backend.db import Database
from backend.errors import ApiError

STEP_S = 30
VALID_WINDOW = 1  # accept the previous/next 30 s step to tolerate clock drift
ACTION_CLASSES = ("moderation", "role_change", "csv_export")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class TotpService:
    def __init__(self, db: Database, key: str | None, issuer: str, stepup_ttl_s: int = 120, now: Callable[[], float] = time.time) -> None:
        self.db, self._key, self.issuer, self.ttl, self.now = db, key, issuer, stepup_ttl_s, now

    # ---- encryption (fail closed) -------------------------------------------------
    def configured(self) -> bool:
        try:
            self._fernet()
            return True
        except ApiError:
            return False

    def _fernet(self) -> Fernet:
        if pyotp is None:  # every secret operation goes through here, so nothing can run without the library
            raise ApiError("Two-factor authentication is not configured on this server.", 503, "totp_unavailable")
        if not self._key:
            raise ApiError("Two-factor authentication is not configured on this server.", 503, "totp_unavailable")
        try:
            return Fernet(self._key.encode())
        except (ValueError, TypeError):
            raise ApiError("Two-factor authentication is not configured on this server.", 503, "totp_unavailable") from None

    def _secret(self, row: dict) -> str:
        try:
            return self._fernet().decrypt(row["secret_enc"].encode()).decode()
        except InvalidToken:  # key rotated without re-enrolment, or corrupted data
            raise ApiError("Two-factor authentication must be re-enrolled.", 503, "totp_unavailable") from None

    # ---- state ------------------------------------------------------------------------
    def row(self, user_id: str) -> dict | None:
        return self.db.one("SELECT user_id, secret_enc, status, created_at, confirmed_at, last_step FROM admin_totp WHERE user_id = ?", (user_id,))

    def status(self, user_id: str) -> str:
        """``none`` | ``pending`` | ``active``."""
        row = self.row(user_id)
        return row["status"] if row else "none"

    # ---- enrolment ---------------------------------------------------------------------
    def start_enrolment(self, user_id: str, account_label: str) -> dict:
        """Create (or replace) a PENDING secret. Returned once; the caller must not log it."""
        fernet = self._fernet()
        if self.status(user_id) == "active":
            raise ApiError("Two-factor authentication is already active. Disable it first to enrol a new device.", 409, "already_enrolled")
        secret = pyotp.random_base32()
        enc = fernet.encrypt(secret.encode()).decode()
        self.db.execute("DELETE FROM admin_totp WHERE user_id = ? AND status = 'pending'", (user_id,))
        # ON CONFLICT DO NOTHING (SQLite 3.24+ and PostgreSQL): a parallel enrolment start loses cleanly instead of raising a key error
        if self.db.execute("INSERT INTO admin_totp (user_id, secret_enc, status, created_at, last_step) VALUES (?, ?, 'pending', ?, 0) "
                           "ON CONFLICT (user_id) DO NOTHING", (user_id, enc, int(self.now()))) != 1:
            raise ApiError("Enrolment is already being set up. Reload the page and try again.", 409, "enrolment_in_progress")
        return {"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=account_label, issuer_name=self.issuer)}

    def _accept_code(self, row: dict, code: str) -> bool:
        """True and records the time step iff ``code`` is valid for a step newer than the last accepted one."""
        code = (code or "").strip().replace(" ", "")
        if not (code.isdigit() and len(code) == 6):
            return False
        totp = pyotp.TOTP(self._secret(row))
        now = self.now()
        for offset in range(-VALID_WINDOW, VALID_WINDOW + 1):  # library generates each candidate; constant-time compare
            if pyotp.utils.strings_equal(code, totp.at(now, counter_offset=offset)):
                step = int(now // STEP_S) + offset
                # compare-and-set: only the first request for this step wins (replay and race safe)
                return self.db.execute("UPDATE admin_totp SET last_step = ? WHERE user_id = ? AND last_step < ?", (step, row["user_id"], step)) == 1
        return False

    def confirm_enrolment(self, user_id: str, code: str) -> bool:
        row = self.row(user_id)
        if not row or row["status"] != "pending":
            return False
        if not self._accept_code(row, code):
            return False
        self.db.execute("UPDATE admin_totp SET status = 'active', confirmed_at = ? WHERE user_id = ? AND status = 'pending'", (int(self.now()), user_id))
        return True

    def verify_active(self, user_id: str, code: str) -> bool:
        row = self.row(user_id)
        return bool(row and row["status"] == "active" and self._accept_code(row, code))

    def disable(self, user_id: str) -> None:
        self.db.execute("DELETE FROM admin_totp WHERE user_id = ?", (user_id,))
        self.db.execute("DELETE FROM admin_stepups WHERE user_id = ?", (user_id,))

    # ---- step-up proofs -------------------------------------------------------------------
    def issue_proof(self, user_id: str, session_hash: str, action_class: str) -> dict:
        if action_class not in ACTION_CLASSES:
            raise ApiError("Unknown action.", 400, "invalid_action")
        now = int(self.now())
        self.db.execute("DELETE FROM admin_stepups WHERE expires_at < ?", (now - 3600,))  # housekeeping
        token = secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO admin_stepups (id_hash, user_id, session_hash, action_class, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (_hash(token), user_id, session_hash, action_class, now, now + self.ttl))
        return {"proof": token, "expires_in": self.ttl, "action": action_class}

    def consume_proof(self, user_id: str, session_hash: str, action_class: str, token: object) -> None:
        """Atomically marks the proof used. Wrong/expired/used/other-session/other-action all fail identically."""
        if not isinstance(token, str) or not (20 <= len(token) <= 200):
            raise ApiError("Two-factor confirmation is required for this action.", 403, "stepup_required")
        now = int(self.now())
        used = self.db.execute("UPDATE admin_stepups SET used_at = ? WHERE id_hash = ? AND user_id = ? AND session_hash = ? AND action_class = ? "
                               "AND used_at IS NULL AND expires_at >= ?", (now, _hash(token), user_id, session_hash, action_class, now))
        if used != 1:
            raise ApiError("Two-factor confirmation is required for this action.", 403, "stepup_required")
