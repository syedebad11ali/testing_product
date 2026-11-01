"""Browser test for the separate Developer Login page. Run:  python tests/browser/developer_login_test.py

Covers: Developer link on /login opens /developer-login; invalid credentials (unknown user, wrong admin password,
a normal user's correct password) end at /nice-try with no session; the valid admin lands on /admin; no CSP/console
errors; no horizontal scroll on a phone. Throwaway database and admin password."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ADMIN_PW = "Throwaway-Admin-Pw-2468!"
USER_PW = "correct-horse-battery"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    shots = Path(os.environ.get("LOGIN_SHOTS", tmp)); shots.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"),
           "ADMIN_001_PASSWORD": ADMIN_PW, "APP_ENV": "development", "LOGIN_RATE_LIMIT_PER_MIN": "100"}
    env.pop("DEV_ADMIN_PASSWORD", None)
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()

            def page(vp=None):
                pg = b.new_context(viewport=vp or {"width": 1366, "height": 768}).new_page()
                pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
                pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
                return pg

            def has_session(pg):
                return pg.evaluate("fetch('/api/v1/auth/me').then(r => r.json()).then(d => d.user)")

            # a normal user exists (to prove its correct password is not enough here)
            pg = page(); pg.goto(f"{base}/login"); pg.click("#nav-signup")
            pg.fill("#su-name", "Sara Khan"); pg.fill("#su-email", "sara@example.com"); pg.fill("#su-pw", USER_PW); pg.fill("#su-confirm", USER_PW)
            pg.click("#form-signup button[type=submit]"); pg.wait_for_url(f"{base}/", timeout=8000)
            pg.context.close()

            # the link on the login page opens the separate page
            pg = page(); pg.goto(f"{base}/login"); pg.wait_for_selector("#form-login:not([hidden])")
            assert pg.locator("#dev-skip").count() == 0, "old toggle button still present"
            pg.click("#developer-link"); pg.wait_for_url("**/developer-login", timeout=8000)
            pg.wait_for_selector("#form-dev"); pg.screenshot(path=str(shots / "developer-login-desktop.png"))
            pg.click("#form-dev button[type=submit]")
            assert "Enter the administrator username" in pg.inner_text("#form-dev"), "empty submit message"

            # invalid credentials -> /nice-try, no session
            for ident, pw in (("whoever", "whatever-123"), ("admin_001", "wrong-password-123"), ("sara@example.com", USER_PW)):
                pg.goto(f"{base}/developer-login"); pg.wait_for_selector("#form-dev")
                pg.fill("#dev-id", ident); pg.fill("#dev-pw", pw)
                pg.click("#form-dev button[type=submit]"); pg.wait_for_url("**/nice-try", timeout=8000)
                assert has_session(pg) is None, f"session created for {ident}"
                pg.goto(f"{base}/admin"); assert pg.url.rstrip("/").endswith("/login"), f"/admin reachable after failed {ident}"
            pg.context.close()

            # valid admin -> /admin
            pg = page(); pg.goto(f"{base}/developer-login"); pg.wait_for_selector("#form-dev")
            pg.fill("#dev-id", "admin_001"); pg.fill("#dev-pw", ADMIN_PW)
            pg.click("#form-dev button[type=submit]"); pg.wait_for_url("**/admin", timeout=8000)
            user = has_session(pg); assert user and user["role"] == "admin", "admin session missing"
            pg.context.close()

            # phone layout
            pg = page({"width": 390, "height": 844}); pg.goto(f"{base}/developer-login"); pg.wait_for_selector("#form-dev")
            pg.screenshot(path=str(shots / "developer-login-mobile.png"))
            assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "horizontal scroll on phone"
            b.close()
    finally:
        srv.terminate()
    if problems:
        print("PROBLEMS:", *problems[:10], sep="\n  "); return 1
    print("developer_login_test: OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
