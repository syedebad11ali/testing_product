"""Browser test: the failure paths and double-submit guard of "Continue as Guest". Run:  python tests/browser/guest_entry_failures_test.py

(`guest_entry_test` covers the happy path and the guest UI.) Covers: a 429 answer shows the server's message and creates no
session; a network failure shows a message and creates no session; the button is usable again after each failure; a double
click sends exactly ONE guest request and ends as a real guest session on `/`; no console errors, page errors or CSP
violations on any of these flows. Throwaway database."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BANNER = "#form-login [data-banner]"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
           "LOGIN_RATE_LIMIT_PER_MIN": "100", "GUEST_MAX_ACTIVE_PER_IP": "1000"}
    env.pop("DEV_ADMIN_PASSWORD", None)
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems, failures = f"http://127.0.0.1:{port}", [], []

    def check(ok, what):
        print(("PASS " if ok else "FAIL ") + what)
        if not ok: failures.append(what)

    def me(pg):
        return pg.evaluate("fetch('/api/v1/auth/me').then(r => r.json()).then(d => d.user)")

    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_context().new_page()
            pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
            pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
            pg.goto(base + "/login"); pg.wait_for_selector("#guest-btn"); dismiss_consent(pg)

            # 429: the server's own message, no session, button usable again
            pg.route("**/api/v1/auth/guest", lambda r: r.fulfill(status=429, content_type="application/json",
                     body='{"error":"Too many guest sessions from this network. Please try again later or create an account.","code":"guest_limit"}'))
            pg.click("#guest-btn")
            pg.locator(f"{BANNER}:has-text('Too many guest sessions')").wait_for(timeout=8000)
            check(urlparse(pg.url).path == "/login" and me(pg) is None, "429: message shown, still on /login, no session")
            check(pg.locator("#guest-btn").is_enabled(), "429: guest button usable again")
            pg.unroute("**/api/v1/auth/guest")

            # network failure: a message, no session, button usable again
            pg.route("**/api/v1/auth/guest", lambda r: r.abort())
            pg.click("#guest-btn")
            pg.locator(f"{BANNER}:text-matches('\\\\S')").wait_for(timeout=8000)
            check(urlparse(pg.url).path == "/login" and me(pg) is None, "network failure: message shown, no session")
            check(pg.locator("#guest-btn").is_enabled(), "network failure: guest button usable again")
            pg.unroute("**/api/v1/auth/guest")

            # double click: exactly one request, a genuine guest session on /
            posts = []
            pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" and r.url.endswith("/api/v1/auth/guest") else None)
            pg.dblclick("#guest-btn"); pg.wait_for_url(base + "/", timeout=8000)
            check(len(posts) == 1, f"double click sends one guest request (saw {len(posts)})")
            user = me(pg)
            check(bool(user) and user["role"] == "guest", "double click ends as a genuine guest session")
            b.close()
    finally:
        srv.terminate()
    if problems:
        print("CONSOLE/PAGE PROBLEMS:", *problems[:10], sep="\n  "); failures.append("console problems")
    if failures:
        print("FAILED:", *failures, sep="\n  "); return 1
    print("guest_entry_failures_test: OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
