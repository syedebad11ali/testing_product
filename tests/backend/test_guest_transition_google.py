"""G3b2b: Google sign-in uses the SAME guest -> account transition as login/signup (`_start_session`).
MOCKED: the Google ID-token verifier is replaced by a fake (no network, no credentials), exactly like auth GoogleTests.
This proves the server-side session handling for a Google success/failure; it is NOT a live Google OAuth verification."""
import time
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_auth import Client  # noqa: E402
from tests.backend.test_guest import GUEST, db  # noqa: E402

CID = "test-client.apps.googleusercontent.com"


def n(c, sql):
    return db(c).one(sql)["n"]


class GoogleGuestTransition(unittest.TestCase):
    def setUp(self):
        self.c = Client(app_env="development", google_client_id=CID)
        self.claims = {}
        kpt = self.c.app.extensions["kpt"]
        kpt.google_verifier = lambda cred, cid: (_ for _ in ()).throw(ValueError("bad signature")) if cred == "raise" else dict(self.claims)
        self.assertEqual(self.c.post(GUEST, {}).status_code, 201)

    def google(self, credential="tok", **claim_overrides):
        cfg = self.c.get("/api/v1/auth/google/config").get_json()
        self.claims = {"aud": CID, "iss": "https://accounts.google.com", "exp": time.time() + 600, "sub": "g-777",
                       "email": "gina@example.com", "email_verified": True, "name": "Gina Shah", "nonce": cfg["nonce"], **claim_overrides}
        return self.c.post("/api/v1/auth/google", {"credential": credential})

    def test_google_success_ends_the_callers_guest_session_only(self):
        kpt = self.c.app.extensions["kpt"]
        mine = db(self.c).one("SELECT user_id, ip_hash FROM sessions")
        other, _ = kpt.guests().create(mine["ip_hash"], "other-browser")          # another visitor on the same network
        self.assertEqual(n(self.c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 2)
        r = self.google()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/api/v1/auth/me").get_json()["user"]["role"], "user")
        self.assertEqual(db(self.c).one("SELECT COUNT(*) AS n FROM users WHERE id=?", (mine["user_id"],))["n"], 0)   # my guest row is gone
        left = db(self.c).one("SELECT id FROM users WHERE role='guest'")["id"]
        self.assertEqual(left, other["id"])                                         # the other guest is untouched
        self.assertEqual(db(self.c).one("SELECT COUNT(*) AS n FROM sessions WHERE user_id=? AND revoked_at IS NULL", (other["id"],))["n"], 1)
        self.assertEqual(n(self.c, "SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL"), 2)   # the new account session + the other guest

    def test_failed_google_sign_in_keeps_the_guest_session(self):
        for kind in ("raise", "wrong_aud", "unverified", "bad_nonce"):
            if kind == "raise":
                r = self.google(credential="raise")
            elif kind == "wrong_aud":
                r = self.google(aud="someone-else.apps.googleusercontent.com")
            elif kind == "unverified":
                r = self.google(email_verified=False)
            else:
                r = self.google(nonce="not-ours")
            self.assertGreaterEqual(r.status_code, 400, kind)
            self.assertEqual(self.c.get("/api/v1/auth/me").get_json()["user"]["role"], "guest", kind)
        self.assertEqual(n(self.c, "SELECT COUNT(*) AS n FROM users WHERE role='guest'"), 1)
        self.assertEqual(n(self.c, "SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL"), 1)

    def test_no_second_session_store_is_created(self):
        self.assertEqual(self.google().status_code, 200)
        self.assertEqual(n(self.c, "SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL"), 1)


if __name__ == "__main__":
    unittest.main()
