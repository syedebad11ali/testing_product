"""Browser test: admin two-factor in the real UI (Playwright). Run:  python tests/browser/admin_totp_test.py
Uses real wall-clock TOTP codes (pyotp) and a throwaway database + a freshly generated TOTP_ENCRYPTION_KEY, so it waits for the next
30 s time step between uses (replay protection). Takes about a minute. Not part of `npm run test:all` (needs a browser)."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
import pyotp
from cryptography.fernet import Fernet
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ADMIN_PW, PW = "Throwaway-Admin-Pw-2468!", "correct-horse-battery-9"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def next_step():
    """Block until a new 30 s step starts so the previous code can no longer be replayed."""
    time.sleep(30 - (time.time() % 30) + 0.5)


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
           "ADMIN_001_PASSWORD": ADMIN_PW, "TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
           "LOGIN_RATE_LIMIT_PER_MIN": "100", "RATE_LIMIT_PER_MIN": "1000"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems = f"http://127.0.0.1:{port}", []
    watch = lambda pg: (pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None),
                        pg.on("pageerror", lambda e: problems.append(f"pageerror on {pg.url}: {str(e.stack)[:300]}")))
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            # a user to moderate
            vctx = b.new_context(); vp = vctx.new_page(); watch(vp)
            vp.goto(f"{base}/signup"); vp.wait_for_selector("#form-signup")   # T5a: no banner before sign-in
            vp.fill("#su-name", "Victor Victim"); vp.fill("#su-email", "victor@example.com"); vp.fill("#su-pw", PW); vp.fill("#su-confirm", PW)
            vp.click("#form-signup button[type=submit]"); vp.wait_for_url(f"{base}/", wait_until="commit")

            actx = b.new_context(accept_downloads=True); pg = actx.new_page(); watch(pg)
            pg.goto(f"{base}/login"); pg.wait_for_selector("#form-login")   # T5a: no banner before sign-in
            pg.fill("#login-id", "admin_001"); pg.fill("#login-pw", ADMIN_PW); pg.click("#form-login button[type=submit]")
            pg.wait_for_url(f"{base}/admin", wait_until="commit"); pg.wait_for_selector("#users tbody tr"); dismiss_consent(pg, wait_ms=3000)  # banner now appears after login
            assert "off" in pg.inner_text("#totp-state"), pg.inner_text("#totp-state")

            # enrol: needs the password; the key is shown once; a wrong code is refused; the right one turns it on
            pg.click("#totp-start"); assert "password" in pg.inner_text("#msg").lower()
            pg.fill("#reauth", ADMIN_PW); pg.click("#totp-start"); pg.wait_for_selector("#totp-enroll:not([hidden])")
            secret = pg.inner_text("#totp-secret").strip(); assert len(secret) >= 16
            pg.fill("#totp-code", "000000"); pg.click("#totp-confirm"); pg.wait_for_selector("#msg:has-text('not valid')")
            totp = pyotp.TOTP(secret)
            pg.fill("#totp-code", totp.now()); pg.click("#totp-confirm")
            pg.wait_for_selector("#totp-state:has-text('is on')")
            assert pg.inner_text("#totp-secret").strip() == "", "setup key must disappear after confirmation"

            # CSV export now needs a fresh code (the enrolment code is spent)
            next_step()
            with pg.expect_download() as dl:
                pg.click("#exportUsers"); pg.wait_for_selector("#stepup[open]")
                pg.fill("#su-code", "123456" if totp.now() != "123456" else "654321"); pg.press("#su-code", "Enter")
                pg.wait_for_selector("#su-err:not(:empty)")   # a wrong code stays in the dialog with an error
                pg.fill("#su-code", totp.now()); pg.press("#su-code", "Enter")
            name = dl.value.suggested_filename; assert name == "kpt-users.csv", name
            assert "victor@example.com" in Path(dl.value.path()).read_text(encoding="utf-8")

            # banning needs yet another fresh code; cancelling the dialog leaves the user active
            pg.fill("#reauth", ADMIN_PW); pg.fill("#reason", "spam listings")
            row = pg.locator("#users tbody tr", has_text="victor@example.com")
            row.get_by_text("Ban / Suspend").click(); pg.wait_for_selector("#stepup[open]")
            pg.press("#su-code", "Escape"); assert not pg.evaluate("document.getElementById('stepup').open")
            assert "cancelled" in pg.inner_text("#msg").lower()
            next_step()
            row.get_by_text("Ban / Suspend").click(); pg.wait_for_selector("#stepup[open]")
            pg.fill("#su-code", totp.now()); pg.press("#su-code", "Enter")
            pg.wait_for_selector("#users tbody:has-text('banned')", timeout=15000)
            b.close()
    finally:
        srv.terminate()
    for x in problems: print("PROBLEM:", x)
    print("admin_totp:", "FAIL" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
