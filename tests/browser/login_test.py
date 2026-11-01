"""Browser test for the redesigned login page (Playwright). Run:  python tests/browser/login_test.py

Covers: Login/Sign Up toggle, inline validation messages, wrong password for admin_001 -> /nice-try,
correct password -> /admin, Google "not configured" state, no CSP violations. Uses a throwaway database
and a throwaway admin password. Writes screenshots to $LOGIN_SHOTS (default: a temp folder) so they can be
compared with design-reference/login/screenshot-*.png. Not part of `npm run test:all` (needs a browser)."""
import hashlib, os, socket, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ADMIN_PW = "Throwaway-Admin-Pw-2468!"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    shots = Path(os.environ.get("LOGIN_SHOTS", tmp)); shots.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"),
           "ADMIN_001_PASSWORD": ADMIN_PW, "APP_ENV": "development", "LOGIN_RATE_LIMIT_PER_MIN": "100"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            for name, vp in (("desktop-1366x768", {"width": 1366, "height": 768}), ("mobile-390x844", {"width": 390, "height": 844})):
                pg = b.new_page(viewport=vp)
                # Property photos are not in the repo archive (known, unrelated), so their 404s are ignored; any other failed request is a problem.
                pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
                pg.on("response", lambda r: problems.append(f"{r.status} {r.url}") if r.status >= 400 and "Property%20Images" not in r.url and "/api/v1/auth/" not in r.url else None)
                pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
                pg.goto(f"{base}/login"); pg.wait_for_selector("#form-login:not([hidden])")
                pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(300)
                pg.screenshot(path=str(shots / f"login-{name}.png"))
                if name.startswith("mobile"):
                    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "horizontal scroll on phone"
                    pg.close(); continue

                # validation: empty submit shows messages and focuses the first invalid field
                pg.click("#form-login button[type=submit]")
                assert "Username or email is required." in pg.inner_text("#form-login"), "missing identifier message"
                assert pg.evaluate("document.activeElement.id") == "login-id", "first invalid field not focused"
                pg.fill("#login-id", "x"); assert pg.locator("#login-id-err").count() == 0, "error not cleared on edit"

                # toggle without reload
                pg.click("#nav-signup"); assert pg.is_visible("#form-signup") and not pg.is_visible("#form-login")
                pg.click("#form-signup button[type=submit]")
                text = pg.inner_text("#form-signup")
                for msg in ("Full name is required.", "Email is required.", "Password is required."): assert msg in text, msg
                pg.fill("#su-name", "Test User"); pg.fill("#su-email", "nope"); pg.fill("#su-pw", "short"); pg.fill("#su-confirm", "different")
                pg.click("#form-signup button[type=submit]")
                text = pg.inner_text("#form-signup")
                for msg in ("Enter a valid email address.", "Use at least 10 characters.", "Passwords do not match."): assert msg in text, msg
                assert "10 characters" in pg.inner_text("#pw-hint"), "hint must show the real server policy"
                pg.click("#form-signup [data-switch=login]"); assert pg.is_visible("#form-login")

                # eye toggle
                pg.fill("#login-pw", "secret"); pg.click("#form-login [data-eye]")
                assert pg.get_attribute("#login-pw", "type") == "text" and pg.get_attribute("#form-login [data-eye]", "aria-pressed") == "true"

                # Google is not configured: a clear message, never a fake sign-in
                pg.click("#form-login [data-google]")
                assert "not configured" in pg.inner_text("#form-login [data-banner]"), "Google not-configured message"
                assert pg.url.endswith("/login"), "Google button must not navigate"

                # admin_001 + wrong password -> /nice-try, and no session was created
                pg.fill("#login-id", "admin_001"); pg.fill("#login-pw", "wrong-password-123")
                pg.click("#form-login button[type=submit]"); pg.wait_for_url("**/nice-try", timeout=8000)
                assert pg.evaluate("fetch('/api/v1/auth/me').then(r=>r.json()).then(d=>d.user)") is None, "wrong password created a session"

                # admin_001 + right password -> /admin
                pg.goto(f"{base}/login"); pg.fill("#login-id", "admin_001"); pg.fill("#login-pw", ADMIN_PW)
                pg.click("#form-login button[type=submit]"); pg.wait_for_url("**/admin", timeout=8000)

                # forgot password: honest note when email is not configured, same generic result either way
                pg.evaluate("fetch('/api/v1/auth/logout',{method:'POST',headers:{'X-CSRF-Token':document.cookie.match(/kpt_csrf=([^;]+)/)[1]}})")
                pg.goto(f"{base}/login"); pg.click("#form-login [data-switch=forgot]"); assert pg.is_visible("#form-forgot")
                pg.wait_for_function("document.querySelector('#forgot-note').textContent.includes('not set up')", timeout=5000)
                pg.click("#form-forgot button[type=submit]"); assert "Email is required." in pg.inner_text("#form-forgot")
                pg.fill("#fg-email", "someone@example.com"); pg.click("#form-forgot button[type=submit]")
                pg.wait_for_selector("#form-forgot [data-banner].ok", timeout=5000)

                # reset link: sign up, plant a known token hash, follow ?reset=, set a new password, log in with it
                pg.goto(f"{base}/signup"); pg.fill("#su-name", "Reset Me"); pg.fill("#su-email", "reset@example.com")
                pg.fill("#su-pw", "old-passphrase-12345"); pg.fill("#su-confirm", "old-passphrase-12345")
                pg.click("#form-signup button[type=submit]"); pg.wait_for_url(base + "/", timeout=8000)
                db = sqlite3.connect(tmp / "t.sqlite3"); uid = db.execute("select id from users where email='reset@example.com'").fetchone()[0]
                now = int(time.time())
                db.execute("insert into password_resets (id_hash,user_id,created_at,expires_at) values (?,?,?,?)",
                           (hashlib.sha256(b"browser-test-token").hexdigest(), uid, now, now + 900)); db.commit(); db.close()
                pg.goto(f"{base}/login?reset=browser-test-token"); pg.wait_for_selector("#form-reset:not([hidden])")
                assert "reset=" not in pg.url, "token must be removed from the address bar"
                pg.fill("#rs-new", "new-passphrase-67890"); pg.fill("#rs-confirm", "mismatch"); pg.click("#form-reset button[type=submit]")
                assert "Passwords do not match." in pg.inner_text("#form-reset")
                pg.fill("#rs-confirm", "new-passphrase-67890"); pg.click("#form-reset button[type=submit]")
                pg.wait_for_selector("#form-login:not([hidden]) [data-banner].ok", timeout=8000)
                pg.fill("#login-id", "reset@example.com"); pg.fill("#login-pw", "new-passphrase-67890")
                pg.click("#form-login button[type=submit]"); pg.wait_for_url(base + "/", timeout=8000)

                # signed in visitors see "Signed in as", not the form
                pg.goto(f"{base}/login"); pg.wait_for_selector("#welcome:not([hidden])", timeout=5000)
                assert pg.is_hidden("#form-login"), "form shown to a signed-in user"
                pg.close()
            b.close()
    finally:
        srv.terminate()
    csp = [m for m in problems if m]
    if csp:
        print("PROBLEMS:", *csp, sep="\n  "); return 1
    print(f"login page OK; screenshots in {shots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
