"""G2: a Guest can browse only. Server-side enforcement of 'every other interactive feature needs an account'.

* chat (submit, session, feedback; versioned and legacy paths): anonymous 401, guest 403 guest_not_allowed, user/admin allowed;
* CORS pre-flights keep working; a pending password change is still refused; rejected guest calls do not end the guest session;
* a route-permission matrix over the real Flask URL map with an EXPLICIT public allow-list: any API route outside it must refuse
  anonymous callers (401 auth_required) and guests (403 guest_not_allowed), so a future unguarded route fails here.
"""
import re
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_auth import ADMIN_PW, BASE, Client  # noqa: E402

V1 = "/api/v1"
CHAT = (f"{V1}/chat", "/api/chat")
SESSION = (f"{V1}/chat/session", "/api/chat/session")
FEEDBACK = (f"{V1}/chat/feedback", "/api/chat/feedback")

# Routes intentionally reachable without an account (path relative to /api/v1 or /api, method). Everything else under /api/ is an
# account feature. Authentication infrastructure must stay public for guests: they need it to log in / sign up / exit.
PUBLIC = {
    ("/auth/csrf", "GET"), ("/auth/me", "GET"), ("/auth/features", "GET"), ("/auth/google/config", "GET"),
    ("/auth/login", "POST"), ("/auth/signup", "POST"), ("/auth/google", "POST"), ("/auth/forgot", "POST"), ("/auth/reset", "POST"),
    ("/auth/guest", "POST"), ("/auth/logout", "POST"), ("/auth/forget-device", "POST"),
    ("/auth/developer-login", "POST"), ("/auth/dev-skip", "POST"),
    ("/health", "GET"), ("/listings", "GET"), ("/listings/by-ref/<ref>", "GET"),
}
ADMIN_STATUS_HIDDEN = {("/health/detail", "GET")}   # answers 404 to everyone who is not an admin (existing behaviour)


def make(kind: str) -> Client:
    c = Client(app_env="development")
    if kind == "guest":
        assert c.post(f"{V1}/auth/guest", {}).status_code == 201
    elif kind == "user":
        assert c.signup().status_code == 201
    elif kind == "admin":
        assert c.post(f"{V1}/auth/developer-login", {"identifier": "admin_001", "password": ADMIN_PW}).status_code == 200
    return c


def code(r):
    return (r.get_json(silent=True) or {}).get("code")


def post(c, path, body):
    return c.post(path, body)


class ChatIsAnAccountFeature(unittest.TestCase):
    def test_anonymous_is_refused_everywhere(self):
        c = make("anon")
        for path in CHAT + FEEDBACK:
            r = post(c, path, {"message": "hello", "message_id": "abcdefgh", "rating": "up"})
            self.assertEqual((r.status_code, code(r)), (401, "auth_required"), path)
        for path in SESSION:
            r = c.get(path)
            self.assertEqual((r.status_code, code(r)), (401, "auth_required"), path)

    def test_guest_is_refused_with_guest_not_allowed(self):
        c = make("guest")
        for path in CHAT + FEEDBACK:
            r = post(c, path, {"message": "hello", "message_id": "abcdefgh", "rating": "up"})
            self.assertEqual((r.status_code, code(r)), (403, "guest_not_allowed"), path)
        for path in SESSION:
            r = c.get(path)
            self.assertEqual((r.status_code, code(r)), (403, "guest_not_allowed"), path)

    def test_registered_user_and_admin_keep_chat(self):
        for kind in ("user", "admin"):
            c = make(kind)
            for path in CHAT:
                r = post(c, path, {"message": "hello"})
                self.assertEqual(r.status_code, 200, (kind, path))
                self.assertTrue(r.get_json()["reply"], (kind, path))
            mid = post(c, CHAT[0], {"message": "prices in Gulshan"}).get_json()["message_id"]
            for path in FEEDBACK:
                self.assertEqual(post(c, path, {"message_id": mid, "rating": "up"}).status_code, 200, (kind, path))
            for path in SESSION:
                self.assertEqual(c.get(path).status_code, 200, (kind, path))

    def test_validation_still_runs_for_accounts(self):
        c = make("user")
        r = post(c, CHAT[0], {"message": ""})
        self.assertEqual((r.status_code, code(r)), (400, "empty_message"))

    def test_cors_preflight_still_answers_without_a_session(self):
        c = make("anon")
        for path in CHAT + FEEDBACK:
            self.assertEqual(c.c.options(path, base_url=BASE).status_code, 204, path)

    def test_pending_password_change_is_still_refused(self):
        c = make("user")
        c.app.extensions["kpt"].database().execute("UPDATE users SET must_change_password = 1 WHERE email = 'sara@example.com'")
        r = post(c, CHAT[0], {"message": "hello"})
        self.assertEqual((r.status_code, code(r)), (403, "password_change_required"))

    def test_rejected_guest_calls_do_not_end_the_guest_session(self):
        c = make("guest")
        for _ in range(3):
            self.assertEqual(post(c, CHAT[0], {"message": "hello"}).status_code, 403)
            self.assertEqual(c.get(SESSION[0]).status_code, 403)
        me = c.get(f"{V1}/auth/me").get_json()["user"]
        self.assertEqual(me["role"], "guest")
        self.assertEqual(c.get(f"{V1}/listings").status_code, 200)   # and browsing still works with the same session
        db = c.app.extensions["kpt"].database()
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM users WHERE role = 'guest'")["n"], 1)
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL")["n"], 1)


