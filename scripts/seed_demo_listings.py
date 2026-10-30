"""Create a demo seller account and listings for the static demo properties (p1..p8) so "Chat with seller" works locally.

Local development only: refuses to run in production. The demo seller's password comes from DEMO_SELLER_PASSWORD
(never hard-coded); the account is a normal user. Run:  DEMO_SELLER_PASSWORD='<12+ chars>' python scripts/seed_demo_listings.py
"""
from __future__ import annotations

import os
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import Settings  # noqa: E402
from backend.db import open_database  # noqa: E402
from backend.security import passwords  # noqa: E402

_SRC = (Path(__file__).resolve().parents[1] / "frontend/js/data/properties.js").read_text(encoding="utf-8")
DEMO = [(i, f"{t}, {a}", a) for i, t, a in re.findall(r"id:'(p\d+)',title:'([^']*)',type:'[^']*',area:'([^']*)'", _SRC)]
EMAIL = "demo.seller@kpt.local"


def main() -> int:
    s = Settings.from_env()
    if s.is_production:
        print("Refusing to seed demo data in production.")
        return 1
    pw = os.getenv("DEMO_SELLER_PASSWORD", "")
    if len(pw) < 12:
        print("Set DEMO_SELLER_PASSWORD (12+ characters).")
        return 1
    db = open_database(s.database_url, local_path=s.local_db_path)
    db.migrate()
    row = db.one("SELECT id FROM users WHERE email = ?", (EMAIL,))
    uid = row["id"] if row else uuid.uuid4().hex
    now = int(time.time())
    if not row:
        db.execute("INSERT INTO users (id, email, name, password_hash, role, status, method, must_change_password, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (uid, EMAIL, "Demo Seller", passwords.hash_password(pw), "user", "active", "password", 0, now))
    for ref, title, area in DEMO:
        if not db.one("SELECT id FROM listings WHERE ref = ?", (ref,)):
            db.execute("INSERT INTO listings (id, ref, seller_id, title, area, status, created_at) VALUES (?,?,?,?,?,?,?)", (uuid.uuid4().hex, ref, uid, title, area, "active", now))
    print(f"Seeded {len(DEMO)} demo listings for {EMAIL}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
