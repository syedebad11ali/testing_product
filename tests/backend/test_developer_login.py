"""Developer Login endpoint: only an active admin gets a session; every other attempt ends at /nice-try."""
import dataclasses
import unittest
import warnings

warnings.filterwarnings("ignore")

from backend.config import Settings  # noqa: E402
from backend.services import dev_skip  # noqa: E402
from tests.backend.test_auth import ADMIN_PW, Client  # noqa: E402

NICE = {"redirect": "/nice-try"}
DEV_PW = "local-dev-skip-pass"


def dev(c, ident, pw, **kw):
    return c.post("/api/v1/auth/developer-login", {"identifier": ident, "password": pw}, **kw)


def session_cookies(r):
    return [h for h in r.headers.getlist("Set-Cookie") if "session" in h]


class DeveloperLoginTests(unittest.TestCase):
    def test_valid_admin_gets_admin_session_and_page(self):
        c = Client(app_env="development")
        r = dev(c, "admin_001", ADMIN_PW)
        self.assertEqual((r.status_code, r.get_json()["redirect"]), (200, "/admin"))
        self.assertTrue(session_cookies(r))
        self.assertEqual(c.get("/admin").status_code, 200)
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "admin")

    def test_invalid_credentials_go_to_nice_try_without_session(self):
        c = Client(app_env="development")
        for ident, pw in (("whoever", "whatever"), ("admin_001", "wrong-password"), ("nobody@example.com", ADMIN_PW), ("ADMIN_001", "x")):
            r = dev(c, ident, pw)
            self.assertEqual((r.status_code, r.get_json()), (200, NICE), ident)
            self.assertEqual(session_cookies(r), [], ident)
        self.assertEqual(c.get("/admin").status_code, 302)
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])

    def test_correct_password_of_a_normal_user_is_denied(self):
        c = Client(app_env="development")
        self.assertEqual(c.signup().status_code, 201)
        c.post("/api/v1/auth/logout", {})
        r = dev(c, "sara@example.com", "correct-horse-battery")
        self.assertEqual((r.status_code, r.get_json()), (200, NICE))
        self.assertEqual(session_cookies(r), [])
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])
        db = c.app.extensions["kpt"].database()
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM login_events WHERE method='developer' AND success=0 AND reason='not_admin'")["n"], 1)
        self.assertEqual(c.get("/api/v1/admin/users").status_code, 401)

    def test_legacy_dev_admin_is_refused_by_production_settings(self):
        # A production app needs PostgreSQL (not available here), so the production rule is checked on the settings.
        prod = dataclasses.replace(Settings.from_env(), app_env="production", dev_admin_password=DEV_PW, database_url=None)
        self.assertFalse(dev_skip.available(prod))
        self.assertFalse(dev_skip._admin_allowed(prod, "admin__01", DEV_PW))

    def test_real_admin_path_does_not_depend_on_dev_skip(self):
        c = Client(app_env="development", dev_admin_password=None)
        self.assertEqual(dev(c, "admin__01", "anything").get_json(), NICE)
        self.assertEqual(dev(c, "admin_001", ADMIN_PW).get_json()["redirect"], "/admin")

    def test_failed_attempts_count_toward_lockout(self):
        c = Client(app_env="development", lockout_threshold=3)
        for _ in range(3):
            self.assertEqual(dev(c, "admin_001", "bad").get_json(), NICE)
        r = dev(c, "admin_001", ADMIN_PW)   # correct password, but locked
        self.assertEqual((r.get_json(), session_cookies(r)), (NICE, []))

    def test_legacy_dev_admin_accepted_here_in_development_only(self):
        c = Client(app_env="development", dev_admin_password=DEV_PW)
        self.assertEqual(dev(c, "admin__01", "wrong").get_json(), NICE)
        r = dev(c, "admin__01", DEV_PW)
        self.assertEqual(r.get_json()["redirect"], "/admin")
        self.assertEqual(c.get("/admin").status_code, 200)
        for pw in (None, ""):
            c2 = Client(app_env="development", dev_admin_password=pw)
            self.assertEqual(dev(c2, "admin__01", "x").get_json(), NICE)

    def test_csrf_and_input_validation(self):
        c = Client(app_env="development")
        self.assertEqual(dev(c, "admin_001", ADMIN_PW, token=None).status_code, 403)
        self.assertEqual(c.post("/api/v1/auth/developer-login", {"identifier": "", "password": ""}).status_code, 400)

    def test_dev_skip_endpoint_unchanged(self):
        c = Client(app_env="development", dev_admin_password=DEV_PW)
        self.assertEqual(c.post("/api/v1/auth/dev-skip", {"identifier": "admin_001", "password": ADMIN_PW}).get_json(), NICE)

    def test_features_advertises_developer_login(self):
        c = Client(app_env="development")
        self.assertTrue(c.get("/api/v1/auth/features").get_json()["developer_login"])


if __name__ == "__main__":
    unittest.main()


class DeveloperLoginPageTests(unittest.TestCase):
    def test_page_is_served_and_wired_to_the_endpoint(self):
        c = Client(app_env="development")
        for path in ("/developer-login", "/developer-login.html"):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn(b'id="form-dev"', r.data)
            self.assertIn(b"/js/developer-login.js", r.data)
        self.assertNotIn("unsafe-inline", c.get("/developer-login").headers["Content-Security-Policy"].split("script-src")[1].split(";")[0])
        js = c.get("/js/developer-login.js")
        self.assertIn(b"/api/v1/auth/developer-login", js.data)

    def test_login_page_links_to_it_and_has_no_skip_toggle(self):
        c = Client(app_env="development")
        html = c.get("/login").data
        self.assertIn(b'href="/developer-login"', html)
        self.assertNotIn(b"dev-skip", html)
        self.assertNotIn(b"dev-skip", c.get("/js/auth-page.js").data)

    def test_page_alone_grants_nothing(self):
        c = Client(app_env="development")
        c.get("/developer-login")
        self.assertEqual(c.get("/admin").status_code, 302)
        self.assertEqual(c.get("/api/v1/admin/users").status_code, 401)
