"""Restricted guest sessions ("Continue as guest").

A guest is a real server-side session for a throwaway ``users`` row (``role='guest'``, no email, no username, no password
hash, so it can never be used with password login, Google linking or password reset). Guests are rejected by
``login_required`` on every route that does not opt in, are invisible to admin lists/exports/session views, never get a
remember-me token, and have short idle/absolute lifetimes. Expired guest rows are removed in bounded batches.
"""
from __future__ import annotations

import time
import uuid

from backend.config import Settings
from backend.db import Database
from backend.errors import ApiError


class GuestService:
    def __init__(self, db: Database, settings: Settings, sessions) -> None:
        self.db, self.s, self.sessions = db, settings, sessions

    def active_for_ip(self, ip_hash: str, now: int | None = None) -> int:
        now = now or int(time.time())
        return self.db.one(
            "SELECT COUNT(*) AS n FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.role = 'guest' AND s.ip_hash = ? "
            "AND s.revoked_at IS NULL AND s.expires_at > ? AND s.last_seen_at + s.idle_s >= ?", (ip_hash, now, now))["n"]

    def create(self, ip_hash: str, user_agent: str) -> tuple[dict, str]:
        """New guest user + session. Raises 429 when this network already holds too many live guest sessions."""
        self.cleanup()
        if self.active_for_ip(ip_hash) >= self.s.guest_max_active_per_ip:
            raise ApiError("Too many guest sessions from this network. Please try again later or create an account.", 429, "guest_limit")
        now = int(time.time())
        user = {"id": uuid.uuid4().hex, "email": None, "username": None, "name": "Guest", "role": "guest", "status": "active",
                "must_change_password": 0}  # nosec B105 - a 0/1 flag, not a secret
        self.db.execute(
            "INSERT INTO users (id, email, username, name, password_hash, role, status, method, must_change_password, created_at, last_login_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (user["id"], None, None, "Guest", None, "guest", "active", "guest", 0, now, now))
        return user, self.sessions.create(user, ip_hash, user_agent)

    def cleanup(self, limit: int | None = None) -> int:
        """Delete guest users (and their sessions) that have no live session. At most ``limit`` rows per call."""
        limit, now = limit or self.s.guest_cleanup_batch, int(time.time())
        rows = self.db.all(
            "SELECT u.id FROM users u WHERE u.role = 'guest' AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.user_id = u.id "
            "AND s.revoked_at IS NULL AND s.expires_at > ? AND s.last_seen_at + s.idle_s >= ?) ORDER BY u.created_at LIMIT ?", (now, now, limit))
        return self._delete([r["id"] for r in rows])

    def discard(self, user_id: str) -> int:
        """Guest logged out: revoke and remove the row now (no-op for non-guests)."""
        self.sessions.revoke_user(user_id)
        return self._delete([user_id])

    def _delete(self, ids: list[str]) -> int:
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        self.db.execute(f"DELETE FROM sessions WHERE user_id IN ({marks}) AND user_id IN (SELECT id FROM users WHERE role = 'guest')", tuple(ids))  # noqa: S608  # nosec B608 - only ? placeholders are interpolated
        return self.db.execute(f"DELETE FROM users WHERE role = 'guest' AND id IN ({marks})", tuple(ids))  # noqa: S608  # nosec B608 - only ? placeholders are interpolated
