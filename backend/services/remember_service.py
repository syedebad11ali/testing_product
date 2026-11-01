""""Remember me": long-lived login tokens using the selector + validator pattern. No Flask imports.

The cookie value is ``<selector>.<validator>``. The database holds the selector and only a SHA-256 of the
validator, so a database leak cannot be replayed. Every successful use **rotates** the token (new
validator, new selector). Rotated rows are kept until they expire so that *re-presenting an old token*
-- the sign of a stolen cookie -- is detectable: that revokes every remember token and session of the
user. A short grace window (``ROTATION_GRACE_S``) treats two parallel requests from the same browser
as a race, not theft. Admin accounts never receive a remember token (stricter than a short timeout).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import uuid
from dataclasses import dataclass

from backend.services.moderation_service import resolve_status
from backend.config import Settings
from backend.db import Database

ROTATION_GRACE_S = 10
_VALUE = re.compile(r"([A-Za-z0-9_-]{8,32})\.([A-Za-z0-9_-]{20,64})")


def _hash(validator: str) -> str:
    return hashlib.sha256(validator.encode()).hexdigest()


def device_label(user_agent: str) -> str:
    """A coarse, human label such as "Chrome on Windows" (never the raw user agent)."""
    ua = user_agent or ""
    browser = next((n for p, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if p in ua), "Browser")
    system = next((n for p, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"), ("Mac OS X", "macOS"), ("Linux", "Linux")) if p in ua), "unknown device")
    return f"{browser} on {system}"


@dataclass
class Redeemed:
    user_id: str
    cookie_value: str   # the rotated value to send back
    token_id: str


class RememberService:
    def __init__(self, db: Database, settings: Settings, audit=None) -> None:
        self.db, self.s, self.audit = db, settings, audit
        self.days_s = max(1, settings.remember_days) * 86400

    # -- issue ------------------------------------------------------------------------------------
    def _insert(self, user_id: str, label: str, now: int) -> tuple[str, str]:
        selector, validator = secrets.token_urlsafe(12), secrets.token_urlsafe(32)
        token_id = uuid.uuid4().hex
        self.db.execute(
            "INSERT INTO remember_tokens (id, selector, validator_hash, user_id, device_label, created_at, last_used_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (token_id, selector, _hash(validator), user_id, label[:60], now, now, now + self.days_s))
        return token_id, f"{selector}.{validator}"

    def issue(self, user: dict, user_agent: str) -> str | None:
        """Cookie value for a new token, or ``None`` when this user may not have one (admins)."""
        if user.get("role") == "admin" or user.get("must_change_password"):
            return None
        return self._insert(user["id"], device_label(user_agent), int(time.time()))[1]

    # -- redeem -----------------------------------------------------------------------------------
    def redeem(self, raw: str, user_agent: str) -> Redeemed | None:
        """Validate and rotate. ``None`` for anything invalid; reuse of a rotated token revokes everything."""
        m = _VALUE.fullmatch(raw or "")
        if not m:
            return None
        selector, validator = m.groups()
        row = self.db.one("SELECT * FROM remember_tokens WHERE selector = ?", (selector,))
        now = int(time.time())
        if not row or row["revoked_at"] or now > row["expires_at"]:
            return None
        if not hmac.compare_digest(row["validator_hash"], _hash(validator)):
            return None  # right selector, wrong validator: guessing, not reuse of a real token
        if row["rotated_at"]:
            if now - row["rotated_at"] > ROTATION_GRACE_S:
                self.revoke_user(row["user_id"])
                if self.audit:
                    self.audit.admin_action(row["user_id"], "remember_reuse_detected", row["user_id"], "", "all remember tokens and sessions revoked")
            return None
        user = self.db.one("SELECT id, role, status, must_change_password FROM users WHERE id = ?", (row["user_id"],))
        if not user or resolve_status(self.db, user["id"], user["status"]) != "active" or user["role"] == "admin" or user["must_change_password"]:
            return None
        self.db.execute("UPDATE remember_tokens SET rotated_at = ? WHERE id = ? AND rotated_at IS NULL", (now, row["id"]))
        token_id, value = self._insert(row["user_id"], row["device_label"] or device_label(user_agent), now)
        # Keep the original lifetime window sliding from first issue: a rotated token does not extend past it.
        self.db.execute("UPDATE remember_tokens SET expires_at = ?, created_at = ? WHERE id = ?", (row["expires_at"], row["created_at"], token_id))
        return Redeemed(row["user_id"], value, token_id)

    # -- list / revoke ------------------------------------------------------------------------------
    def devices(self, user_id: str, current_selector: str = "") -> list[dict]:
        now = int(time.time())
        rows = self.db.all(
            "SELECT id, selector, device_label, created_at, last_used_at, expires_at FROM remember_tokens "
            "WHERE user_id = ? AND revoked_at IS NULL AND rotated_at IS NULL AND expires_at > ? ORDER BY last_used_at DESC", (user_id, now))
        return [{"id": r["id"], "label": r["device_label"] or "Unknown device", "created_at": r["created_at"],
                 "last_used_at": r["last_used_at"], "expires_at": r["expires_at"], "current": bool(current_selector) and r["selector"] == current_selector}
                for r in rows]

    def revoke_cookie(self, raw: str) -> None:
        """Revoke the token (and its rotated predecessors) behind this device's cookie."""
        m = _VALUE.fullmatch(raw or "")
        if m:
            row = self.db.one("SELECT user_id FROM remember_tokens WHERE selector = ?", (m.group(1),))
            if row and hmac.compare_digest(self.db.one("SELECT validator_hash FROM remember_tokens WHERE selector = ?", (m.group(1),))["validator_hash"], _hash(m.group(2))):
                self.db.execute("UPDATE remember_tokens SET revoked_at = ? WHERE selector = ? AND revoked_at IS NULL", (int(time.time()), m.group(1)))

    def revoke_one(self, user_id: str, token_id: str) -> bool:
        return self.db.execute("UPDATE remember_tokens SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
                               (int(time.time()), token_id, user_id)) > 0

    def revoke_user(self, user_id: str) -> int:
        """Revoke every remember token AND every session of the user (theft response, 'log out everywhere')."""
        now = int(time.time())
        n = self.db.execute("UPDATE remember_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
        self.db.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
        return n
