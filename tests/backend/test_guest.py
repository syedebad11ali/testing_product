"""Restricted guest sessions (T3): real server-side session, denied on every private/admin route, hidden from admin views."""
import re
import time
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_auth import ADMIN_PW, Client  # noqa: E402

GUEST = "/api/v1/auth/guest"


def guest_client(**kw):
    c = Client(app_env="development", **kw)
    r = c.post(GUEST, {})
    assert r.status_code == 201, r.get_json()
    return c


def db(c):
    return c.app.extensions["kpt"].database()


def fill(rule: str) -> str:
    return re.sub(r"<(?:int:)?[^>]+>", lambda m: "1" if m.group(0).startswith("<int:") else "a" * 32, rule)


class GuestSessionTests(unittest.TestCase):
    def test_guest_gets_a_real_restricted_session(self):
        c = Client(app_env="development")
        r = c.post(GUEST, {})
        self.assertEqual((r.status_code, r.get_json()["user"]["role"]), (201, "guest"))
        self.assertTrue([h for h in r.headers.getlist("Set-Cookie") if "session" in h])
        self.assertFalse([h for h in r.headers.getlist("Set-Cookie") if "remember" in h])
        me = c.get("/api/v1/auth/me").get_json()["user"]
        self.assertEqual((me["role"], me["name"]), ("guest", "Guest"))
        row = db(c).one("SELECT * FROM users WHERE role='guest'")
        self.assertIsNone(row["email"]); self.assertIsNone(row["username"]); self.assertIsNone(row["password_hash"])
        s = db(c).one("SELECT idle_s, expires_at - created_at AS span FROM sessions")
        self.assertEqual((s["idle_s"], s["span"]), (900, 7200))   # shorter than a normal user (1800 / 43200)

    def test_guest_endpoint_needs_csrf_and_ignores_remember(self):
        c = Client(app_env="development")
        self.assertEqual(c.post(GUEST, {}, token=None).status_code, 403)
        r = c.post(GUEST, {"remember": True})
        self.assertFalse([h for h in r.headers.getlist("Set-Cookie") if "remember" in h])
        self.assertEqual(db(c).one("SELECT COUNT(*) AS n FROM remember_tokens")["n"], 0)

    def test_guest_cannot_log_in_with_a_password_or_become_admin(self):
        c = guest_client()
        for ident in ("", "guest", "Guest", "admin_001"):
            r = c.post("/api/v1/auth/login", {"identifier": ident or "x", "password": "anything-at-all"})
            self.assertIn(r.status_code, (200, 400, 401))
            self.assertNotEqual(r.get_json().get("ok"), True)
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "guest")
        self.assertEqual(c.get("/admin").status_code, 302)
        self.assertEqual(c.get("/api/v1/admin/users").status_code, 403)

    def test_features_advertise_guest(self):
        self.assertTrue(Client(app_env="development").get("/api/v1/auth/features").get_json()["guest"])

    def test_logout_removes_the_guest_row_and_session(self):
        c = guest_client()
        self.assertEqual(c.post("/api/v1/auth/logout", {}).status_code, 200)
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])
        self.assertEqual(db(c).one("SELECT COUNT(*) AS n FROM users WHERE role='guest'")["n"], 0)
        self.assertEqual(db(c).one("SELECT COUNT(*) AS n FROM sessions")["n"], 0)

    def test_per_network_cap(self):
        c = Client(app_env="development", guest_max_active_per_ip=2)
        self.assertEqual([c.post(GUEST, {}).status_code for _ in range(3)], [201, 201, 429])

    def test_cleanup_is_bounded_and_only_touches_expired_guests(self):
        c = Client(app_env="development", guest_cleanup_batch=2, guest_max_active_per_ip=50)
        for _ in range(5):
            c.post(GUEST, {})
        self.assertEqual(c.signup().status_code, 201)   # also ends this client's own (5th) guest session -> 4 guests left
        d = db(c)
        d.execute("UPDATE sessions SET expires_at = 1 WHERE user_id IN (SELECT id FROM users WHERE role='guest')")
        gs = c.app.extensions["kpt"].guests()
        self.assertEqual(gs.cleanup(), 2)                                  # bounded by guest_cleanup_batch
        self.assertEqual(d.one("SELECT COUNT(*) AS n FROM users WHERE role='guest'")["n"], 2)
        self.assertEqual(gs.cleanup(limit=100), 2)
        self.assertEqual(d.one("SELECT COUNT(*) AS n FROM users WHERE role='guest'")["n"], 0)
        self.assertEqual(d.one("SELECT COUNT(*) AS n FROM users WHERE role='user'")["n"], 1)       # the real user survives
        self.assertEqual(d.one("SELECT COUNT(*) AS n FROM users WHERE role='admin'")["n"], 1)
        self.assertEqual(d.one("SELECT COUNT(*) AS n FROM sessions")["n"], 1)                       # only Sara's session remains

    def test_live_guests_are_not_cleaned_and_new_guest_triggers_cleanup(self):
        c = Client(app_env="development")
        c.post(GUEST, {})
        d = db(c)
        self.assertEqual(c.app.extensions["kpt"].guests().cleanup(), 0)
        d.execute("UPDATE sessions SET last_seen_at = last_seen_at - 5000")   # idle-expired
        c2 = Client(app_env="development"); c2.app = c.app
        c.post(GUEST, {})                                                       # creating a guest cleans the stale one
        self.assertEqual(d.one("SELECT COUNT(*) AS n FROM users WHERE role='guest'")["n"], 1)

    def test_expired_guest_session_is_rejected(self):
        c = guest_client()
        db(c).execute("UPDATE sessions SET last_seen_at = ?", (int(time.time()) - 5000,))
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])


