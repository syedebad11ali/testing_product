"""T4: login-first routing. The application pages are served only with a real server-side session (user, guest or admin);
everything a visitor needs to sign in stays public. Enforced by the server, not by frontend redirects."""
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_auth import ADMIN_PW, Client  # noqa: E402

APP_PAGES = ["/", "/index.html", "/listings", "/listings.html"]
PUBLIC_PAGES = ["/login", "/signup", "/developer-login", "/nice-try", "/privacy", "/robots.txt", "/sitemap.xml"]


def guest():
    c = Client(app_env="development")
    assert c.post("/api/v1/auth/guest", {}).status_code == 201
    return c


def user():
    c = Client(app_env="development")
    assert c.signup().status_code == 201
    return c


def admin():
    c = Client(app_env="development")
    r = c.post("/api/v1/auth/developer-login", {"identifier": "admin_001", "password": ADMIN_PW})
    assert r.status_code == 200, r.get_json()
    return c


class AnonymousTests(unittest.TestCase):
    def setUp(self):
        self.c = Client(app_env="development")

    def test_app_pages_redirect_to_login(self):
        for path in APP_PAGES:
            r = self.c.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertTrue(r.headers["Location"].startswith("/login"), (path, r.headers["Location"]))

    def test_listings_keeps_its_return_path_and_the_home_page_adds_none(self):
        self.assertEqual(self.c.get("/listings").headers["Location"], "/login?next=/listings")
        self.assertEqual(self.c.get("/listings.html").headers["Location"], "/login?next=/listings")
        self.assertEqual(self.c.get("/").headers["Location"], "/login")
        self.assertEqual(self.c.get("/index.html").headers["Location"], "/login")

    def test_request_input_is_never_echoed_into_the_redirect(self):
        for path in ("/?next=//evil.example", "/listings?next=https://evil.example", "/index.html?next=/\\evil.example"):
            loc = self.c.get(path).headers["Location"]
            self.assertIn(loc, ("/login", "/login?next=/listings"), path)
            self.assertNotIn("evil", loc)

    def test_everything_needed_to_sign_in_stays_public(self):
        for path in PUBLIC_PAGES:
            self.assertEqual(self.c.get(path).status_code, 200, path)
        for path in ("/css/login.css", "/js/auth-page.js", "/js/developer-login.js"):
            self.assertEqual(self.c.get(path).status_code, 200, path)
        self.assertEqual(self.c.get("/api/v1/auth/features").status_code, 200)
        self.assertEqual(self.c.get("/api/v1/auth/csrf").status_code, 200)
        self.assertIsNone(self.c.get("/api/v1/auth/me").get_json()["user"])

    def test_a_forged_or_garbage_session_cookie_gets_nothing(self):
        for value in ("garbage", "a" * 43, ""):
            c = Client(app_env="development")
            c.c.set_cookie("session", value, domain="localhost")
            self.assertEqual(c.get("/").status_code, 302, value)

    def test_private_and_admin_pages_still_redirect(self):
        for path in ("/messages", "/admin"):
            self.assertEqual(self.c.get(path).status_code, 302, path)
        self.assertEqual(self.c.get("/api/v1/admin/users").status_code, 401)
        self.assertEqual(self.c.get("/api/v1/messages/conversations").status_code, 401)


