"""Guest -> account transition: a successful sign-up / login ends the caller's own guest session; failures keep it;
other guests on the same network are untouched."""
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_auth import ADMIN_PW  # noqa: E402,F401
from tests.backend.test_guest import GUEST, db, guest_client  # noqa: E402

PW = "correct-horse-battery"


def n(c, sql):
    return db(c).one(sql)["n"]


class GuestTransitionTests(unittest.TestCase):
    def test_signup_ends_the_guest_session_and_row(self):
        c = guest_client()
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "guest")
        self.assertEqual(c.signup().status_code, 201)
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "user")
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 0)
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL"), 1)

    def test_login_ends_the_guest_session_and_row(self):
        c = guest_client()
        self.assertEqual(c.signup().status_code, 201)
        c.post("/api/v1/auth/logout", {})
        self.assertEqual(c.post(GUEST, {}).status_code, 201)
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 1)
        self.assertEqual(c.login("sara@example.com", PW).status_code, 200)
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 0)
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "user")

    def test_failed_signup_and_login_keep_the_guest_session(self):
        c = guest_client()
        self.assertGreaterEqual(c.signup(pw="short").status_code, 400)          # rejected sign-up
        self.assertEqual(c.login("nobody@example.com", "wrong-password-1").status_code, 401)  # rejected login
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "guest")
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 1)
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL"), 1)

    def test_other_guests_on_the_same_network_are_untouched(self):
        c = guest_client()
        kpt = c.app.extensions["kpt"]
        mine = db(c).one("SELECT user_id, ip_hash FROM sessions")
        other, _raw = kpt.guests().create(mine["ip_hash"], "other-browser")      # another visitor, same IP hash
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 2)
        self.assertEqual(c.signup().status_code, 201)
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 1)
        left = db(c).one("SELECT id FROM users WHERE role='guest'")["id"]
        self.assertEqual(left, other["id"])
        self.assertEqual(db(c).one("SELECT COUNT(*) AS n FROM sessions WHERE user_id=? AND revoked_at IS NULL", (other["id"],))["n"], 1)
        self.assertNotEqual(left, mine["user_id"])

    def test_pressing_guest_again_does_not_discard_the_old_guest(self):
        c = guest_client()
        self.assertEqual(c.post(GUEST, {}).status_code, 201)
        self.assertEqual(n(c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 2)  # unchanged cap/cleanup behaviour


if __name__ == "__main__":
    unittest.main()
