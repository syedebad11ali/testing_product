"""Part 2B: consent, remember-me, preference cookie, chat continuity, forget-device, delete-account."""
import json
import pathlib
import re
import unittest
import warnings

warnings.filterwarnings("ignore")

from backend.security import consent  # noqa: E402
from backend.services import prefs  # noqa: E402
from tests.backend.test_api import make_client  # noqa: E402
from tests.backend.test_auth import ADMIN_PW, BASE, Client  # noqa: E402

CONSENT_ALL = "v=1&p=1&a=0"
PW = "correct-horse-battery"


def allow(client, value=CONSENT_ALL):
    client.c.set_cookie("kpt_consent", value, domain="localhost")


def cookie_value(client, name):
    c = client.c.get_cookie(name, domain="localhost")
    return c.value if c else None


def set_cookie_headers(resp):
    return resp.headers.getlist("Set-Cookie")


class ConsentTests(unittest.TestCase):
    def test_parse_accepts_only_current_wellformed_records(self):
        self.assertEqual(consent.parse("v=1&p=1&a=0"), {"version": 1, "preferences": True, "analytics": False})
        self.assertEqual(consent.parse("v%3D1%26p%3D0%26a%3D1")["analytics"], True)  # URL-encoded form from document.cookie
        for bad in ("", "v=2&p=1&a=1", "v=1&p=2&a=0", "garbage", "v=1&p=1", "v=1&p=1&a=0; extra", "v=1&p=1&a=0" * 20):
            self.assertIsNone(consent.parse(bad), bad)


class PrefsTests(unittest.TestCase):
    CASES = [(c["raw"], c["expected"]) for c in json.load(open(pathlib.Path(__file__).resolve().parents[1] / "shared" / "prefs_cases.json", encoding="utf-8"))]  # shared with tests/frontend/cookies.test.js

    def test_sanitize_cases(self):
        for raw, expected in self.CASES:
            self.assertEqual(prefs.sanitize(raw), expected, raw)

    def test_lists_are_capped_and_cookie_stays_small(self):
        out = prefs.sanitize({"recent": [f"P{i}" for i in range(100)], "saved": [f"S{i}" for i in range(100)]})
        self.assertEqual(len(out["recent"]), 20)
        self.assertLessEqual(len(out["saved"]), 30)
        self.assertLess(len(json.dumps(out)), 3000)

    def test_merge_unions_lists_and_prefers_cookie_scalars(self):
        merged = prefs.merge({"theme": "light", "saved": ["A1", "B2"]}, {"theme": "dark", "saved": ["C3", "A1"]})
        self.assertEqual(merged["theme"], "dark")
        self.assertEqual(merged["saved"], ["C3", "A1", "B2"])


