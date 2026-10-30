"""Two-account browser test for buyer-seller messaging (Playwright). Run:  python tests/browser/messaging_test.py

Buyer: signs up, opens a demo property, clicks "Chat with seller" -> thread opens, sends text incl. an XSS payload.
Seller (demo account from scripts/seed_demo_listings.py): sees the unread badge, reads the message as inert text,
replies; the buyer's open page receives the reply by polling. Also: signed-out visitor is routed through login.
Throwaway database; not part of `npm run test:all` because it needs a browser."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SELLER_PW, BUYER_PW = "demo-seller-password-1", "correct-horse-battery"
PAYLOAD = '<img src=x onerror="window.__pwned=1"> hello'


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def api(pg, path, body=None):
    return pg.evaluate("""async ([path, body]) => {
        const c = await (await fetch('/api/v1/auth/csrf')).json();
        const r = await fetch(path, {method: body === null ? 'GET' : 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': c.csrf_token}, body: body === null ? undefined : JSON.stringify(body)});
        return {status: r.status, data: await r.json().catch(() => ({}))};
    }""", [path, body])


def dismiss_banner(pg):
    pg.wait_for_selector("#consentBanner"); pg.click("[data-choice=reject]")  # the banner covers the page until a choice is made


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
           "LOGIN_RATE_LIMIT_PER_MIN": "100", "RATE_LIMIT_PER_MIN": "1000", "MESSAGE_RATE_LIMIT_PER_MIN": "100", "DEMO_SELLER_PASSWORD": SELLER_PW}
    subprocess.run([sys.executable, "scripts/seed_demo_listings.py"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, failures = f"http://127.0.0.1:{port}", []
    check = lambda ok, what: (print(("PASS " if ok else "FAIL ") + what), None if ok else failures.append(what))
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            # guest visitor (a signed-out visitor never reaches the app since T4): Chat with seller does not open a conversation,
            # it says an account is needed and offers Log in with the listing context kept in the return path
            anon = b.new_context().new_page(); enter_as_guest(anon, base)
            anon.click("[data-onclick=\"nav('detail','p1')\"]"); anon.click("text=Chat with seller")
            anon.wait_for_selector("#sellerChatNote a")
            check("free account" in anon.inner_text("#sellerChatNote"), "guest: told that messaging needs an account")
            check("/messages" not in anon.url, "guest: no conversation was opened")
            anon.click("#sellerChatNote >> text=Log in")
            anon.wait_for_url("**/login?next=*")
            check("next=" in anon.url and "messages" in anon.url, "guest: Log in link keeps the return path")

            buyer_ctx = b.new_context(); buyer = buyer_ctx.new_page(); buyer.goto(base + "/login")
            check(api(buyer, "/api/v1/auth/signup", {"name": "Bilal Buyer", "email": "bilal@example.com", "password": BUYER_PW})["status"] in (200, 201), "buyer signs up")
            buyer.goto(base); dismiss_banner(buyer); buyer.click("[data-onclick=\"nav('detail','p1')\"]"); buyer.click("text=Chat with seller")
            buyer.wait_for_url("**/messages?c=*"); buyer.wait_for_selector("#thread:not([hidden])")
            check(buyer.inner_text("#peer").startswith("Demo"), "buyer: thread opened, counterpart shown by short name")
            buyer.fill("#body", PAYLOAD); buyer.click("#send"); buyer.wait_for_selector(".msg-bubble.mine")
            check(buyer.evaluate("() => window.__pwned") is None and PAYLOAD in buyer.inner_text("#messages"), "buyer: HTML payload shown as text, never executed")

            seller_ctx = b.new_context(); seller = seller_ctx.new_page(); seller.goto(base + "/login")
            check(api(seller, "/api/v1/auth/login", {"identifier": "demo.seller@kpt.local", "password": SELLER_PW})["status"] == 200, "seller logs in")
            seller.goto(base + "/messages"); dismiss_banner(seller); seller.wait_for_selector(".msg-item")
            check("1 new" in seller.inner_text("#inbox"), "seller: unread badge in inbox")
            seller.click(".msg-item"); seller.wait_for_selector(".msg-bubble")
            check(seller.evaluate("() => window.__pwned") is None and PAYLOAD in seller.inner_text("#messages"), "seller: payload inert")
            seller.fill("#body", "Thanks, it is available."); seller.click("#send")
            buyer.locator(".msg-bubble").nth(1).wait_for(timeout=15000)  # appears via the page's polling
            check("Thanks, it is available." in buyer.inner_text("#messages"), "buyer: reply arrives by polling")
            check(len(buyer.query_selector_all(".msg-bubble")) == 2, "no duplicate messages after polling")

            # a third account cannot read the thread
            other = b.new_context().new_page(); other.goto(base + "/login")
            api(other, "/api/v1/auth/signup", {"name": "Omar Other", "email": "omar@example.com", "password": BUYER_PW})
            cid = buyer.url.split("c=")[1]
            check(api(other, f"/api/v1/messages/conversations/{cid}", None)["status"] == 404, "third account gets 404 for the conversation")
            b.close()
    finally:
        srv.terminate()
    print("OK" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
