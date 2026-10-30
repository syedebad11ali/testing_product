"""Regression: with the confirm-password field focused and mismatching, ONE click on "Create account" must submit and show every
validation error. Before the fix the blur check added an error line under the confirm field, the button moved before mouse-up and the
click was lost (users had to click twice). Run:  python tests/browser/signup_single_click_test.py"""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(Path(tempfile.mkdtemp()) / "t.db"), "APP_ENV": "development"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures = []
    check = lambda ok, what: (print(("PASS " if ok else "FAIL ") + what), None if ok else failures.append(what))
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            for label, viewport in (("desktop", {"width": 1280, "height": 800}), ("mobile 375px", {"width": 375, "height": 760})):
                pg = b.new_context(viewport=viewport).new_page(); pg.goto(f"http://127.0.0.1:{port}/signup"); pg.wait_for_selector("#form-signup")
                check(pg.locator("#consentBanner").count() == 0, f"{label}: no cookie banner on the sign-up page (T5a)")
                pg.fill("#su-name", "Test User"); pg.fill("#su-email", "nope"); pg.fill("#su-pw", "short"); pg.fill("#su-confirm", "different")  # confirm stays focused
                pg.click("#form-signup button[type=submit]")
                text = pg.inner_text("#form-signup")
                check(all(m in text for m in ("Enter a valid email address.", "Use at least 10 characters.", "Passwords do not match.")), f"{label}: a single click shows all three errors")
                check(pg.evaluate("() => document.activeElement.id") == "su-email", f"{label}: focus moves to the first invalid field (email)")
                # keyboard path still validates on blur: Tab out of a mismatching confirm field shows the mismatch message
                pg.fill("#su-email", "ok@example.com"); pg.fill("#su-pw", "long-enough-password"); pg.fill("#su-confirm", "x"); pg.keyboard.press("Tab")
                check(pg.inner_text("#su-confirm-err") == "Passwords do not match.", f"{label}: Tab out of the confirm field still reports the mismatch")
            b.close()
    finally:
        srv.terminate()
    print("OK" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