class RememberTests(unittest.TestCase):
    def setUp(self):
        self.cl = Client()
        self.signup = self.cl.signup(pw=PW)
        self.cl.post("/api/v1/auth/logout")

    def login(self, remember=True):
        return self.cl.post("/api/v1/auth/login", {"identifier": "sara@example.com", "password": PW, "remember": remember})

    def test_without_consent_nothing_optional_is_set(self):
        r = self.login()
        body = r.get_json()
        self.assertFalse(body["remembered"])
        self.assertIn("Preferences", body["remember_note"])
        self.assertIsNone(cookie_value(self.cl, "__Host-kpt_remember"))

    def test_with_consent_cookie_has_strict_flags_and_no_pii(self):
        allow(self.cl)
        r = self.login()
        self.assertTrue(r.get_json()["remembered"])
        headers = set_cookie_headers(r)
        remember = next(h for h in headers if h.startswith("__Host-kpt_remember="))
        for flag in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=2592000"):
            self.assertIn(flag, remember)
        self.assertNotIn("Domain", remember)
        for h in headers:  # no personal data in any cookie value
            for needle in ("sara", "Sara", "example.com", PW):
                self.assertNotIn(needle, h.split(";")[0])

    def test_stored_validator_is_hashed(self):
        allow(self.cl)
        self.login()
        raw = cookie_value(self.cl, "__Host-kpt_remember")
        selector, validator = raw.split(".")
        row = self.cl.app.extensions["kpt"].database().one("SELECT * FROM remember_tokens WHERE selector = ?", (selector,))
        self.assertNotEqual(row["validator_hash"], validator)
        self.assertNotIn(validator, json.dumps(row))

    def test_returns_after_session_ends_and_rotates(self):
        allow(self.cl)
        self.login()
        first = cookie_value(self.cl, "__Host-kpt_remember")
        self.cl.c.delete_cookie("__Host-kpt_session", domain="localhost")  # browser closed: session cookie gone
        me = self.cl.get("/api/v1/auth/me").get_json()
        self.assertEqual(me["user"]["name"], "Sara Khan")
        second = cookie_value(self.cl, "__Host-kpt_remember")
        self.assertNotEqual(first, second)
        self.assertIsNotNone(cookie_value(self.cl, "__Host-kpt_session"))

    def test_replaying_an_old_token_revokes_everything(self):
        allow(self.cl)
        self.login()
        old = cookie_value(self.cl, "__Host-kpt_remember")
        self.cl.c.delete_cookie("__Host-kpt_session", domain="localhost")
        self.cl.get("/api/v1/auth/me")  # legitimate use: rotates
        db = self.cl.app.extensions["kpt"].database()
        db.execute("UPDATE remember_tokens SET rotated_at = rotated_at - 100 WHERE rotated_at IS NOT NULL")  # outside the grace window
        thief = Client.__new__(Client)
        thief.app, thief.c = self.cl.app, self.cl.app.test_client()
        thief.c.set_cookie("kpt_consent", CONSENT_ALL, domain="localhost")
        thief.c.set_cookie("__Host-kpt_remember", old, domain="localhost")
        self.assertIsNone(thief.c.get("/api/v1/auth/me", base_url=BASE).get_json()["user"])
        # the real user's newest token and session are dead too: a fresh login is forced
        self.cl.c.delete_cookie("__Host-kpt_session", domain="localhost")
        self.assertIsNone(self.cl.get("/api/v1/auth/me").get_json()["user"])
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM remember_tokens WHERE revoked_at IS NULL")["n"], 0)
        self.assertTrue(db.one("SELECT 1 AS x FROM audit_log WHERE action = 'remember_reuse_detected'"))

    def test_parallel_request_inside_grace_window_is_not_treated_as_theft(self):
        allow(self.cl)
        self.login()
        old = cookie_value(self.cl, "__Host-kpt_remember")
        self.cl.c.delete_cookie("__Host-kpt_session", domain="localhost")
        self.cl.get("/api/v1/auth/me")
        racer = self.cl.app.test_client()
        racer.set_cookie("kpt_consent", CONSENT_ALL, domain="localhost")
        racer.set_cookie("__Host-kpt_remember", old, domain="localhost")
        self.assertIsNone(racer.get("/api/v1/auth/me", base_url=BASE).get_json()["user"])
        self.cl.c.delete_cookie("__Host-kpt_session", domain="localhost")
        self.assertIsNotNone(self.cl.get("/api/v1/auth/me").get_json()["user"])  # real user still fine

    def test_tampered_or_expired_tokens_are_rejected(self):
        allow(self.cl)
        self.login()
        raw = cookie_value(self.cl, "__Host-kpt_remember")
        selector = raw.split(".")[0]
        self.cl.c.delete_cookie("__Host-kpt_session", domain="localhost")
        self.cl.c.set_cookie("__Host-kpt_remember", selector + ".A" * 5 + "x" * 30, domain="localhost")
        self.assertIsNone(self.cl.get("/api/v1/auth/me").get_json()["user"])
        self.cl.c.set_cookie("__Host-kpt_remember", raw, domain="localhost")
        self.cl.app.extensions["kpt"].database().execute("UPDATE remember_tokens SET expires_at = 1")
        self.assertIsNone(self.cl.get("/api/v1/auth/me").get_json()["user"])

    def test_logout_ends_this_device_only_and_logout_all_ends_every_device(self):
        allow(self.cl)
        self.login()
        other = Client.__new__(Client)
        other.app, other.c = self.cl.app, self.cl.app.test_client()
        other.token = other.c.get("/api/v1/auth/csrf", base_url=BASE).get_json()["csrf_token"]
        other.c.set_cookie("kpt_consent", CONSENT_ALL, domain="localhost")
        other.login("sara@example.com", PW)
        self.assertTrue(other.post("/api/v1/auth/login", {"identifier": "sara@example.com", "password": PW, "remember": True}).get_json()["remembered"])
        self.assertEqual(len(self.cl.get("/api/v1/auth/devices").get_json()["devices"]), 2)
        self.assertEqual([d["current"] for d in self.cl.get("/api/v1/auth/devices").get_json()["devices"]].count(True), 1)
        self.cl.post("/api/v1/auth/logout")
        self.assertIsNone(cookie_value(self.cl, "__Host-kpt_remember"))
        self.assertEqual(len(other.get("/api/v1/auth/devices").get_json()["devices"]), 1)  # other device untouched
        other.post("/api/v1/auth/logout-all")
        self.assertEqual(self.cl.app.extensions["kpt"].database().one("SELECT COUNT(*) AS n FROM remember_tokens WHERE revoked_at IS NULL")["n"], 0)

    def test_revoke_one_device_requires_ownership(self):
        allow(self.cl)
        self.login()
        dev = self.cl.get("/api/v1/auth/devices").get_json()["devices"][0]
        self.assertEqual(self.cl.post("/api/v1/auth/devices/revoke", {"id": "z" * 32}).status_code, 400)
        self.assertEqual(self.cl.post("/api/v1/auth/devices/revoke", {"id": "0" * 32}).status_code, 404)
        self.assertEqual(self.cl.post("/api/v1/auth/devices/revoke", {"id": dev["id"]}).status_code, 200)

    def test_password_change_revokes_remember_tokens(self):
        allow(self.cl)
        self.login()
        self.cl.post("/api/v1/auth/change-password", {"current_password": PW, "new_password": "another-long-passphrase-9"})
        self.assertEqual(self.cl.app.extensions["kpt"].database().one("SELECT COUNT(*) AS n FROM remember_tokens WHERE revoked_at IS NULL")["n"], 0)

    def test_admin_never_gets_a_remember_token(self):
        allow(self.cl)
        r = self.cl.post("/api/v1/auth/login", {"identifier": "admin_001", "password": ADMIN_PW, "remember": True})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["remembered"])
        self.assertIsNone(cookie_value(self.cl, "__Host-kpt_remember"))


