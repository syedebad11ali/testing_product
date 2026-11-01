"""Browser test (Session 15): seller edits and closes/reopens a listing from My listings (keyboard + status messages);
a buyer no longer sees it while closed. Run: python tests/browser/listing_lifecycle_test.py"""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PW = "correct-horse-battery-9"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
           "LOGIN_RATE_LIMIT_PER_MIN": "100", "RATE_LIMIT_PER_MIN": "1000", "MESSAGE_RATE_LIMIT_PER_MIN": "200"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems = f"http://127.0.0.1:{port}", []
    watch = lambda pg: (pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None),
                        pg.on("pageerror", lambda e: problems.append(f"pageerror: {str(e.stack)[:300]}")),
                        pg.on("dialog", lambda d: (problems.append(f"native dialog {d.type}"), d.dismiss())))

    def signup(ctx, name, email):
        pg = ctx.new_page(); watch(pg)
        pg.goto(f"{base}/signup"); pg.wait_for_selector("#form-signup")
        assert pg.locator("#consentBanner").count() == 0, "T5a: no consent banner before sign-in"
        pg.fill("#su-name", name); pg.fill("#su-email", email); pg.fill("#su-pw", PW); pg.fill("#su-confirm", PW)
        pg.click("#form-signup button[type=submit]"); pg.wait_for_url(f"{base}/", wait_until="commit")
        pg.wait_for_selector("[data-choice=reject]"); pg.click("[data-choice=reject]")  # T5a: the banner appears after sign-in
        return pg

    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            sp = signup(b.new_context(), "Sara Seller", "sara@example.com")
            bp = signup(b.new_context(), "Bilal Buyer", "bilal@example.com")
            sp.goto(f"{base}/listings"); sp.wait_for_selector("#create-form:not([hidden])")
            sp.fill("#c-title", "Corner house"); sp.fill("#c-area", "Gulshan"); sp.click("#c-submit")
            sp.wait_for_selector("#mine li", timeout=10000)

            # edit: validation, keyboard Escape returns focus, save shows plain text (no markup interpreted)
            sp.click("#mine li button:has-text('Edit')"); sp.wait_for_selector(".ls-edit input")
            assert sp.evaluate("document.activeElement.tagName") == "INPUT", "focus not moved into editor"
            sp.fill(".ls-edit input >> nth=0", "ab"); sp.keyboard.press("Enter")
            sp.wait_for_selector("text=3 to 120")
            sp.keyboard.press("Escape"); sp.wait_for_selector(".ls-edit", state="detached")
            assert "Edit" in sp.evaluate("document.activeElement.textContent"), "focus not restored to Edit button"
            sp.click("#mine li button:has-text('Edit')"); sp.fill(".ls-edit input >> nth=0", "<i>Renovated</i> corner house")
            sp.fill(".ls-edit input >> nth=1", "DHA"); sp.click(".ls-edit button[type=submit]")
            sp.wait_for_selector("#mine-status:has-text('Saved')", timeout=10000)
            sp.wait_for_selector("#mine li:has-text('DHA')", timeout=10000)   # wait for the list refetch, not just the message
            sp.wait_for_selector("#mine:has-text('DHA')", timeout=10000)  # the status text appears one request before the list refetch finishes
            assert "<i>Renovated</i>" in sp.inner_text("#mine") and "DHA" in sp.inner_text("#mine")

            # buyer sees it, then it closes
            bp.goto(f"{base}/listings"); bp.wait_for_selector("#browse li")
            sp.click("#mine li button:has-text('Close')")
            sp.wait_for_selector("#mine-status:has-text('Closed')", timeout=10000)
            sp.wait_for_selector("#mine li button:has-text('Reopen')", timeout=10000); sp.wait_for_selector("#browse-empty:not([hidden])", timeout=10000)
            assert "closed" in sp.inner_text("#mine") and sp.locator("#browse li").count() == 0, "closed listing still in browse"
            bp.goto(f"{base}/listings"); bp.wait_for_selector("#browse-empty:not([hidden])")
            assert bp.locator("#browse li").count() == 0

            # reopen
            sp.click("#mine li button:has-text('Reopen')"); sp.wait_for_selector("#mine-status:has-text('Reopened')", timeout=10000)
            bp.goto(f"{base}/listings"); bp.wait_for_selector("#browse li")
            b.close()
    finally:
        srv.terminate()
    if problems:
        print("FAIL", problems); return 1
    print("listing lifecycle browser test OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
