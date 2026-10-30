"""Browser test for T4: login-first routing and the Continue as Guest experience. Run:  python tests/browser/guest_entry_test.py

Covers: signed-out visitors are sent to the login page (home page and listings, return path kept for listings); the real
"Continue as Guest" button creates a restricted server-side guest session; the header shows a Guest indicator; the listings page
offers browsing but no create-listing form, personal listings or Messages link; the browser really gets 403 from private and admin
APIs; guests reaching /messages or /admin land on a usable login form (not "signed in"); the guest-limit message; Exit guest logs out.
Throwaway database; needs a browser so it is not part of `npm run test:all`."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def start(port, tmp, **extra):
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "LOCAL_DB_PATH": str(tmp / f"{port}.sqlite3"), "APP_ENV": "development", **extra}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError: time.sleep(0.25)
    return srv


def main() -> int:
    tmp, failures = Path(tempfile.mkdtemp()), []
    check = lambda cond, msg: failures.append(msg) if not cond else print("PASS", msg)
    port, port2 = free_port(), free_port()
    srv, srv2 = start(port, tmp, GUEST_MAX_ACTIVE_PER_IP="1000"), start(port2, tmp, GUEST_MAX_ACTIVE_PER_IP="1")
    base, base2 = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{port2}"
    me = lambda pg: pg.evaluate("() => fetch('/api/v1/auth/me').then(r => r.json())")
    status = lambda pg, path: pg.evaluate("(p) => fetch(p).then(r => r.status)", path)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(); pg = ctx.new_page()

            # 1. signed out: login first
            pg.goto(base); check(pg.url == base + "/login", "signed-out visit to / ends on /login")
            pg.goto(base + "/listings"); q = urlparse(pg.url)
            check(q.path == "/login" and parse_qs(q.query).get("next") == ["/listings"], "signed-out visit to /listings ends on /login with next=/listings")
            check(pg.is_visible("#guest-btn") and "Continue as Guest" in pg.inner_text("#guest-btn"), "login page shows a Continue as Guest button")
            check(pg.is_visible("#developer-link"), "Developer link is still a separate entry")
            check((me(pg))["user"] is None, "no session exists before choosing anything")

            # 2. Continue as Guest (no credentials)
            if pg.query_selector("[data-choice=reject]"): pg.click("[data-choice=reject]")
            pg.click("#guest-btn"); pg.wait_for_url(base + "/listings")      # next=/listings is honoured for guests (public page)
            check(True, "guest entered from /login?next=/listings lands on the public listings page")
            pg.goto(base + "/"); user = me(pg)["user"]
            check(user and user["role"] == "guest", "the button created a real guest session (role guest, not admin)")
            pg.wait_for_selector("#authLink .auth-guest")
            check(pg.inner_text("#authLink .auth-guest").strip().lower() == "guest", "header shows the Guest indicator")
            check(pg.locator("#authLink a[href='/login']").count() == 1, "header offers Log in to a guest")
            check(pg.locator("#creatorsMenu").count() == 1 and pg.locator("[data-onclick^=\"nav('detail'\"]").first.is_visible(), "guest can browse the property listings on the home page")

            # 3. listings page: browse yes, create/mine/messages no
            pg.goto(base + "/listings"); pg.wait_for_selector("#guest-badge:not([hidden])")
            check(pg.url == base + "/listings", "guest may open the listings page")
            check(not pg.is_visible("#create-form") and not pg.is_visible("#mine-card"), "guest sees no create-listing form or personal listings")
            check(not pg.is_visible("#messages-link"), "guest sees no Messages link")
            check(pg.is_visible("#login-note") and "sign up" in pg.inner_text("#login-note"), "guest is invited to log in or sign up")

            # 4. the browser really is refused by the server
            check(status(pg, "/api/v1/messages/conversations") == 403, "private messaging API refuses the guest (403)")
            check(status(pg, "/api/v1/listings/mine") == 403, "personal listings API refuses the guest (403)")
            check(status(pg, "/api/v1/admin/users") == 403, "admin API refuses the guest (403)")
            check(status(pg, "/api/v1/listings") == 200, "public listings API still works for the guest")

            # 5. guest on private pages gets a usable login form, not a dead "signed in" panel
            pg.goto(base + "/messages"); check("/login" in pg.url, "guest opening /messages is sent to login")
            pg.wait_for_selector("#form-login"); pg.wait_for_timeout(300)
            check(pg.is_visible("#form-login") and not pg.is_visible("#welcome"), "login form is shown to a guest (not 'signed in')")
            pg.goto(base + "/admin"); check("/login" in pg.url, "guest opening /admin is sent to login")

            # 6. Exit guest ends the session
            pg.goto(base + "/"); pg.wait_for_selector("#authLink .auth-guest")
            if pg.query_selector("[data-choice=reject]") and pg.is_visible("[data-choice=reject]"): pg.click("[data-choice=reject]")
            pg.click("#authLink .auth-logout"); pg.wait_for_url(base + "/login")
            check(me(pg)["user"] is None and pg.goto(base + "/").url == base + "/login", "Exit ends the guest session and the app is locked again")

            # 7. guest limit: a second guest on a server that allows one is refused with a clear message and no session
            g1 = b.new_context().new_page(); g1.goto(base2 + "/login")
            if g1.query_selector("[data-choice=reject]"): g1.click("[data-choice=reject]")
            g1.click("#guest-btn"); g1.wait_for_url(base2 + "/")
            g2 = b.new_context().new_page(); g2.goto(base2 + "/login")
            if g2.query_selector("[data-choice=reject]"): g2.click("[data-choice=reject]")
            g2.click("#guest-btn"); g2.wait_for_selector("#form-login .banner, #form-login [role=alert]", timeout=8000)
            check("guest sessions" in g2.inner_text("#form-login").lower(), "guest limit shows the server's message")
            check(g2.url == base2 + "/login" and me(g2)["user"] is None, "refused guest stays signed out on the login page")
            check(g2.is_enabled("#guest-btn") and "Continue as Guest" in g2.inner_text("#guest-btn"), "button is usable again after the failure")

            # 8. Developer Login and normal sign-up are unaffected
            d = b.new_context().new_page(); d.goto(base + "/login"); d.click("#developer-link"); d.wait_for_url(base + "/developer-login")
            check(d.is_visible("form"), "Developer link opens the separate developer page")
            u = b.new_context().new_page(); u.goto(base + "/signup"); u.fill("#su-name", "Sara Khan"); u.fill("#su-email", "sara.t4@example.com")
            u.fill("#su-pw", "correct-horse-battery"); u.fill("#su-confirm", "correct-horse-battery"); u.click("#form-signup button[type=submit]")
            u.wait_for_url(base + "/"); check(me(u)["user"]["role"] == "user", "normal sign-up still works and gives a regular user")
            check(u.locator("#authLink .auth-guest").count() == 0 and status(u, "/api/v1/messages/conversations") == 200, "a regular user sees no guest limits")
            b.close()
    finally:
        srv.terminate(); srv2.terminate()
    if failures:
        print("FAILED:", failures); return 1
    print("guest_entry_test: OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