class AccountApiTests(unittest.TestCase):
    def setUp(self):
        self.cl = Client()
        self.cl.signup(pw=PW)

    def test_prefs_roundtrip_is_sanitised_and_merged(self):
        r = self.cl.c.put("/api/v1/auth/prefs", json={"prefs": {"theme": "dark", "saved": ["A1"], "email": "x@y.z"}},
                          headers={"Origin": BASE, "X-CSRF-Token": self.cl.token}, base_url=BASE)
        self.assertEqual(r.get_json()["prefs"], {"theme": "dark", "saved": ["A1"]})
        r = self.cl.c.put("/api/v1/auth/prefs", json={"prefs": {"saved": ["B2"]}}, headers={"Origin": BASE, "X-CSRF-Token": self.cl.token}, base_url=BASE)
        self.assertEqual(r.get_json()["prefs"]["saved"], ["B2", "A1"])
        self.assertEqual(self.cl.get("/api/v1/auth/prefs").get_json()["prefs"]["theme"], "dark")

    def test_prefs_require_login_and_csrf(self):
        anon = Client()
        self.assertEqual(anon.get("/api/v1/auth/prefs").status_code, 401)
        r = self.cl.c.put("/api/v1/auth/prefs", json={"prefs": {}}, base_url=BASE, headers={"Origin": BASE})
        self.assertEqual(r.status_code, 403)

    def test_forget_device_clears_remember_and_chat_state(self):
        allow(self.cl)
        self.cl.post("/api/v1/auth/logout")
        self.cl.post("/api/v1/auth/login", {"identifier": "sara@example.com", "password": PW, "remember": True})
        self.cl.c.post("/api/v1/chat", json={"message": "prices in Gulshan"}, base_url=BASE)
        self.assertIsNotNone(cookie_value(self.cl, "__Host-kpt_chat"))
        r = self.cl.post("/api/v1/auth/forget-device")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(cookie_value(self.cl, "__Host-kpt_remember"))
        self.assertIsNone(cookie_value(self.cl, "__Host-kpt_chat"))
        self.assertEqual(self.cl.app.extensions["kpt"].database().one("SELECT COUNT(*) AS n FROM chat_sessions")["n"], 0)

    def test_delete_account_needs_password_and_confirmation(self):
        self.assertEqual(self.cl.post("/api/v1/auth/delete-account", {"password": PW}).status_code, 400)
        self.assertEqual(self.cl.post("/api/v1/auth/delete-account", {"password": "nope-nope-nope", "confirm": "DELETE"}).status_code, 403)
        self.assertEqual(self.cl.post("/api/v1/auth/delete-account", {"password": PW, "confirm": "DELETE"}).status_code, 200)
        db = self.cl.app.extensions["kpt"].database()
        self.assertIsNone(db.one("SELECT 1 AS x FROM users WHERE email = 'sara@example.com'"))
        self.assertFalse(db.one("SELECT 1 AS x FROM login_events WHERE identifier LIKE '%sara%'"))
        self.assertIsNone(self.cl.get("/api/v1/auth/me").get_json()["user"])

    def test_admin_cannot_self_delete(self):
        admin = Client()
        admin.login("admin_001", ADMIN_PW)
        self.assertEqual(admin.post("/api/v1/auth/delete-account", {"password": ADMIN_PW, "confirm": "DELETE"}).status_code, 403)


