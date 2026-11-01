"""Forgot-password: single-use, hashed, 15-minute reset tokens. No Flask imports.

* ``request_reset`` always looks the same to the caller (no account enumeration); only the email differs.
* Only the SHA-256 of the token is stored; the token itself exists only in the email link.
* ``reset`` consumes the token atomically, sets the new password, and signs the user out everywhere.
* ``admin_001`` (has a username) is excluded: its password is managed through the environment/admin flow.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from typing import Callable

from backend.config import Settings
from backend.db import Database
from backend.errors import ApiError
from backend.security import passwords
from backend.services.audit_service import AuditService
from backend.services.session_service import SessionService

log = logging.getLogger("kpt.reset")
TTL_S = 900


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordResetService:
    def __init__(self, db: Database, settings: Settings, sessions: SessionService, audit: AuditService,
                 send: Callable[[str, str, str], bool], mail_enabled: bool) -> None:
        self.db, self.s, self.sessions, self.audit, self._send, self.mail_enabled = db, settings, sessions, audit, send, mail_enabled

    def request_reset(self, email: str, ip_hash: str, ua: str) -> None:
        email = email.strip().lower()[:254]
        row = self.db.one("SELECT * FROM users WHERE email = ?", (email,))
        if not row or row["status"] != "active" or row["username"]:
            self.audit.login_event(identifier=email, method="reset", success=False, ip_hash=ip_hash, user_agent=ua, reason="reset_no_account")
            return
        token, now = secrets.token_urlsafe(32), int(time.time())
        self.db.execute("DELETE FROM password_resets WHERE user_id = ? OR expires_at < ?", (row["id"], now))  # one live token per user
        self.db.execute("INSERT INTO password_resets (id_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                        (_hash(token), row["id"], now, now + TTL_S))
        link = f"{self.s.app_base_url.rstrip('/')}/login?reset={token}"
        self.audit.login_event(identifier=email, method="reset", success=True, ip_hash=ip_hash, user_agent=ua, user_id=row["id"], reason="reset_requested")
        if self.mail_enabled:
            self._send(email, "Reset your Karachi Property Trust password",
                       f"Open this link within 15 minutes to choose a new password:\n\n{link}\n\n"
                       "If you did not ask for this, ignore this email; your password has not changed.")
        elif not self.s.is_production:
            log.info("password reset link (dev only, email not configured): %s", link)  # never logged in production

    def reset(self, token: str, new_password: str, ip_hash: str) -> None:
        bad = ApiError("This reset link is invalid or has expired. Request a new one.", 400, "reset_invalid")
        now = int(time.time())
        row = self.db.one("SELECT * FROM password_resets WHERE id_hash = ?", (_hash(token),))
        if not row or row["used_at"] is not None or row["expires_at"] < now:
            raise bad
        user = self.db.one("SELECT * FROM users WHERE id = ?", (row["user_id"],))
        if not user or user["status"] != "active" or user["username"]:
            raise bad
        problems = passwords.policy_problems(new_password, email=user["email"] or "")
        if problems:
            raise ApiError(" ".join(problems), 400, "weak_password")  # token stays usable: the user can retry
        if self.db.execute("UPDATE password_resets SET used_at = ? WHERE id_hash = ? AND used_at IS NULL", (now, row["id_hash"])) != 1:
            raise bad  # lost a race with another use of the same token
        self.db.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?", (passwords.hash_password(new_password), user["id"]))
        self.sessions.revoke_user(user["id"])
        self.audit.admin_action(user["id"], "password_reset", user["id"], ip_hash)
