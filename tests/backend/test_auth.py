"""Auth, sessions, CSRF, admin_001 flow and admin access control (Flask test client, in-memory SQLite)."""
import dataclasses
import time
import unittest
import warnings

warnings.filterwarnings("ignore")

from backend.app import create_app  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.security import passwords  # noqa: E402

ADMIN_PW = "local-demo-admin-pass"
BASE = "https://localhost"


class Client:
    """Test client that behaves like the browser frontend: https, cookies, CSRF header + Origin."""

    def __init__(self, **overrides):
        # google_client_id=None keeps every test hermetic: create_app() loads the developer's .env, which may set a real
        # GOOGLE_CLIENT_ID. Tests that need Google pass their own value (GoogleTests) through **overrides.
        base = dict(gemini_api_key=None, google_client_id=None, local_db_path=":memory:", cookie_secure=True, admin_001_password=ADMIN_PW,
                    rate_limit_per_min=1000, verify_rate_limit_per_min=1000, login_rate_limit_per_min=1000)
        self.app = create_app(dataclasses.replace(Settings.from_env(), **{**base, **overrides}))
        self.c = self.app.test_client()
        self.token = self.c.get("/api/v1/auth/csrf", base_url=BASE).get_json()["csrf_token"]

    def post(self, path, json=None, token="default", origin=BASE):
        headers = {"Origin": origin} if origin else {}
        t = self.token if token == "default" else token
        if t:
            headers["X-CSRF-Token"] = t
        return self.c.post(path, json=json, headers=headers, base_url=BASE)

    def get(self, path, **kw):
        return self.c.get(path, base_url=BASE, **kw)

    def signup(self, email="sara@example.com", pw="correct-horse-battery", name="Sara Khan"):
        return self.post("/api/v1/auth/signup", {"name": name, "email": email, "password": pw})

    def login(self, ident, pw):
        return self.post("/api/v1/auth/login", {"identifier": ident, "password": pw})


class PasswordTests(unittest.TestCase):
    def test_hash_verify_and_policy(self):
        h = passwords.hash_password("correct-horse-battery")
        self.assertTrue(passwords.verify_password("correct-horse-battery", h))
        self.assertFalse(passwords.verify_password("wrong", h))
        self.assertFalse(passwords.verify_password("anything", None))
        self.assertNotIn("correct-horse", h)
        self.assertTrue(passwords.policy_problems("short"))
        self.assertTrue(passwords.policy_problems("password123"))
        self.assertTrue(passwords.policy_problems("sara.khan-2024", email="sara.khan@example.com"))
        self.assertEqual(passwords.policy_problems("correct-horse-battery"), [])

    def test_admin_strength_gate(self):
        self.assertFalse(passwords.is_strong_for_admin("admin_001", "admin_001"))
        self.assertFalse(passwords.is_strong_for_admin("shortPass1!", "admin_001"))
        self.assertTrue(passwords.is_strong_for_admin("Tr1cky-long-passphrase!", "admin_001"))


class CsrfTests(unittest.TestCase):
    def test_missing_wrong_token_and_foreign_origin_are_rejected(self):
        c = Client()
        for kw in ({"token": None}, {"token": "x" * 40}, {"origin": "https://evil.example"}):
            r = c.signup() if not kw else c.post("/api/v1/auth/signup", {"name": "A", "email": "a@b.co", "password": "correct-horse-battery"}, **kw)
            self.assertEqual((r.status_code, r.get_json()["code"]), (403, "csrf_failed"), kw)

    def test_csrf_cookie_flags(self):
        c = Client()
        cookie = [h for h in c.c.get("/api/v1/auth/csrf", base_url="https://localhost").headers.getlist("Set-Cookie")]
        self.assertEqual(cookie, [])  # already issued once in Client(); second call reuses it
        fresh = create_app(dataclasses.replace(Settings.from_env(), local_db_path=":memory:", cookie_secure=True)).test_client()
        sc = fresh.get("/api/v1/auth/csrf", base_url=BASE).headers["Set-Cookie"]
        for flag in ("__Host-kpt_csrf=", "Secure", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, sc)