class ChatContinuityTests(unittest.TestCase):
    def setUp(self):
        self.cl = Client()

    def chat(self, message, **extra):
        return self.cl.c.post("/api/v1/chat", json={"message": message, **extra}, base_url=BASE)

    def test_no_chat_cookie_before_consent_or_after_rejecting(self):
        r = self.chat("hello")
        self.assertFalse(r.get_json()["continuity"])
        self.assertFalse([h for h in set_cookie_headers(r) if "kpt_chat" in h])
        allow(self.cl, "v=1&p=0&a=0")
        r = self.chat("hello")
        self.assertFalse([h for h in set_cookie_headers(r) if "kpt_chat" in h])
        self.assertEqual(self.cl.get("/api/v1/chat/session").get_json()["history"], [])

    def test_chat_cookie_flags_and_context_survives_a_refresh(self):
        allow(self.cl)
        r = self.chat("prices of houses in Gulshan")
        header = next(h for h in set_cookie_headers(r) if "kpt_chat=" in h)
        for flag in ("__Host-kpt_chat=", "HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=604800"):
            self.assertIn(flag, header)
        self.assertRegex(cookie_value(self.cl, "__Host-kpt_chat"), r"^[0-9a-f]{32}$")
        # a different server instance (cold start) shares only the database
        kpt = self.cl.app.extensions["kpt"]
        kpt._service = None
        kpt.chat_service()
        snap = self.cl.get("/api/v1/chat/session").get_json()
        self.assertTrue(snap["continuity"])
        self.assertEqual(snap["history"][0]["text"], "prices of houses in Gulshan")
        self.assertTrue(snap["memory"])
        self.assertIn("Welcome back", snap["welcome"]["text"])
        self.assertNotIn(",", snap["welcome"]["text"])  # anonymous: never a name

    def test_start_over_clears_stored_conversation(self):
        allow(self.cl)
        self.chat("prices of houses in Gulshan")
        self.chat("hello", reset=True)
        history = self.cl.get("/api/v1/chat/session").get_json()["history"]
        self.assertEqual([m["text"] for m in history if m["role"] == "user"], ["hello"])

    def test_signed_in_visitor_is_greeted_by_first_name_and_anonymous_by_last_viewed(self):
        allow(self.cl)
        self.cl.signup(pw=PW)
        self.chat("hello there")
        self.assertIn("Welcome back, Sara", self.cl.get("/api/v1/chat/session").get_json()["welcome"]["text"])
        anon = Client()
        allow(anon)
        anon.c.post("/api/v1/chat", json={"message": "hello"}, base_url=BASE)
        pid = anon.app.extensions["kpt"].chat_service().store.df.property_id.iloc[0]
        anon.c.set_cookie("kpt_prefs", json.dumps({"recent": [pid]}), domain="localhost")
        w = anon.get("/api/v1/chat/session").get_json()["welcome"]
        self.assertEqual(w["text"].split("!")[0], "Welcome back")
        self.assertIn("Continue with", w["chips"][0]["label"])

    def test_tampered_prefs_cookie_is_ignored(self):
        allow(self.cl)
        self.chat("hello")
        self.cl.c.set_cookie("kpt_prefs", "%7Bnot json", domain="localhost")
        self.assertEqual(self.cl.get("/api/v1/chat/session").status_code, 200)
        self.cl.c.set_cookie("kpt_prefs", json.dumps({"recent": ["<img src=x>", "../../etc"]}), domain="localhost")
        w = self.cl.get("/api/v1/chat/session").get_json()["welcome"]
        self.assertNotIn("<", json.dumps(w))

    def test_legacy_embed_without_cookies_still_works(self):
        r = self.cl.c.post("/api/chat", json={"message": "hello", "session_id": "embed-123"}, base_url=BASE)
        self.assertEqual(r.status_code, 200)
        self.assertIn("reply", r.get_json())


