"""DEV-ONLY "Skip login" troll button: everything goes to /nice-try, except admin__01 + DEV_ADMIN_PASSWORD."""
import dataclasses
import unittest
import warnings

warnings.filterwarnings("ignore")

from backend.config import Settings  # noqa: E402
from backend.services import dev_skip  # noqa: E402
from tests.backend.test_auth import BASE, Client  # noqa: E402

DEV_PW = "local-dev-skip-pass"
TROLL = {"redirect": "/nice-try"}


def skip(c, ident, pw, **kw):
    return c.post("/api/v1/auth/dev-skip", {"identifier": ident, "password": pw}, **kw)


def session_cookies(r):
    return [h for h in r.headers.getlist("Set-Cookie") if "session" in h]


class DevSkipTests(unittest.TestCase):
    def test_any_credentials_land_on_the_dog_page_without_a_session(self):
        c = Client(app_env="development", dev_admin_password=DEV_PW)
        for ident, pw in (("whoever", "whatever"), ("admin_001", "local-demo-admin-pass"), ("admin__01", "wrong"),
                          ("ADMIN__01 ", "nope"), ("a@b.co", "x")):
            r = skip(c, ident, pw)
            self.assertEqual((r.status_code, r.get_json()), (200, TROLL), ident)
            self.assertFalse(session_cookies(r), ident)
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])
        self.assertEqual(c.get("/admin").status_code, 302)
        self.assertEqual(c.app.extensions["kpt"].database().one("SELECT COUNT(*) AS n FROM sessions")["n"], 0)

    def test_dev_admin_credentials_open_the_admin_page(self):
        c = Client(app_env="development", dev_admin_password=DEV_PW)
        r = skip(c, "admin__01", DEV_PW)
        self.assertEqual((r.status_code, r.get_json()["redirect"]), (200, "/admin"))
        self.assertTrue(session_cookies(r))
        self.assertEqual(c.get("/admin").status_code, 200)
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "admin")

    def test_empty_or_unset_env_password_never_matches(self):
        for pw in (None, ""):
            c = Client(app_env="development", dev_admin_password=pw)
            for guess in ("x", " ", "None"):
                self.assertEqual(skip(c, "admin__01", guess).get_json(), TROLL)
            self.assertEqual(c.get("/admin").status_code, 302)

    def test_wrong_guesses_at_the_dev_admin_name_are_logged(self):
        c = Client(app_env="development", dev_admin_password=DEV_PW)
        skip(c, "admin__01", "guess-1")
        skip(c, "someone-else", "guess-2")
        db = c.app.extensions["kpt"].database()
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM login_events WHERE method='dev_skip' AND success=0")["n"], 1)

    def test_normal_login_form_cannot_use_the_dev_account(self):
        c = Client(app_env="development", dev_admin_password=DEV_PW)
        skip(c, "admin__01", DEV_PW)   # creates the row
        other = Client(app_env="development", dev_admin_password=DEV_PW)
        skip(other, "admin__01", DEV_PW)
        for ident in ("admin__01", "admin_01"):
            r = other.login(ident, DEV_PW)
            self.assertEqual(r.status_code, 401, ident)
        row = other.app.extensions["kpt"].database().one("SELECT password_hash FROM users WHERE username='admin__01'")
        self.assertIsNone(row["password_hash"])

    def test_production_has_no_such_endpoint_and_no_button(self):
        c = Client(app_env="production", database_url=None, dev_admin_password=DEV_PW)
        r = skip(c, "admin__01", DEV_PW)
        self.assertEqual((r.status_code, r.get_json()["code"]), (404, "not_found"))
        self.assertFalse(session_cookies(r))
        self.assertIs(c.get("/api/v1/auth/features").get_json()["dev_skip"], False)

    def test_features_offers_the_button_in_development(self):
        c = Client(app_env="development")
        self.assertIs(c.get("/api/v1/auth/features").get_json()["dev_skip"], True)

    def test_csrf_still_required(self):
        c = Client(app_env="development", dev_admin_password=DEV_PW)
        r = skip(c, "admin__01", DEV_PW, token=None)
        self.assertEqual((r.status_code, r.get_json()["code"]), (403, "csrf_failed"))

    def test_shared_database_refuses_the_admin_shortcut(self):
        s = dataclasses.replace(Settings.from_env(), app_env="development", dev_admin_password=DEV_PW,
                                database_url="postgresql://example.invalid/db")
        self.assertFalse(dev_skip._admin_allowed(s, "admin__01", DEV_PW))
        local = dataclasses.replace(s, database_url=None)
        self.assertTrue(dev_skip._admin_allowed(local, "admin__01", DEV_PW))
        self.assertFalse(dev_skip._admin_allowed(dataclasses.replace(local, app_env="production"), "admin__01", DEV_PW))


if __name__ == "__main__":
    unittest.main()