class SignupLoginTests(unittest.TestCase):
    def test_signup_login_logout_and_cookie_flags(self):
        c = Client()
        r = c.signup()
        self.assertEqual(r.status_code, 201)
        sc = [h for h in r.headers.getlist("Set-Cookie") if "__Host-kpt_session" in h][0]
        for flag in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, sc)
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["name"], "Sara Khan")
        self.assertEqual(c.post("/api/v1/auth/logout").status_code, 200)
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])
        ok = c.login("SARA@example.com", "correct-horse-battery")
        self.assertEqual((ok.status_code, ok.get_json()["redirect"]), (200, "/"))

    def test_generic_error_for_wrong_password_and_unknown_user(self):
        c = Client()
        c.signup()
        a = c.login("sara@example.com", "wrong-password-here")
        b = c.login("nobody@example.com", "wrong-password-here")
        self.assertEqual((a.status_code, a.get_json()["error"]), (401, "Invalid email or password."))
        self.assertEqual(a.get_json()["error"], b.get_json()["error"])
        self.assertEqual(a.get_json()["code"], b.get_json()["code"])

    def test_signup_validation_and_duplicates(self):
        c = Client()
        self.assertEqual(c.signup(pw="short").get_json()["code"], "weak_password")
        self.assertEqual(c.signup(email="not-an-email").get_json()["code"], "invalid_email")
        self.assertEqual(c.signup().status_code, 201)
        self.assertEqual(c.signup().status_code, 409)

    def test_sql_injection_payloads_are_just_bad_credentials(self):
        c = Client()
        for payload in ("' OR '1'='1", "admin_001' --", "x'; DROP TABLE users; --"):
            self.assertIn(c.login(payload, payload).status_code, (401, 200))
        self.assertEqual(c.signup().status_code, 201)  # table still there

    def test_lockout_after_repeated_failures(self):
        c = Client(lockout_threshold=3)
        c.signup()
        for _ in range(3):
            self.assertEqual(c.login("sara@example.com", "wrong-password-here").status_code, 401)
        self.assertEqual(c.login("sara@example.com", "correct-horse-battery").status_code, 401)  # correct pw, still locked

    def test_session_idle_and_absolute_expiry(self):
        import time
        c = Client()
        c.signup()
        db = c.app.extensions["kpt"].database()
        db.execute("UPDATE sessions SET last_seen_at = ?", (int(time.time()) - 10_000,))
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])
        c.login("sara@example.com", "correct-horse-battery")
        db.execute("UPDATE sessions SET expires_at = ?", (int(time.time()) - 1,))
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])

    def test_login_rate_limit(self):
        c = Client(login_rate_limit_per_min=2)
        codes = [c.login("x@example.com", "wrong-password-here").status_code for _ in range(3)]
        self.assertEqual(codes, [401, 401, 429])


class AdminLoginTests(unittest.TestCase):
    def test_wrong_password_goes_to_nice_try_without_session(self):
        c = Client()
        bodies = set()
        for pw in ("wrong-one", "wrong-two", ""):
            r = c.login("admin_001", pw) if pw else c.login("admin_001", "x")
            self.assertEqual((r.status_code, r.get_json()), (200, {"redirect": "/nice-try"}))
            self.assertFalse([h for h in r.headers.getlist("Set-Cookie") if "session" in h])
            bodies.add(r.get_data())
        self.assertEqual(len(bodies), 1)
        self.assertIsNone(c.get("/api/v1/auth/me").get_json()["user"])
        db = c.app.extensions["kpt"].database()
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM login_events WHERE identifier='admin_001' AND success=0")["n"], 3)
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM sessions")["n"], 0)

    def test_locked_admin_still_gets_the_same_joke_even_with_right_password(self):
        c = Client(lockout_threshold=2)
        for _ in range(2):
            c.login("admin_001", "wrong")
        self.assertEqual(c.login("admin_001", ADMIN_PW).get_json(), {"redirect": "/nice-try"})

    def test_correct_password_reaches_admin_and_normal_user_does_not(self):
        c = Client()
        self.assertEqual(c.get("/admin").status_code, 302)  # anonymous
        r = c.login("admin_001", ADMIN_PW)
        self.assertEqual((r.status_code, r.get_json()["redirect"]), (200, "/admin"))
        self.assertEqual(c.get("/admin").status_code, 200)
        user = Client()
        user.signup()
        self.assertEqual(user.get("/admin").status_code, 302)

    def test_admin_disabled_without_env_password(self):
        c = Client(admin_001_password=None)
        self.assertEqual(c.login("admin_001", "admin_001").get_json(), {"redirect": "/nice-try"})

    def test_production_refuses_weak_admin_password_and_forces_change(self):
        weak = Client(app_env="production", database_url=None, admin_001_password="admin_001", local_db_path=":memory:")
        # production without DATABASE_URL: accounts unavailable (503), never a silent in-memory DB
        self.assertEqual(weak.login("admin_001", "admin_001").status_code, 503)
        from backend.db import open_database
        from backend.db.seed import seed_admin
        s = dataclasses.replace(Settings.from_env(), app_env="production")
        db = open_database(None)
        self.assertEqual(seed_admin(db, dataclasses.replace(s, admin_001_password="admin_001")), "refused_weak_password")
        self.assertEqual(seed_admin(db, dataclasses.replace(s, admin_001_password="Tr1cky-long-passphrase!")), "created")
        self.assertEqual(db.one("SELECT must_change_password AS m FROM users WHERE username='admin_001'")["m"], 1)

    def test_plaintext_default_password_is_not_in_the_repo(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[2]
        needle = 'ADMIN_001_PASSWORD=' + 'admin' + '_001'
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".js", ".html", ".css", ".json", ".example"} and ".local" not in p.parts \
                    and "node_modules" not in p.parts and p.name != "test_auth.py":
                self.assertNotIn(needle, p.read_text(encoding="utf-8", errors="ignore"), str(p))


