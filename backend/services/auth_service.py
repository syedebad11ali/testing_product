"""Sign-up, login, lockout and password change. No Flask imports; routes stay thin.

Security properties (see docs/AUTH.md):
* generic "Invalid email or password" for every failure (no account enumeration);
* equal work for unknown users (verify against a dummy hash);
* lockout per (account, IP) pair plus a higher per-account ceiling;
* ``admin_001`` is a normal row, created by ``db/seed.py`` from ``ADMIN_001_PASSWORD``; the browser never
  sees or compares a password, and every wrong password gets the same ``denied`` outcome.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass

from backend.services.moderation_service import resolve_status
from backend.config import Settings
from backend.db import Database
from backend.errors import ApiError
from backend.security import passwords
from backend.services.audit_service import AuditService
from backend.services.session_service import SessionService

ADMIN_USERNAME = "admin_001"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
ACCOUNT_CEILING_FACTOR = 4


@dataclass
class LoginOutcome:
    kind: str  # "ok" | "invalid" | "admin_denied"
    user: dict | None = None
    session_id: str | None = None


def public_user(row: dict) -> dict:
    return {"id": row.get("id") or row.get("user_id"), "name": row["name"], "role": row["role"],
            "must_change_password": bool(row.get("must_change_password"))}


class AuthService:
    def __init__(self, db: Database, settings: Settings, sessions: SessionService, audit: AuditService) -> None:
        self.db, self.s, self.sessions, self.audit = db, settings, sessions, audit

    # -- sign-up ---------------------------------------------------------------------------------
    def signup(self, name: str, email: str, password: str, ip_hash: str, ua: str) -> tuple[dict, str]:
        name, email = " ".join(name.split()), email.strip().lower()
        if not (1 <= len(name) <= 80):
            raise ApiError("Please enter your name (up to 80 characters).", 400, "invalid_name")
        if not EMAIL_RE.match(email) or len(email) > 254:
            raise ApiError("Please enter a valid email address.", 400, "invalid_email")
        problems = passwords.policy_problems(password, email=email)
        if problems:
            raise ApiError(" ".join(problems), 400, "weak_password")
        if self.db.one("SELECT 1 AS x FROM users WHERE email = ?", (email,)):
            self.audit.login_event(identifier=email, method="password", success=False, ip_hash=ip_hash, user_agent=ua, reason="signup_duplicate")
            raise ApiError("We could not create an account with those details. If you already registered, log in instead.", 409, "signup_failed")
        user = {"id": uuid.uuid4().hex, "name": name, "email": email, "role": "user",
                "must_change_password": 0}  # nosec B105 - a 0/1 flag, not a secret
        now = int(time.time())
        self.db.execute("INSERT INTO users (id, email, name, password_hash, role, status, method, must_change_password, created_at, last_login_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)", (user["id"], email, name, passwords.hash_password(password), "user", "active", "password", 0, now, now))
        self.audit.login_event(identifier=email, method="password", success=True, ip_hash=ip_hash, user_agent=ua, user_id=user["id"], reason="signup")
        return user, self.sessions.create(user, ip_hash, ua)

    # -- login -----------------------------------------------------------------------------------
    def _locked(self, identifier: str, ip_hash: str) -> bool:
        since = int(time.time()) - self.s.lockout_window_s
        pair = self.db.one("SELECT COUNT(*) AS n FROM login_events WHERE identifier = ? AND ip_hash = ? AND success = 0 AND ts > ?",
                           (identifier, ip_hash, since))["n"]
        total = self.db.one("SELECT COUNT(*) AS n FROM login_events WHERE identifier = ? AND success = 0 AND ts > ?",
                            (identifier, since))["n"]
        return pair >= self.s.lockout_threshold or total >= self.s.lockout_threshold * ACCOUNT_CEILING_FACTOR

    def login(self, identifier: str, password: str, ip_hash: str, ua: str, *, admin_only: bool = False) -> LoginOutcome:
        """Password login. With ``admin_only`` (Developer Login) a correct password of a non-admin account is
        treated exactly like a wrong one: no session, no last-login update, outcome ``admin_denied``."""
        method = "developer" if admin_only else "password"
        ident = identifier.strip().lower()[:254]
        is_admin_name = ident == ADMIN_USERNAME
        row = self.db.one("SELECT * FROM users WHERE username = ?" if is_admin_name else "SELECT * FROM users WHERE email = ?", (ident,))
        if row:
            row["status"] = resolve_status(self.db, row["id"], row["status"])
        locked = self._locked(ident, ip_hash)
        # Always do the same expensive hash work, whether or not the account exists or is locked.
        password_ok = passwords.verify_password(password, row["password_hash"] if row else None)
        enabled = bool(row) and row["status"] == "active" and bool(row["password_hash"])
        not_admin = admin_only and bool(row) and row["role"] != "admin"
        if password_ok and enabled and not locked and not not_admin:
            now = int(time.time())
            if passwords.needs_rehash(row["password_hash"]):
                self.db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (passwords.hash_password(password), row["id"]))
            self.db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
            self.audit.login_event(identifier=ident, method=method, success=True, ip_hash=ip_hash, user_agent=ua, user_id=row["id"])
            return LoginOutcome("ok", row, self.sessions.create(row, ip_hash, ua))  # new id every login = rotation
        reason = "locked" if locked else (row["status"] if row and row["status"] != "active" else ("not_admin" if not_admin and password_ok else "bad_credentials"))
        self.audit.login_event(identifier=ident, method=method, success=False, ip_hash=ip_hash, user_agent=ua,
                               user_id=row["id"] if row else None, reason=reason)
        return LoginOutcome("admin_denied" if (is_admin_name or admin_only) else "invalid")

    # -- google ----------------------------------------------------------------------------------
    def google_login(self, ident, ip_hash: str, ua: str) -> LoginOutcome:
        """Sign in (or create / link) the account for a Google-verified identity.

        Linking: a verified email matches an existing password account. Because this site has no email
        verification for password sign-ups, that account may have been created by someone who does not
        own the address (pre-hijacking). So on first link the password is cleared and every existing
        session is revoked; the real owner can set a new password later. ``ADMIN_EMAILS`` promotion is
        applied here only, never for password sign-ups. The seeded ``admin_001`` (has a username) is never
        linked or created through Google.
        """
        now = int(time.time())
        row = self.db.one("SELECT * FROM users WHERE google_sub = ?", (ident.sub,))
        if row:
            row["status"] = resolve_status(self.db, row["id"], row["status"])
        reason = "google"
        if not row:
            row = self.db.one("SELECT * FROM users WHERE email = ?", (ident.email,))
            if row:
                row["status"] = resolve_status(self.db, row["id"], row["status"])
            if row and row["username"]:
                self.audit.login_event(identifier=ident.email, method="google", success=False, ip_hash=ip_hash, user_agent=ua,
                                       user_id=row["id"], reason="reserved_account")
                return LoginOutcome("invalid")
            if row:
                if row["status"] != "active":
                    return self._google_denied(ident, ip_hash, ua, row, row["status"])
                self.db.execute("UPDATE users SET google_sub = ?, password_hash = NULL WHERE id = ?", (ident.sub, row["id"]))
                self.sessions.revoke_user(row["id"])
                self.audit.admin_action(row["id"], "google_linked", row["id"], ip_hash, "password cleared on link")
                reason = "google_link"
            else:
                row = {"id": uuid.uuid4().hex, "email": ident.email, "name": ident.name, "role": "user", "status": "active",
                       "username": None, "must_change_password": 0}  # nosec B105 - a 0/1 flag, not a secret
                self.db.execute("INSERT INTO users (id, email, name, password_hash, role, status, method, must_change_password, "
                                "created_at, last_login_at, google_sub) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (row["id"], ident.email, ident.name, None, "user", "active", "google", 0, now, now, ident.sub))
                reason = "google_signup"
        if row["status"] != "active":
            return self._google_denied(ident, ip_hash, ua, row, row["status"])
        if ident.email in self.s.admin_emails and row["role"] != "admin":
            self.db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (row["id"],))
            self.audit.admin_action(row["id"], "admin_promoted_google", row["id"], ip_hash, "ADMIN_EMAILS")
            row = {**row, "role": "admin"}
        self.db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        self.audit.login_event(identifier=ident.email, method="google", success=True, ip_hash=ip_hash, user_agent=ua,
                               user_id=row["id"], reason=reason)
        return LoginOutcome("ok", row, self.sessions.create(row, ip_hash, ua))

    def _google_denied(self, ident, ip_hash: str, ua: str, row: dict, reason: str) -> LoginOutcome:
        self.audit.login_event(identifier=ident.email, method="google", success=False, ip_hash=ip_hash, user_agent=ua,
                               user_id=row["id"], reason=reason)
        return LoginOutcome("invalid")

    # -- password change ----------------------------------------------------------------------------
    def change_password(self, user_id: str, current: str, new: str, keep_session_raw: str | None) -> None:
        row = self.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
        if not row or not passwords.verify_password(current, row["password_hash"]):
            raise ApiError("Current password is incorrect.", 403, "invalid_credentials")
        problems = passwords.policy_problems(new, email=row["email"] or "", username=row["username"] or "")
        if row["username"] == ADMIN_USERNAME and self.s.is_production and not passwords.is_strong_for_admin(new, ADMIN_USERNAME):
            problems.append("Admin passwords need 14+ characters with at least three character types.")
        if problems:
            raise ApiError(" ".join(problems), 400, "weak_password")
        self.db.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?", (passwords.hash_password(new), user_id))
        self.sessions.revoke_user(user_id, keep_raw=keep_session_raw)  # other devices must log in again

    # -- account deletion ------------------------------------------------------------------------
    def delete_account(self, user_id: str, password: str, ip_hash: str) -> None:
        """Delete a user and everything tied to them. Password accounts must re-authenticate; Google-only accounts
        rely on the signed-in session plus the typed confirmation. The built-in admin and any admin cannot self-delete.
        Login events are kept for security but lose the user link and the email/username (data minimisation)."""
        row = self.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
        if not row:
            raise ApiError("Account not found.", 404, "not_found")
        if row["role"] == "admin" or row["username"] == ADMIN_USERNAME:
            raise ApiError("Admin accounts cannot be deleted here.", 403, "forbidden")
        if row["password_hash"] and not passwords.verify_password(password, row["password_hash"]):
            raise ApiError("Password is incorrect.", 403, "invalid_credentials")
        # Messaging: close the user's listings and drop their blocks and conversations, except conversations that were
        # reported (kept as abuse evidence until an admin resolves the report; see docs/MESSAGING.md).
        self.db.execute("UPDATE listings SET status = 'closed' WHERE seller_id = ?", (user_id,))
        self.db.execute("DELETE FROM user_blocks WHERE blocker_id = ? OR blocked_id = ?", (user_id, user_id))
        keep = "SELECT conversation_id FROM message_reports WHERE status = 'open'"
        mine = f"(SELECT id FROM conversations WHERE (buyer_id = ? OR seller_id = ?) AND id NOT IN ({keep}))"  # noqa: S608  # nosec B608 - f-string pieces are fixed literals (keep/mine/table from a fixed tuple); ids are bound
        self.db.execute(f"DELETE FROM messages WHERE conversation_id IN {mine}", (user_id, user_id))  # noqa: S608 - fixed SQL  # nosec B608 - f-string pieces are fixed literals (keep/mine/table from a fixed tuple); ids are bound
        self.db.execute("DELETE FROM conversations WHERE (buyer_id = ? OR seller_id = ?) AND id NOT IN (" + keep + ")", (user_id, user_id))  # noqa: S608  # nosec B608 - f-string pieces are fixed literals (keep/mine/table from a fixed tuple); ids are bound
        for table in ("sessions", "remember_tokens", "user_prefs", "password_resets"):
            self.db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))  # noqa: S608 - fixed table names  # nosec B608 - table iterates a fixed tuple of literals; id bound
        self.db.execute("UPDATE login_events SET user_id = NULL, identifier = 'deleted' WHERE user_id = ?", (user_id,))
        self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.audit.admin_action(user_id, "account_deleted", user_id, ip_hash)