class GuestRestrictionTests(unittest.TestCase):
    def test_guest_is_denied_on_named_private_and_write_routes(self):
        c = guest_client()
        for method, path in (("get", "/api/v1/messages/conversations"), ("get", "/api/v1/messages/unread"),
                             ("post", "/api/v1/messages/start"), ("get", "/api/v1/listings/mine"), ("post", "/api/v1/listings"),
                             ("post", "/api/v1/verification/check"), ("get", "/api/v1/account/prefs"), ("get", "/api/v1/account/devices"),
                             ("post", "/api/v1/auth/change-password"), ("get", "/api/v1/admin/users"), ("get", "/api/v1/admin/export/users.csv")):
            r = c.get(path) if method == "get" else c.post(path, {})
            if r.status_code == 404:
                continue   # path guess does not exist in this build; the matrix below covers every real route
            self.assertEqual(r.status_code, 403, path)

    def test_public_browsing_still_works_for_guests(self):
        c = guest_client()
        self.assertEqual(c.get("/api/v1/listings").status_code, 200)
        self.assertEqual(c.get("/").status_code, 200)
        self.assertEqual(c.get("/listings").status_code, 200)
        self.assertEqual(c.get("/api/v1/health").status_code, 200)

    def test_messages_page_sends_guests_to_login(self):
        c = guest_client()
        r = c.get("/messages")
        self.assertEqual((r.status_code, r.headers["Location"].split("?")[0]), (302, "/login"))

    def test_guest_is_not_a_seller_or_buyer_in_listing_lookup(self):
        c = guest_client()
        r = c.get("/api/v1/listings/by-ref/" + "a" * 8)
        self.assertLess(r.status_code, 500)

    def test_admin_cannot_manage_guest_rows(self):
        g = guest_client()
        gid = db(g).one("SELECT id FROM users WHERE role='guest'")["id"]
        a = Client(app_env="development"); a.app = g.app
        a.c = g.app.test_client(); a.token = a.c.get("/api/v1/auth/csrf", base_url="https://localhost").get_json()["csrf_token"]
        self.assertEqual(a.post("/api/v1/auth/developer-login", {"identifier": "admin_001", "password": ADMIN_PW}).status_code, 200)
        users = a.get("/api/v1/admin/users?per=100").get_json()
        self.assertEqual([u for u in users["users"] if u["role"] == "guest"], [])
        self.assertEqual(users["total"], len(users["users"]))
        self.assertEqual([u for u in a.get("/api/v1/admin/users?role=guest").get_json()["users"] if u["role"] == "guest"], [])
        csv_rows = a.get("/api/v1/admin/export/users.csv").get_data(as_text=True).splitlines()
        self.assertGreaterEqual(len(csv_rows), 2)   # header + admin_001: a real export, not an error body
        self.assertFalse([r for r in csv_rows[1:] if ",guest," in r])
        self.assertEqual([s for s in a.get("/api/v1/admin/sessions").get_json()["sessions"] if s["role"] == "guest"], [])
        for path in (f"/api/v1/admin/users/{gid}/disable", f"/api/v1/admin/users/{gid}/role"):
            self.assertEqual(a.post(path, {"role": "admin", "reason": "test reason", "password": ADMIN_PW}).status_code, 404, path)
        self.assertEqual(db(g).one("SELECT role FROM users WHERE id = ?", (gid,))["role"], "guest")


