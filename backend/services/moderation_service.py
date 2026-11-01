"""Bans / suspensions. State lives in ``users.status = 'banned'`` plus an append-only ``user_bans`` history.

Enforcement is central: ``SessionService.lookup``, password / Google login and remember-me redemption all treat any
status other than ``active`` as denied, so no endpoint can forget to check it. ``resolve_status`` lazily reinstates an
expired temporary ban the first time the account is seen afterwards. No Flask imports.
"""
from __future__ import annotations

import time
import uuid

from backend.db import Database
from backend.errors import ApiError

MAX_TEMP_DAYS = 365


def resolve_status(db: Database, user_id: str, status: str) -> str:
    """The effective status: an expired temporary ban becomes ``active`` (and the history row is closed)."""
    if status != "banned":
        return status
    now = int(time.time())
    ban = db.one("SELECT id, expires_at FROM user_bans WHERE user_id = ? AND lifted_at IS NULL ORDER BY created_at DESC LIMIT 1", (user_id,))
    if ban and ban["expires_at"] is not None and ban["expires_at"] <= now:
        db.execute("UPDATE user_bans SET lifted_at = ?, lifted_by = 'system', lift_reason = 'expired' WHERE id = ?", (now, ban["id"]))
        db.execute("UPDATE users SET status = 'active' WHERE id = ? AND status = 'banned'", (user_id,))
        db.execute("INSERT INTO audit_log (id, ts, actor_id, action, target, ip_hash, detail) VALUES (?,?,?,?,?,?,?)",
                   (uuid.uuid4().hex, now, "system", "ban_expired", user_id, "", "temporary ban ended"))
        return "active"
    return "banned"


class ModerationService:
    def __init__(self, db: Database, sessions, audit) -> None:
        self.db, self.sessions, self.audit = db, sessions, audit

    def current(self, user_id: str) -> dict | None:
        row = self.db.one(
            "SELECT b.kind, b.reason, b.created_at, b.expires_at, COALESCE(a.name, b.actor_id) AS actor FROM user_bans b "
            "LEFT JOIN users a ON a.id = b.actor_id WHERE b.user_id = ? AND b.lifted_at IS NULL ORDER BY b.created_at DESC LIMIT 1", (user_id,))
        return row

    def validate_ban_request(self, kind: object, days: object) -> None:
        """Request-shape validation with no side effects. The API calls it BEFORE consuming a one-time step-up proof, so a typo
        never wastes a two-factor code (codes are replay-protected per 30 s step). State checks (already banned) stay after
        the proof on purpose: authorization ordering is unchanged."""
        if kind not in ("temporary", "permanent"):
            raise ApiError("kind must be 'temporary' or 'permanent'.", 400, "invalid_kind")
        if kind == "temporary" and not (isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= MAX_TEMP_DAYS):
            raise ApiError(f"days must be between 1 and {MAX_TEMP_DAYS} for a temporary suspension.", 400, "invalid_days")

    def ban(self, actor_id: str, target: dict, kind: str, reason: str, days: int | None, ip_hash: str) -> dict:
        self.validate_ban_request(kind, days)
        if target["status"] == "banned" and resolve_status(self.db, target["id"], "banned") == "banned":
            raise ApiError("This account is already banned or suspended.", 409, "already_banned")
        now = int(time.time())
        expires = now + days * 86400 if kind == "temporary" else None
        # Audit first: if the audit write fails the request fails and no ban is applied.
        self.audit.admin_action(actor_id, f"user_{'suspended' if kind == 'temporary' else 'banned'}", target["id"], ip_hash,
                                f"{kind}{f' {days}d' if days else ''}: {reason}"[:200])
        self.db.execute("INSERT INTO user_bans (id, user_id, kind, reason, actor_id, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
                        (uuid.uuid4().hex, target["id"], kind, reason, actor_id, now, expires))
        self.db.execute("UPDATE users SET status = 'banned' WHERE id = ?", (target["id"],))
        revoked = self.sessions.revoke_user(target["id"])  # also revokes every remember token
        return {"kind": kind, "expires_at": expires, "sessions_revoked": revoked}

    def unban(self, actor_id: str, target: dict, reason: str, ip_hash: str) -> None:
        if target["status"] != "banned":
            raise ApiError("This account is not banned.", 409, "not_banned")
        self.audit.admin_action(actor_id, "user_reinstated", target["id"], ip_hash, f"reinstated: {reason}"[:200])
        now = int(time.time())
        self.db.execute("UPDATE user_bans SET lifted_at = ?, lifted_by = ?, lift_reason = ? WHERE user_id = ? AND lifted_at IS NULL",
                        (now, actor_id, reason, target["id"]))
        self.db.execute("UPDATE users SET status = 'active' WHERE id = ? AND status = 'banned'", (target["id"],))