class AdminApiTests(unittest.TestCase):
    ROUTES = [("get", "/api/v1/admin/users"), ("get", "/api/v1/admin/login-events"), ("get", "/api/v1/admin/sessions"),
              ("post", "/api/v1/admin/users/" + "0" * 32 + "/status"), ("post", "/api/v1/admin/users/" + "0" * 32 + "/role"),
              ("post", "/api/v1/admin/users/" + "0" * 32 + "/logout")]

    def hit(self, c, method, path):
        return c.get(path) if method == "get" else c.post(path, {})

    def test_anonymous_gets_401_and_normal_user_gets_403_everywhere(self):
        anon, user = Client(), Client()
        user.signup()
        for m, p in self.ROUTES:
            self.assertEqual(self.hit(anon, m, p).status_code, 401, p)
            self.assertEqual(self.hit(user, m, p).status_code, 403, p)

    def test_admin_can_manage_users_with_reauth_and_audit(self):
        c = Client()
        c.login("admin_001", ADMIN_PW)
        other = Client()
        # share one DB: reuse admin app for the second user
        other.app, other.c = c.app, c.app.test_client()
        other.token = other.c.get("/api/v1/auth/csrf", base_url=BASE).get_json()["csrf_token"]
        uid = other.signup().get_json()["user"]["id"]
        listing = c.get("/api/v1/admin/users?q=sara").get_json()
        self.assertEqual(listing["total"], 1)
        self.assertNotIn("scrypt", str(listing))
        self.assertNotIn("password_hash", str(listing))
        bad = c.post(f"/api/v1/admin/users/{uid}/status", {"status": "disabled", "password": "nope"})
        self.assertEqual(bad.get_json()["code"], "reauth_failed")
        self.assertEqual(c.post(f"/api/v1/admin/users/{uid}/status", {"status": "disabled", "password": ADMIN_PW}).status_code, 200)
        self.assertIsNone(other.get("/api/v1/auth/me").get_json()["user"])  # sessions revoked
        self.assertEqual(other.login("sara@example.com", "correct-horse-battery").status_code, 401)
        self.assertEqual(c.post("/api/v1/admin/users/nothex/role", {"role": "admin", "password": ADMIN_PW}).status_code, 404)
        n = c.app.extensions["kpt"].database().one("SELECT COUNT(*) AS n FROM audit_log WHERE action='user_disabled'")["n"]
        self.assertEqual(n, 1)

    def test_admin_cannot_demote_self(self):
        c = Client()
        me = c.login("admin_001", ADMIN_PW).get_json()["user"]["id"]
        r = c.post(f"/api/v1/admin/users/{me}/role", {"role": "user", "password": ADMIN_PW})
        self.assertEqual(r.get_json()["code"], "self_action")