class RouteAuthorizationMatrix(unittest.TestCase):
    """Every API route x {anonymous, user, guest, admin}. Discovered from the URL map, so a new private route is covered."""

    @classmethod
    def setUpClass(cls):
        cls.base = Client(app_env="development", guest_max_active_per_ip=1000)
        cls.app = cls.base.app
        cls.routes = []
        for rule in cls.app.url_map.iter_rules():
            if rule.rule.startswith("/api/") and rule.endpoint != "static":
                for m in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                    cls.routes.append((m, fill(rule.rule)))

    def client_for(self, kind):
        c = Client(app_env="development", guest_max_active_per_ip=1000)
        c.app = self.app
        c.c = self.app.test_client()
        c.token = c.c.get("/api/v1/auth/csrf", base_url="https://localhost").get_json()["csrf_token"]
        if kind == "guest":
            assert c.post(GUEST, {}).status_code == 201
        elif kind == "user":
            self.assertIn(c.signup(email=f"u{time.time_ns()}@example.com").status_code, (201,))
        elif kind == "admin":
            assert c.post("/api/v1/auth/developer-login", {"identifier": "admin_001", "password": ADMIN_PW}).status_code == 200
        return c

    @staticmethod
    def call(c, method, path):
        if method == "GET":
            return c.get(path)
        return c.post(path, {}) if method == "POST" else getattr(c.c, method.lower())(path, json={}, headers={"X-CSRF-Token": c.token, "Origin": "https://localhost"}, base_url="https://localhost")

    def test_matrix(self):
        self.assertGreater(len(self.routes), 50)
        anon = self.client_for("anon")
        guest = self.client_for("guest")
        private, admin_only = [], []
        for method, path in self.routes:
            if path.endswith("/auth/guest") or path.endswith("/auth/logout"):
                continue   # session lifecycle routes are exercised in the tests above
            ra, rg = self.call(anon, method, path), self.call(guest, method, path)
            self.assertLess(ra.status_code, 500, (method, path)); self.assertLess(rg.status_code, 500, (method, path))
            if ra.status_code == 401:                       # a login-protected route
                private.append((method, path))
                self.assertEqual(rg.status_code, 403, f"guest must be denied on {method} {path} (got {rg.status_code})")
                if "/admin" not in path:
                    self.assertEqual(rg.get_json().get("code"), "guest_not_allowed", (method, path))
            if "/api/v1/admin/" in path or path.endswith("/admin"):
                admin_only.append((method, path))
                self.assertIn(rg.status_code, (403, 404), (method, path))
        self.assertGreater(len(private), 25)
        self.assertGreater(len(admin_only), 15)

    def test_admin_routes_deny_normal_users_and_guests_but_not_admins(self):
        user, guest, admin = self.client_for("user"), self.client_for("guest"), self.client_for("admin")
        gets = [p for m, p in self.routes if m == "GET" and p.startswith("/api/v1/admin/")]
        self.assertGreater(len(gets), 5)
        for p in gets:
            self.assertEqual(user.get(p).status_code, 403, p)
            self.assertEqual(guest.get(p).status_code, 403, p)
            self.assertNotIn(admin.get(p).status_code, (401, 403), p)


if __name__ == "__main__":
    unittest.main()
