"""Browser test: seller creates a listing -> second account finds it and opens a chat -> report / block / unblock dialogs.
Run:  python tests/browser/listings_test.py   (Playwright + Chromium; throwaway database; not part of `npm run test:all`)."""
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
                        pg.on("pageerror", lambda e: problems.append(f"pageerror on {pg.url}: {str(e.stack)[:300]}")))

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
            seller_ctx, buyer_ctx = b.new_context(), b.new_context()
            sp = signup(seller_ctx, "Sara Seller", "sara@example.com")
            bp = signup(buyer_ctx, "Bilal Buyer", "bilal@example.com")

            # 1. seller creates a listing (validation first, then success; no double submit)
            sp.goto(f"{base}/listings"); sp.wait_for_selector("#create-form:not([hidden])")
            sp.click("#c-submit"); assert "3 to 120" in sp.inner_text("#c-status"), "title validation missing"
            sp.fill("#c-title", "<b>Corner</b> house near park"); sp.fill("#c-area", "Gulshan-e-Iqbal")
            sp.click("#c-submit"); sp.wait_for_selector("text=Created. Reference u-", timeout=10000)
            ref = sp.inner_text("#c-status").split("Reference ")[1].strip(" .")
            sp.wait_for_selector("#mine li", timeout=10000)
            assert sp.locator("#mine li").count() == 1 and "<b>" in sp.inner_text("#mine"), "My listings missing or markup was interpreted"
            sp.wait_for_selector("#browse li", timeout=10000)   # the browse list refreshes asynchronously after create (was an intermittent race)
            assert sp.locator("#browse li").count() == 1, "listing not discoverable"

            # 2. buyer finds it, sees it labelled unverified, opens the chat and writes
            bp.goto(f"{base}/listings"); bp.wait_for_selector("#browse li")
            assert "unverified" in bp.inner_text("#browse"), "missing unverified label"
            bp.click("#browse li button"); bp.wait_for_selector("#detail:not([hidden])")
            assert "Seller-submitted, unverified" in bp.inner_text("#detail")
            bp.click("#d-chat"); bp.wait_for_url("**/messages?c=*", wait_until="commit")
            bp.wait_for_selector("#composer textarea:not([disabled])", timeout=10000)
            bp.fill("#body", "Is this still available?"); bp.click("#send"); bp.wait_for_selector("text=Is this still available?")

            # 3. seller opens the inbox: dialogs for report / block / unblock
            sp.goto(f"{base}/messages"); sp.wait_for_selector("#inbox .msg-item"); sp.click("#inbox .msg-item")
            sp.wait_for_selector("text=Is this still available?")
            sp.click("#report"); assert sp.evaluate("document.getElementById('dlg').open"), "report dialog did not open"
            sp.click("#dlg-ok"); assert "3 to 500" in sp.inner_text("#dlg-err"), "empty report must be rejected inside the dialog"
            sp.keyboard.press("Escape"); assert not sp.evaluate("document.getElementById('dlg').open"), "Esc should close the dialog"
            sp.click("#report"); sp.fill("#dlg-input", "Asked for money before viewing"); sp.click("#dlg-ok")
            sp.wait_for_selector("text=Thank you. Our moderators will review"); assert not sp.evaluate("document.getElementById('dlg').open")
            # per-message report: the menu lists the OTHER person's messages (plain text) and the chosen id is sent
            sent = []; sp.on("request", lambda r: sent.append(r.post_data or "") if r.url.endswith("/report") else None)
            sp.click("#report"); assert sp.locator("#dlg-target").is_visible()
            assert sp.locator("#dlg-target-select option").first.inner_text() == "The whole conversation"
            assert sp.locator("#dlg-target-select option").count() >= 2, "no selectable messages offered"
            assert sp.locator("#dlg-target-select option >> nth=1").inner_text().startswith("Message: ")
            sp.select_option("#dlg-target-select", index=1); sp.fill("#dlg-input", "This message pressures me to pay"); sp.click("#dlg-ok")
            for _ in range(40):
                if any("pressures" in d for d in sent): break
                sp.wait_for_timeout(100)
            assert any('"message_id":"' in d and "pressures" in d for d in sent), sent
            assert not sp.evaluate("document.getElementById('dlg').open")
            sp.click("#report"); sp.fill("#dlg-input", "Whole conversation report"); sp.click("#dlg-ok")      # default = no message id
            for _ in range(40):
                if any("Whole conversation" in d for d in sent): break
                sp.wait_for_timeout(100)
            assert not any('"message_id":"' in d for d in sent if "Whole conversation" in d), sent
            sp.click("#block"); assert "unblock" in sp.inner_text("#dlg-text").lower(), "block dialog must explain the effect"
            sp.click("#dlg-ok"); sp.wait_for_selector("#unblock:not([hidden])"); assert sp.locator("#block").is_hidden()
            assert sp.locator("#composer textarea").is_disabled(), "composer should be disabled while blocked"
            sp.click("#unblock"); sp.click("#dlg-ok"); sp.wait_for_selector("#block:not([hidden])"); assert sp.locator("#unblock").is_hidden()
            # My listings is paginated (10 per page): create 12 more through the page's own API client, then page through
            sp.goto(f"{base}/listings"); sp.wait_for_selector("#create-form:not([hidden])")
            sp.evaluate("""async () => { const t = (await (await fetch('/api/v1/auth/csrf')).json()).csrf_token;
              for (let i = 0; i < 12; i++) await fetch('/api/v1/listings', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':t}, body: JSON.stringify({title:'Paged '+i, area:'Clifton'})}); }""")
            sp.reload(); sp.wait_for_selector("#mine-pager:not([hidden])")
            assert sp.locator("#mine li").count() == 10 and sp.locator("#mine-prev").is_disabled()
            sp.click("#mine-next"); sp.wait_for_selector("#mine-next[disabled]", timeout=10000)
            assert sp.locator("#mine-next").is_disabled() and "Page 2" in sp.inner_text("#mine-page")
            b.close()
    finally:
        srv.terminate()
    for x in problems: print("PROBLEM:", x)
    print("listings:", "FAIL" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
