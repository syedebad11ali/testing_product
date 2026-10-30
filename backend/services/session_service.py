"""Server-side sessions. The cookie holds a random 256-bit id; only its SHA-256 is stored.

Idle and absolute lifetimes are enforced on every lookup (admins get shorter ones). Creating a
session for a user never reuses an old id, so login always rotates. No Flask imports.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from backend.services.moderation_service import resolve_status
from backend.config import Settings
from backend.db import Database

TOUCH_EVERY_S = 60  # avoid a write on every request


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class SessionService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db, self.s = db, settings

    def create(self, user: dict, ip_hash: str, user_agent: str) -> str:
        """New session id (returned raw, once). Existing sessions of the user stay valid (other devices)."""
        raw, now = secrets.token_urlsafe(32), int(time.time())
        admin, guest = user["role"] == "admin", user["role"] == "guest"
        idle = self.s.admin_session_idle_s if admin else self.s.guest_session_idle_s if guest else self.s.session_idle_s
        absolute = self.s.admin_session_absolute_s if admin else self.s.guest_session_absolute_s if guest else self.s.session_absolute_s
        self.db.execute(
            "INSERT INTO sessions (id_hash, user_id, created_at, last_seen_at, expires_at, idle_s, ip_hash, user_agent) "
            "VALUES (?,?,?,?,?,?,?,?)", (_hash(raw), user["id"], now, now, now + absolute, idle, ip_hash, user_agent[:200]))
        return raw

    def lookup(self, raw: str) -> dict | None:
        """User + session info for a valid cookie value, else ``None`` (expired, revoked, disabled)."""
        if not raw or len(raw) > 100:
            return None
        row = self.db.one(
            "SELECT s.id_hash, s.last_seen_at, s.expires_at, s.idle_s, s.revoked_at, u.id AS user_id, u.name, u.email, "
            "u.username, u.role, u.status, u.must_change_password FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.id_hash = ?", (_hash(raw),))
        now = int(time.time())
        if not row or row["revoked_at"]:
            return None
        row["status"] = resolve_status(self.db, row["user_id"], row["status"])  # expired temporary bans reinstate here
        if row["status"] != "active":
            return None
        if now > row["expires_at"] or now - row["last_seen_at"] > row["idle_s"]:
            return None
        if now - row["last_seen_at"] >= TOUCH_EVERY_S:
            self.db.execute("UPDATE sessions SET last_seen_at = ? WHERE id_hash = ?", (now, row["id_hash"]))
        return row

    def revoke(self, raw: str) -> None:
        self.db.execute("UPDATE sessions SET revoked_at = ? WHERE id_hash = ? AND revoked_at IS NULL", (int(time.time()), _hash(raw)))

    def revoke_user(self, user_id: str, keep_raw: str | None = None) -> int:
        keep = _hash(keep_raw) if keep_raw else ""
        # A password change / reset / disable must also end 'remember me' on every device.
        self.db.execute("UPDATE remember_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (int(time.time()), user_id))
        return self.db.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL AND id_hash <> ?",
                               (int(time.time()), user_id, keep))

    def active_for_admin(self, limit: int = 100) -> list[dict]:
        now = int(time.time())
        return self.db.all(
            "SELECT u.id AS user_id, u.name, u.role, s.created_at, s.last_seen_at, s.ip_hash, s.user_agent FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE u.role <> 'guest' AND s.revoked_at IS NULL AND s.expires_at > ? ORDER BY s.last_seen_at DESC LIMIT ?",
            (now, limit))
