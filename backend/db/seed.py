"""Create the built-in ``admin_001`` account from ``ADMIN_001_PASSWORD`` (hash only is stored).

* The password never appears in source, HTML, JS or git; it comes from the environment.
* Development: any non-empty value works (a throwaway value in your local .env for a demo).
* Production (``APP_ENV=production``): a weak password (short, equal to / containing the username, common)
  means the account is NOT created, and a created one must change its password on first login.
* An existing account is never overwritten on restart (changing the env var later does not reset it).
"""
from __future__ import annotations

import logging
import time
import uuid

from backend.config import Settings
from backend.db import Database
from backend.security import passwords

log = logging.getLogger("kpt.seed")
USERNAME = "admin_001"


def seed_admin(db: Database, settings: Settings) -> str:
    """Returns ``created`` | ``exists`` | ``skipped_no_password`` | ``refused_weak_password``."""
    if db.one("SELECT 1 AS x FROM users WHERE username = ?", (USERNAME,)):
        return "exists"
    password = settings.admin_001_password
    if not password:
        log.info("ADMIN_001_PASSWORD not set: admin_001 is disabled")
        return "skipped_no_password"
    if settings.is_production and not passwords.is_strong_for_admin(password, USERNAME):
        log.error("ADMIN_001_PASSWORD is too weak for production: admin_001 NOT created")
        return "refused_weak_password"
    db.execute("INSERT INTO users (id, username, name, password_hash, role, status, method, must_change_password, created_at) "
               "VALUES (?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, USERNAME, "Administrator", passwords.hash_password(password),
                                               "admin", "active", "password", 1 if settings.is_production else 0, int(time.time())))
    log.info("admin_001 created (must_change_password=%s)", settings.is_production)
    return "created"
