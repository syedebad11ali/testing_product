"""Operator recovery for a lost authenticator (e.g. admin_001). There is NO web bypass: this needs shell access to the
deployment with the real DATABASE_URL, so it is as strong as access to your hosting account.

    python scripts/reset_admin_totp.py --user admin_001                    # shows what would happen (dry run)
    python scripts/reset_admin_totp.py --user admin_001 --confirm RESET    # removes the second factor, logs the admin out everywhere

It deletes the admin's TOTP secret and pending step-up proofs, revokes all their sessions, and writes an audit entry
(``totp_reset_by_operator``). Afterwards the admin logs in with the password and enrols a new device from the Security panel.
If ADMIN_TOTP_REQUIRED=1 they can still log in and enrol, but cannot use sensitive actions until they do.
It never prints secrets, codes or proofs. See docs/ADMIN.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def reset(db, audit, sessions, username: str, apply: bool) -> dict:
    """Core logic (also used by the tests). Returns a summary; nothing changes unless ``apply``."""
    user = db.one("SELECT id, role FROM users WHERE username = ? OR email = ?", (username, username))
    if not user or user["role"] != "admin":
        return {"ok": False, "reason": "no such admin account"}
    row = db.one("SELECT status FROM admin_totp WHERE user_id = ?", (user["id"],))
    summary = {"ok": True, "user": username, "two_factor": row["status"] if row else "none", "applied": apply}
    if apply:
        db.execute("DELETE FROM admin_totp WHERE user_id = ?", (user["id"],))
        db.execute("DELETE FROM admin_stepups WHERE user_id = ?", (user["id"],))
        summary["sessions_revoked"] = sessions.revoke_user(user["id"])
        audit.admin_action(user["id"], "totp_reset_by_operator", user["id"], "operator", "recovery script")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", required=True, help="admin username or email, e.g. admin_001")
    ap.add_argument("--confirm", default="", help="type RESET to apply (default is a dry run)")
    args = ap.parse_args(argv)
    from backend.config import Settings
    from backend.db import open_database
    from backend.services.audit_service import AuditService
    from backend.services.session_service import SessionService
    s = Settings.from_env()
    db = open_database(s.database_url, local_path=s.local_db_path)
    result = reset(db, AuditService(db, s.ip_hash_salt), SessionService(db, s), args.user, args.confirm == "RESET")
    print(result)
    if result["ok"] and not result["applied"]:
        print("Dry run. Add --confirm RESET to remove the second factor.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
