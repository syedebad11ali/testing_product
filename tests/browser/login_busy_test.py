"""Login page: while a sign-in request is in flight the submit and Google buttons are disabled (no double submits), and the page
recovers afterwards. Uses the real server; the login response is delayed in the browser. Run: python tests/browser/login_busy_test.py"""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development", "LOGIN_RATE_LIMIT_PER_MIN": "100"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, errors = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_context().new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)[:200]))
            pg.goto(base + "/login"); pg.wait_for_selector("#form-login")
            if pg.locator("[data-choice=reject]").count(): pg.click("[data-choice=reject]")

            def slow(route):
                time.sleep(1.2); route.continue_()
            pg.route("**/api/v1/auth/login", slow)
            pg.fill("#login-id", "nobody@example.com"); pg.fill("#login-pw", "wrong-password-here")
            pg.click("#form-login button[type=submit]")
            pg.wait_for_timeout(300)
            assert pg.locator("#form-login button[type=submit]").is_disabled(), "submit must be disabled while the request is in flight"
            assert pg.locator("#form-login").get_attribute("aria-busy") == "true"
            g = pg.locator("#form-login button[data-google], #form-login .gbox").first
            assert g.is_disabled() if g.evaluate("e => e.tagName") == "BUTTON" else "busy" in (g.get_attribute("class") or ""), "Google sign-in must not start during a login"
            pg.locator("#form-login [data-banner]").filter(has_text="Invalid email or password").wait_for(timeout=8000)
            assert not pg.locator("#form-login button[type=submit]").is_disabled(), "page must recover after the response"
            assert pg.locator("#form-login").get_attribute("aria-busy") == "false"
            b.close()
        assert not errors, errors
        print("login_busy_test OK"); return 0
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
