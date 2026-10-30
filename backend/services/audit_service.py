"""Login events and the admin audit log. No Flask imports.

IPs are stored only as a truncated HMAC (``ip_hash``) so events can be correlated without keeping
raw addresses. Never pass passwords, tokens or free text from users into ``detail``.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid

from backend.db import Database

log = logging.getLogger("kpt.audit")


class AuditService:
    def __init__(self, db: Database, ip_salt: str) -> None:
        self.db, self._salt = db, ip_salt.encode()

    def ip_hash(self, ip: str | None) -> str:
        return hmac.new(self._salt, (ip or "unknown").encode(), hashlib.sha256).hexdigest()[:16]

    def login_event(self, *, identifier: str, method: str, success: bool, ip_hash: str, user_agent: str,
                    user_id: str | None = None, reason: str = "") -> None:
        self.db.execute(
            "INSERT INTO login_events (id, ts, user_id, identifier, method, success, reason, ip_hash, user_agent) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, int(time.time()), user_id, identifier[:120], method, int(success), reason[:60], ip_hash,
             user_agent[:200]))
        log.info("login_event method=%s success=%s reason=%s ip=%s", method, success, reason, ip_hash)

    def admin_action(self, actor_id: str, action: str, target: str, ip_hash: str, detail: str = "") -> None:
        self.db.execute("INSERT INTO audit_log (id, ts, actor_id, action, target, ip_hash, detail) VALUES (?,?,?,?,?,?,?)",
                        (uuid.uuid4().hex, int(time.time()), actor_id, action, target[:80], ip_hash, detail[:200]))
        log.warning("admin_action action=%s actor=%s target=%s", action, actor_id, target)