class GuestCanStillBrowse(unittest.TestCase):
    def test_browse_endpoints_and_pages(self):
        c = make("guest")
        self.assertEqual(c.get(f"{V1}/listings").status_code, 200)
        self.assertIn("listings", c.get(f"{V1}/listings").get_json())
        r = c.get(f"{V1}/listings/by-ref/does-not-exist")
        self.assertNotIn(r.status_code, (401, 403))            # a missing listing is a 404, not an authorization error
        self.assertEqual(c.get(f"{V1}/health").status_code, 200)
        for page in ("/", "/listings"):
            self.assertEqual(c.get(page).status_code, 200, page)

    def test_search_and_filter_parameters_are_not_account_features(self):
        c = make("guest")
        r = c.get(f"{V1}/listings?area=Gulshan&q=house&limit=5")
        self.assertEqual(r.status_code, 200)


def fill(rule: str) -> str:
    return re.sub(r"<(?:int:)?([^>]+)>", lambda m: "1" if m.group(0).startswith("<int:") else "a" * 32, rule)


class RoutePermissionMatrix(unittest.TestCase):
    """Every API rule in the URL map (versioned and legacy), checked as anonymous / guest / registered user."""

    @classmethod
    def setUpClass(cls):
        base = Client(app_env="development")
        cls.rules = []
        for rule in base.app.url_map.iter_rules():
            for prefix in (f"{V1}", "/api"):
                if rule.rule.startswith(prefix + "/") and (prefix != "/api" or not rule.rule.startswith(f"{V1}/")):
                    rel = rule.rule[len(prefix):]
                    for m in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                        cls.rules.append((rel, m, rule.rule))
                    break
        cls.anon, cls.guest, cls.user = make("anon"), make("guest"), make("user")

    @staticmethod
    def call(c, method, path):
        headers = {"Origin": BASE, "X-CSRF-Token": c.token}
        send = getattr(c.c, method.lower())   # get / post / put
        return send(path, headers=headers, base_url=BASE) if method == "GET" else send(path, json={}, headers=headers, base_url=BASE)

    def test_the_matrix_covers_the_real_route_map(self):
        rels = {(rel, m) for rel, m, _ in self.rules}
        self.assertGreater(len(self.rules), 60)
        for item in PUBLIC | ADMIN_STATUS_HIDDEN:
            self.assertIn(item, rels, f"public allow-list entry no longer exists: {item}")

    def test_every_route_outside_the_public_list_refuses_anonymous_and_guests(self):
        checked = []
        for rel, method, rule in self.rules:
            if (rel, method) in PUBLIC:
                continue
            path = fill(rule)
            ra, rg = self.call(self.anon, method, path), self.call(self.guest, method, path)
            if (rel, method) in ADMIN_STATUS_HIDDEN:
                self.assertEqual((ra.status_code, rg.status_code), (404, 404), (method, rule))
                continue
            self.assertEqual((ra.status_code, code(ra)), (401, "auth_required"), f"anonymous reached {method} {rule}")
            self.assertEqual((rg.status_code, code(rg)), (403, "guest_not_allowed"), f"guest reached {method} {rule}")
            checked.append((method, rule))
        self.assertGreater(len(checked), 35)
        self.assertTrue({("POST", f"{V1}/chat"), ("POST", "/api/chat"), ("GET", f"{V1}/chat/session"), ("POST", f"{V1}/chat/feedback")} <= set(checked))

    def test_the_guest_session_survives_the_whole_matrix(self):
        for rel, method, rule in self.rules:
            if (rel, method) not in PUBLIC and (rel, method) not in ADMIN_STATUS_HIDDEN:
                self.call(self.guest, method, fill(rule))
        self.assertEqual(self.guest.get(f"{V1}/auth/me").get_json()["user"]["role"], "guest")

    def test_admin_routes_stay_closed_to_a_registered_user(self):
        for rel, method, rule in self.rules:
            if rel.startswith("/admin") and method == "GET":
                r = self.call(self.user, method, fill(rule))
                self.assertEqual((r.status_code, code(r)), (403, "forbidden"), rule)

    def test_public_routes_do_not_demand_an_account(self):
        for rel, method, rule in self.rules:
            if (rel, method) in PUBLIC and method == "GET" and "<" not in rule:
                self.assertEqual(self.call(self.anon, method, rule).status_code, 200, rule)
                self.assertEqual(self.call(self.guest, method, rule).status_code, 200, rule)


if __name__ == "__main__":
    unittest.main()