class VerificationAuthTests(unittest.TestCase):
    def test_owner_check_requires_login_and_csrf(self):
        c = Client()
        body = {"property_id": "DEMO-KPT-8103", "owner_name": "Rahim Mahsud"}
        self.assertEqual(c.post("/api/v1/verification/check", body).status_code, 401)
        c.signup()
        self.assertEqual(c.post("/api/v1/verification/check", body).get_json()["result"], "match")
        self.assertEqual(c.post("/api/v1/verification/check", body, token=None).status_code, 403)

    def test_no_pii_or_secrets_in_cookie_values(self):
        c = Client()
        r = c.signup()
        for h in r.headers.getlist("Set-Cookie"):
            value = h.split("=", 1)[1].split(";")[0]
            for pii in ("sara", "Khan", "example.com", "correct-horse"):
                self.assertNotIn(pii, value)


if __name__ == "__main__":
    unittest.main()


class GoogleTests(unittest.TestCase):
    """Google sign-in with a fake verifier (no network). The real verifier is google-auth's verify_oauth2_token."""
    CID = "test-client.apps.googleusercontent.com"

    def setUp(self):
        self.cl = Client(google_client_id=self.CID, admin_emails=("boss@example.com",))
        self.claims = {}
        kpt = self.cl.app.extensions["kpt"]
        kpt.google_verifier = lambda cred, cid: {**self.claims, **({"_bad": True} if cred == "bad" else {})} if cred != "raise" else (_ for _ in ()).throw(ValueError("bad sig"))

    def _claims(self, nonce, **kw):
        base = {"aud": self.CID, "iss": "https://accounts.google.com", "exp": time.time() + 600, "sub": "g-123",
                "email": "sara@example.com", "email_verified": True, "name": "Sara Khan", "nonce": nonce}
        return {**base, **kw}

    def _login(self, **kw):
        cfg = self.cl.get("/api/v1/auth/google/config").get_json()
        self.assertTrue(cfg["configured"]); self.assertEqual(cfg["client_id"], self.CID)
        self.claims = self._claims(cfg["nonce"], **kw)
        return self.cl.post("/api/v1/auth/google", {"credential": "tok"}), cfg["nonce"]

    def test_unconfigured_is_503_and_never_signs_in(self):
        cl = Client(google_client_id=None)   # explicitly unconfigured, whatever the environment or .env says
        self.assertEqual(cl.get("/api/v1/auth/google/config").get_json(), {"configured": False})
        r = cl.post("/api/v1/auth/google", {"credential": "x"})
        self.assertEqual((r.status_code, r.get_json()["code"]), (503, "google_not_configured"))
        self.assertIsNone(cl.get("/api/v1/auth/me").get_json()["user"])

    def test_creates_user_and_session(self):
        r, _ = self._login()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.cl.get("/api/v1/auth/me").get_json()["user"]["name"], "Sara Khan")
        db = self.cl.app.extensions["kpt"].database()
        u = db.one("SELECT * FROM users WHERE email = ?", ("sara@example.com",))
        self.assertEqual((u["method"], u["role"], u["password_hash"], u["google_sub"]), ("google", "user", None, "g-123"))
        self.assertTrue(db.one("SELECT 1 AS x FROM login_events WHERE method = 'google' AND success = 1"))

    def test_nonce_is_single_use_and_must_be_ours(self):
        r, nonce = self._login()
        self.assertEqual(r.status_code, 200)
        self.claims = self._claims(nonce)  # replay of the same nonce
        self.assertEqual(self.cl.post("/api/v1/auth/google", {"credential": "tok"}).status_code, 401)
        self.claims = self._claims("never-issued")
        self.assertEqual(self.cl.post("/api/v1/auth/google", {"credential": "tok"}).status_code, 401)

    def test_rejects_wrong_audience_issuer_expiry_unverified_email_and_bad_signature(self):
        for kw in ({"aud": "other"}, {"iss": "https://evil.example"}, {"exp": time.time() - 5}):
            cl = Client(google_client_id=self.CID); kpt = cl.app.extensions["kpt"]
            nonce = cl.get("/api/v1/auth/google/config").get_json()["nonce"]
            claims = self._claims(nonce, **kw); kpt.google_verifier = lambda c, i, claims=claims: claims
            self.assertEqual(cl.post("/api/v1/auth/google", {"credential": "t"}).status_code, 401, kw)
        r, _ = self._login(email_verified=False)
        self.assertEqual((r.status_code, r.get_json()["code"]), (401, "google_unverified"))
        self.assertEqual(self.cl.post("/api/v1/auth/google", {"credential": "raise"}).status_code, 401)
        self.assertIsNone(self.cl.get("/api/v1/auth/me").get_json()["user"])

    def test_failed_google_sign_in_never_sets_a_session(self):
        """Every failure path: no session cookie, no session row, /auth/me stays empty (fake verifier)."""
        db = self.cl.app.extensions["kpt"].database()
        cfg = self.cl.get("/api/v1/auth/google/config").get_json()
        for cred, claims in (("bad", {}), ("raise", {}), ("tok", self._claims("never-issued")), ("tok", self._claims(cfg["nonce"], aud="other")),
                             ("tok", self._claims(cfg["nonce"], email_verified=False))):
            self.claims = claims
            r = self.cl.post("/api/v1/auth/google", {"credential": cred})
            self.assertIn(r.status_code, (401,), (cred, r.get_json()))
            self.assertFalse([h for h in r.headers.getlist("Set-Cookie") if "session" in h or "remember" in h], cred)
            cfg = self.cl.get("/api/v1/auth/google/config").get_json()  # a fresh nonce for the next attempt
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM sessions")["n"], 0)
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM users WHERE method='google'")["n"], 0)
        self.assertIsNone(self.cl.get("/api/v1/auth/me").get_json()["user"])

    def test_missing_or_non_text_credential_is_400(self):
        for body in ({}, {"credential": ""}, {"credential": 5}, {"credential": None}):
            r = self.cl.post("/api/v1/auth/google", body)
            self.assertEqual(r.status_code, 400, body)
            self.assertFalse([h for h in r.headers.getlist("Set-Cookie") if "session" in h])

    def test_default_verifier_without_google_auth_is_503_not_a_login(self):
        """Environment without google-auth (as in this sandbox): clear 503, never a session. Import failure is forced."""
        import sys
        from unittest import mock
        from backend.services import google_oauth
        from backend.errors import ApiError
        with mock.patch.dict(sys.modules, {"google.auth.transport": None, "google.oauth2": None}):
            with self.assertRaises(ApiError) as ctx:
                google_oauth._default_verifier("tok", self.CID)
        self.assertEqual((ctx.exception.status, ctx.exception.code), (503, "google_unavailable"))

    def test_linking_clears_password_and_revokes_sessions(self):
        self.cl.signup()  # an (unverified) password account for the same email, with a live session
        self.assertEqual(self.cl.get("/api/v1/auth/me").get_json()["user"]["name"], "Sara Khan")
        attacker = self.cl.app.test_client()
        attacker.set_cookie("__Host-kpt_session", self.cl.c.get_cookie("__Host-kpt_session").value, domain="localhost")
        self.assertIsNotNone(attacker.get("/api/v1/auth/me", base_url=BASE).get_json()["user"], "test setup: stolen cookie works before link")
        r, _ = self._login()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.cl.login("sara@example.com", "correct-horse-battery").status_code, 401, "old password must stop working")
        self.assertEqual(attacker.get("/api/v1/auth/me", base_url=BASE).get_json()["user"] is None, True, "old sessions revoked")
        self.assertEqual(self.cl.app.extensions["kpt"].database().one("SELECT COUNT(*) AS n FROM users")["n"] >= 1, True)

    def test_admin_emails_promote_google_only_never_password_signup(self):
        self.cl.signup(email="boss@example.com", pw="correct-horse-battery", name="Boss")
        db = self.cl.app.extensions["kpt"].database()
        self.assertEqual(db.one("SELECT role FROM users WHERE email = 'boss@example.com'")["role"], "user")
        cl = Client(google_client_id=self.CID, admin_emails=("boss@example.com",)); kpt = cl.app.extensions["kpt"]
        nonce = cl.get("/api/v1/auth/google/config").get_json()["nonce"]
        kpt.google_verifier = lambda c, i: self._claims(nonce, email="boss@example.com", sub="g-boss")
        r = cl.post("/api/v1/auth/google", {"credential": "t"})
        self.assertEqual((r.status_code, r.get_json()["redirect"]), (200, "/admin"))

    def test_disabled_user_and_reserved_admin_cannot_use_google(self):
        self._login()
        db = self.cl.app.extensions["kpt"].database()
        db.execute("UPDATE users SET status = 'disabled' WHERE email = 'sara@example.com'")
        r, _ = self._login()
        self.assertEqual(r.status_code, 401)
        db.execute("UPDATE users SET email = 'admin@example.com' WHERE username = 'admin_001'")
        r, _ = self._login(email="admin@example.com", sub="g-evil")
        self.assertEqual(r.status_code, 401, "admin_001 must never be linked through Google")

    def test_google_endpoints_need_csrf(self):
        self._login()
        self.assertEqual(self.cl.post("/api/v1/auth/google", {"credential": "t"}, token=None).status_code, 403)


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.cl = Client(app_base_url="https://site.example")
        self.sent = []
        self.cl.app.extensions["kpt"].mail_sender = lambda to, subj, text: self.sent.append((to, text)) or True
        self.cl.signup()
        self.cl.post("/api/v1/auth/logout")

    def _token(self):
        text = self.sent[-1][1]
        return text.split("reset=")[1].split()[0]

    def test_same_answer_for_known_and_unknown_email(self):
        a = self.cl.post("/api/v1/auth/forgot", {"email": "sara@example.com"})
        b = self.cl.post("/api/v1/auth/forgot", {"email": "nobody@example.com"})
        self.assertEqual((a.status_code, a.get_json()), (b.status_code, b.get_json()))
        self.assertEqual([to for to, _ in self.sent], ["sara@example.com"])

    def test_reset_flow_single_use_and_revokes_sessions(self):
        self.cl.signup(email="other@example.com", name="Other")  # a live session for a different user must survive
        self.cl.post("/api/v1/auth/forgot", {"email": "sara@example.com"})
        token = self._token()
        self.assertIn("https://site.example/login?reset=", self.sent[-1][1])
        db = self.cl.app.extensions["kpt"].database()
        self.assertIsNone(db.one("SELECT 1 AS x FROM password_resets WHERE id_hash = ?", (token,)), "raw token must not be stored")
        weak = self.cl.post("/api/v1/auth/reset", {"token": token, "new_password": "short"})
        self.assertEqual(weak.status_code, 400)
        ok = self.cl.post("/api/v1/auth/reset", {"token": token, "new_password": "a-brand-new-passphrase"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.cl.post("/api/v1/auth/reset", {"token": token, "new_password": "another-passphrase-1"}).status_code, 400, "single use")
        self.assertEqual(self.cl.login("sara@example.com", "correct-horse-battery").status_code, 401)
        self.assertEqual(self.cl.login("sara@example.com", "a-brand-new-passphrase").status_code, 200)

    def test_expired_and_garbage_tokens_fail_identically(self):
        self.cl.post("/api/v1/auth/forgot", {"email": "sara@example.com"})
        token = self._token()
        self.cl.app.extensions["kpt"].database().execute("UPDATE password_resets SET expires_at = 1")
        bodies = {self.cl.post("/api/v1/auth/reset", {"token": t, "new_password": "a-brand-new-passphrase"}).get_json()["code"] for t in (token, "garbage")}
        self.assertEqual(bodies, {"reset_invalid"})

    def test_admin_001_and_unconfigured_mail(self):
        self.cl.app.extensions["kpt"].database().execute("UPDATE users SET email = 'admin@example.com' WHERE username = 'admin_001'")
        r = self.cl.post("/api/v1/auth/forgot", {"email": "admin@example.com"})
        self.assertEqual((r.status_code, self.sent), (202, []), "admin_001 never gets a reset email")
        cl = Client()
        self.assertEqual(cl.get("/api/v1/auth/features").get_json()["password_reset"], False)
        self.assertEqual(cl.post("/api/v1/auth/forgot", {"email": "sara@example.com"}).status_code, 202)

    def test_reset_requires_csrf(self):
        self.assertEqual(self.cl.post("/api/v1/auth/forgot", {"email": "sara@example.com"}, token=None).status_code, 403)
