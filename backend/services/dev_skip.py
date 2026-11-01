"""DEV-ONLY "Skip login" shortcut (troll button on the login page).

* Anything typed after pressing the button ends at ``/nice-try`` (the dog page). No session is created.
* The one exception: username ``admin__01`` + the password in ``DEV_ADMIN_PASSWORD`` opens ``/admin``.

Hard limits, all enforced here on the server (the browser only decides whether to show the button):
* never in production (``APP_ENV=production``, which Vercel sets): the endpoint answers 404;
* an empty / unset ``DEV_ADMIN_PASSWORD`` can never match, so nobody gets in;
* only with the local SQLite file (no ``DATABASE_URL``), so a shared / real database never gets this account;
* the ``admin__01`` row has no password hash, so the normal login form can never sign into it.
"""
from __future__ import annotations

import hmac
import logging
import time
import uuid

from backend.config import Settings
from backend.db import Database

log = logging.getLogger("kpt.dev_skip")
DEV_ADMIN_USERNAME = "admin__01"   # two underscores on purpose: different from the real admin_001
TROLL_REDIRECT = "/nice-try"


def available(settings: Settings) -> bool:
    return settings.dev_skip_enabled


def _admin_allowed(settings: Settings, identifier: str, password: str) -> bool:
    """True only for the exact dev username + the exact non-empty env password (constant-time compare)."""
    expected = settings.dev_admin_password or ""
    same_pw = hmac.compare_digest(password.encode(), expected.encode())   # always runs: no timing hint
    same_user = hmac.compare_digest(identifier.strip().lower().encode(), DEV_ADMIN_USERNAME.encode())
    return bool(expected) and same_pw and same_user and not settings.is_production and not settings.database_url


def _ensure_dev_admin(db: Database) -> dict:
    row = db.one("SELECT * FROM users WHERE username = ?", (DEV_ADMIN_USERNAME,))
    if row:
        return row
    db.execute("INSERT INTO users (id, username, name, password_hash, role, status, method, must_change_password, created_at) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (uuid.uuid4().hex, DEV_ADMIN_USERNAME, "Dev Admin", None, "admin", "active", "dev_skip", 0, int(time.time())))
    log.warning("dev admin account %s created (local development only)", DEV_ADMIN_USERNAME)
    return db.one("SELECT * FROM users WHERE username = ?", (DEV_ADMIN_USERNAME,))


def try_dev_admin(kpt, identifier: str, password: str, ip_hash: str, ua: str) -> tuple[dict, str] | None:
    """(user, raw session id) when the dev admin credentials match, else ``None`` (caller sends the troll redirect)."""
    s = kpt.settings
    if not _admin_allowed(s, identifier, password):
        if identifier.strip().lower() == DEV_ADMIN_USERNAME:   # leave a trace of wrong guesses at the privileged name
            kpt.audit().login_event(identifier=DEV_ADMIN_USERNAME, method="dev_skip", success=False, ip_hash=ip_hash,
                                    user_agent=ua, reason="bad_dev_credentials")
        return None
    row = _ensure_dev_admin(kpt.database())
    if row["status"] != "active":
        return None
    kpt.audit().login_event(identifier=DEV_ADMIN_USERNAME, method="dev_skip", success=True, ip_hash=ip_hash,
                            user_agent=ua, user_id=row["id"], reason="dev_admin")
    return row, kpt.sessions().create(row, ip_hash, ua)