class CookieInventoryTests(unittest.TestCase):
    """Every Set-Cookie the server emits has deliberate flags (docs/COOKIES.md lists them)."""

    JS_READABLE = {"__Host-kpt_csrf"}

    def test_all_cookies_have_secure_samesite_path_and_httponly_unless_js_needs_them(self):
        cl = Client()
        allow(cl)
        seen = []
        for resp in (cl.get("/api/v1/auth/csrf"), cl.signup(pw=PW), cl.c.post("/api/v1/chat", json={"message": "hi"}, base_url=BASE),
                     cl.post("/api/v1/auth/logout"), cl.login("sara@example.com", PW)):
            seen += set_cookie_headers(resp)
        self.assertTrue(seen)
        for header in seen:
            name = header.split("=")[0]
            self.assertTrue(name.startswith("__Host-"), header)
            for flag in ("Secure", "SameSite=Lax", "Path=/"):
                self.assertIn(flag, header)
            self.assertNotIn("Domain", header)
            if name not in self.JS_READABLE:
                self.assertIn("HttpOnly", header, header)


class PrivacyPageTests(unittest.TestCase):
    ROOT = pathlib.Path(__file__).resolve().parents[2]

    def test_cookie_table_matches_docs_and_page(self):
        doc = (self.ROOT / "docs" / "COOKIES.md").read_text(encoding="utf-8")
        page = (self.ROOT / "frontend" / "privacy.html").read_text(encoding="utf-8")
        in_doc = set(re.findall(r"^\| `([A-Za-z_-]+)` \|", doc, re.M))
        in_page = set(re.findall(r"<td><code>([A-Za-z_-]+)</code></td>", page))
        self.assertEqual(in_doc, in_page)
        self.assertTrue({"kpt_consent", "kpt_prefs", "__Host-kpt_remember", "__Host-kpt_chat"} <= in_page)

    def test_page_routes_and_banner_assets(self):
        c = make_client()
        for path in ("/privacy", "/privacy.html", "/css/consent.css", "/js/consent-banner.js", "/js/core/cookies.js", "/js/core/prefs.js"):
            self.assertEqual(c.get(path).status_code, 200, path)
        for page in ("index.html", "login.html", "admin.html", "privacy.html"):
            html = (self.ROOT / "frontend" / page).read_text(encoding="utf-8")
            self.assertIn("consent.css", html, page)
            self.assertTrue("consent-banner.js" in html or page in ("index.html", "login.html"), page)
        # T5a: the banner is asked for only after sign-in / guest entry, never on the entry pages
        for page in ("login.html", "developer-login.html", "nice-try.html"):
            html = (self.ROOT / "frontend" / page).read_text(encoding="utf-8")
            self.assertNotIn("consent-banner.js", html, page)
            self.assertNotIn("consent.js", html, page)
        for page in ("listings.html", "messages.html", "admin.html", "privacy.html"):
            self.assertIn("consent-banner.js", (self.ROOT / "frontend" / page).read_text(encoding="utf-8"), page)
        self.assertIn("initConsent", (self.ROOT / "frontend/js/main.js").read_text(encoding="utf-8"))

    def test_login_has_remember_me_and_sends_it(self):
        self.assertIn('id="login-remember"', (self.ROOT / "frontend/login.html").read_text(encoding="utf-8"))
        self.assertIn("remember:", (self.ROOT / "frontend/js/auth-page.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