class SessionTests(unittest.TestCase):
    def test_every_kind_of_valid_session_reaches_the_app_pages(self):
        for name, make in (("user", user), ("guest", guest), ("admin", admin)):
            c = make()
            for path in APP_PAGES:
                r = c.get(path)
                self.assertEqual(r.status_code, 200, (name, path))
                self.assertIn(b"<html", r.data[:400].lower(), (name, path))

    def test_gated_pages_are_marked_private_for_caches(self):
        r = guest().get("/")
        self.assertEqual(r.headers["Cache-Control"], "private, no-cache")
        self.assertIn("Cookie", r.headers["Vary"])

    def test_guest_is_not_promoted_by_visiting_pages(self):
        c = guest()
        for path in APP_PAGES + ["/login"]:
            c.get(path)
        self.assertEqual(c.get("/api/v1/auth/me").get_json()["user"]["role"], "guest")
        self.assertEqual(c.get("/admin").status_code, 302)                       # guests are not admins
        self.assertEqual(c.get("/messages").status_code, 302)                    # and cannot use messaging pages
        self.assertEqual(c.get("/api/v1/admin/users").status_code, 403)

    def test_user_cannot_open_the_admin_page_or_api(self):
        c = user()
        self.assertEqual(c.get("/admin").status_code, 302)
        self.assertEqual(c.get("/api/v1/admin/users").status_code, 403)

    def test_admin_still_reaches_the_admin_page_and_api(self):
        c = admin()
        self.assertEqual(c.get("/admin").status_code, 200)
        self.assertEqual(c.get("/api/v1/admin/users").status_code, 200)

    def test_logout_ends_access_for_users_guests_and_admins(self):
        for make in (user, guest, admin):
            c = make()
            self.assertEqual(c.get("/").status_code, 200)
            self.assertEqual(c.post("/api/v1/auth/logout", {}).status_code, 200)
            self.assertEqual(c.get("/").status_code, 302)
            self.assertEqual(c.get("/listings").status_code, 302)


class GuestEntryTests(unittest.TestCase):
    """The Guest button posts to /auth/guest with the CSRF token and the Origin header; check the contract it relies on."""
    def test_guest_endpoint_contract(self):
        c = Client(app_env="development")
        r = c.post("/api/v1/auth/guest", {})
        body = r.get_json()
        self.assertEqual(r.status_code, 201)
        self.assertEqual((body["ok"], body["user"]["role"], body["redirect"]), (True, "guest", "/"))
        self.assertNotIn("admin", str(body).lower().replace("administrator", ""))

    def test_guest_endpoint_requires_the_csrf_token(self):
        c = Client(app_env="development")
        self.assertEqual(c.post("/api/v1/auth/guest", {}, token=None).status_code, 403)
        self.assertEqual(c.c.get("/").status_code, 302)                          # and no session was created

    def test_guest_limit_is_reported_as_429_guest_limit(self):
        c = Client(app_env="development", guest_max_active_per_ip=2)
        self.assertEqual(c.post("/api/v1/auth/guest", {}).status_code, 201)
        other = Client(app_env="development", guest_max_active_per_ip=2)
        other.app = c.app; other.c = c.app.test_client(); other.token = other.c.get("/api/v1/auth/csrf", base_url="https://localhost").get_json()["csrf_token"]
        self.assertEqual(other.post("/api/v1/auth/guest", {}).status_code, 201)
        third = c.app.test_client()
        tok = third.get("/api/v1/auth/csrf", base_url="https://localhost").get_json()["csrf_token"]
        r = third.post("/api/v1/auth/guest", json={}, headers={"Origin": "https://localhost", "X-CSRF-Token": tok}, base_url="https://localhost")
        self.assertEqual((r.status_code, r.get_json()["code"]), (429, "guest_limit"))
        self.assertEqual(third.get("/", base_url="https://localhost").status_code, 302)   # the refused visitor got no session

    def test_normal_and_developer_login_still_open_the_app(self):
        c = Client(app_env="development")
        c.signup()
        c.post("/api/v1/auth/logout", {})
        self.assertEqual(c.get("/").status_code, 302)
        self.assertEqual(c.login("sara@example.com", "correct-horse-battery").status_code, 200)
        self.assertEqual(c.get("/").status_code, 200)
        # An invalid Developer Login is answered with the Nice Try redirect and must not start a session.
        wrong = Client(app_env="development")
        bad = wrong.post("/api/v1/auth/developer-login", {"identifier": "admin_001", "password": "wrong-password-xx"})
        self.assertEqual(bad.get_json().get("redirect"), "/nice-try")
        self.assertFalse([h for h in bad.headers.getlist("Set-Cookie") if h.startswith("session=")])
        self.assertEqual(wrong.get("/").status_code, 302)
        self.assertEqual(wrong.get("/admin").status_code, 302)


if __name__ == "__main__":
    unittest.main()
