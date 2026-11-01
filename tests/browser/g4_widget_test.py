"""G4b: the embedded chatbot widget against the REAL backend (offline rule-based engine, no AI credentials). Run: python tests/browser/g4_widget_test.py

1  public /chatbot-demo: anonymous visitor -> widget loads, a message shows the fixed Login required card (real 401), CTA = KPT /login?next=%2Fchatbot-demo
2  guest -> real 403 guest_not_allowed -> same card, guest session untouched; the CTA leads to login, after login the visitor lands on /chatbot-demo and chats
3  registered user on the first-party /chatbot-demo chats normally (a real answer, not an error row)
4  third-party site (a different origin, localhost vs 127.0.0.1) embedding the widget: even a user who is logged in on KPT gets the fixed login card with the
   not-signed-in-here note, because the KPT session cookie is not sent cross-origin (the chosen security model; authenticated third-party chat is NOT supported)
No console errors, page errors or CSP violations on the KPT pages."""
import os, socket, sqlite3, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest, enter_as_user  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PW = "correct-horse-battery-9"
RESULTS, problems = [], []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(detail)) if not cond and detail else ""))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tp_port, tmp = free_port(), free_port(), Path(tempfile.mkdtemp())
    dbf = str(tmp / "t.sqlite3")
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": dbf, "APP_ENV": "development",
           "LOGIN_RATE_LIMIT_PER_MIN": "300", "RATE_LIMIT_PER_MIN": "300", "ALLOWED_ORIGINS": f"http://localhost:{tp_port}"}
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "GOOGLE_CLIENT_ID"): env.pop(k, None)
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    page = f'<!doctype html><title>Acme Realty</title><h1>Acme Realty</h1><script src="{base}/static/chatbot.js" defer></script>'.encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(page)
        def log_message(self, *a): pass
    tp = HTTPServer(("127.0.0.1", tp_port), H); threading.Thread(target=tp.serve_forever, daemon=True).start()
    TP = f"http://localhost:{tp_port}/"
    LOGIN = f"{base}/login?next=%2Fchatbot-demo"
    watch = lambda pg: (pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None),
                        pg.on("pageerror", lambda e: problems.append(f"pageerror on {pg.url}: {str(e)[:200]}")))
    me = lambda pg: pg.evaluate("fetch('/api/v1/auth/me').then(r=>r.json())")["user"]
    card = lambda pg: pg.evaluate("""() => { const c = document.querySelector('.pc-login'); if (!c) return null; const a = c.querySelector('a');
      return {n: document.querySelectorAll('.pc-login').length, title: c.querySelector('.pc-login-title').textContent, text: c.querySelector('.pc-login-text').textContent, action: a.textContent,
      href: a.href, target: a.getAttribute('target'), note: (c.querySelector('.pc-login-note') || {}).textContent || null}; }""")

    def open_widget(pg, url):
        pg.goto(url); pg.wait_for_selector(".pc-launcher"); pg.click(".pc-launcher"); pg.wait_for_selector(".pc-compose")

    def say(pg, text):
        pg.fill(".pc-input", text); pg.keyboard.press("Enter")

    def real_answer(pg, what):
        pg.wait_for_selector(".pc-row.bot:not(.err) .pc-meta", state="attached", timeout=20000)   # the meta line is only revealed on hover
        row = pg.locator(".pc-row.bot:not(.err)").last
        text, meta = (row.locator(".pc-bubble").text_content() or "").strip(), (row.locator(".pc-meta").text_content() or "").strip()
        check(f"{what}: a real assistant answer (text + source line), no error row, no login card",
              len(text) > 20 and meta != "" and pg.locator(".pc-row.err").count() == 0 and pg.locator(".pc-login").count() == 0, (text[:60], meta))

    try:
        for _ in range(80):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()

            # account used for the login journey
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg)
            email = enter_as_user(pg, base, name="Widget Tester", password=PW); ctx.close()

            # 1. anonymous
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg); seen = []
            pg.on("request", lambda r: seen.append((r.method, r.url)) if "/api/chat" in r.url else None)
            resp = pg.goto(base + "/chatbot-demo")
            check("1 /chatbot-demo is public (200, no redirect to login)", resp.status == 200 and pg.url == base + "/chatbot-demo", (resp.status, pg.url))
            pg.wait_for_selector(".pc-launcher"); pg.click(".pc-launcher"); pg.wait_for_selector(".pc-compose")
            say(pg, "average price in DHA"); pg.wait_for_selector(".pc-login"); c = card(pg)
            check("1 anonymous: fixed Login required card", (c["title"], c["text"], c["action"]) == ("Login required", "Create an account or log in to use this feature.", "Log in / Sign up"), c)
            check("1 anonymous: CTA = KPT login with the fixed safe destination, same tab", c["href"] == LOGIN and c["target"] is None, c)
            check("1 anonymous: no raw backend text, no assistant/error row, no Try again, locked",
                  "Please log in to continue" not in pg.inner_text(".pc-root") and pg.locator(".pc-row.bot:not(:has(.pc-typing))").count() == 1 and pg.locator(".pc-row.err").count() == 0
                  and pg.locator(".pc-retry").count() == 0 and pg.is_disabled(".pc-input"))
            check("1 anonymous: exactly one chat request, not retried", len([s for s in seen if s[0] == "POST"]) == 1, seen)
            pg.click(".pc-login-btn"); pg.wait_for_url(LOGIN.replace("%2Fchatbot-demo", "*"), wait_until="commit")
            check("1 anonymous: the CTA opens the real login page with next=/chatbot-demo", pg.url == LOGIN, pg.url)
            ctx.close()

            # 2. guest -> card -> login -> back on /chatbot-demo -> chat
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg); enter_as_guest(pg, base)
            gid = me(pg)["id"]
            open_widget(pg, base + "/chatbot-demo"); say(pg, "hello"); pg.wait_for_selector(".pc-login"); c = card(pg)
            check("2 guest: fixed card (real 403 guest_not_allowed), KPT login link", (c["title"], c["text"], c["action"], c["href"]) == ("Login required", "Create an account or log in to use this feature.", "Log in / Sign up", LOGIN), c)
            check("2 guest: nothing leaked, one prompt, still a guest", "guest_not_allowed" not in pg.inner_text(".pc-root") and c["n"] == 1 and me(pg)["role"] == "guest")
            pg.click(".pc-login-btn"); pg.wait_for_selector("#form-login:not([hidden])")
            pg.fill("#login-id", email); pg.fill("#login-pw", PW); pg.click("#form-login button[type=submit]")
            try: pg.wait_for_url(base + "/chatbot-demo", wait_until="commit", timeout=15000)
            except Exception: print("DEBUG url", pg.url, "banner:", pg.locator("#form-login [data-banner]").text_content()); raise
            dismiss_consent(pg, wait_ms=2500)
            pg.wait_for_selector(".pc-launcher"); pg.click(".pc-launcher"); pg.wait_for_selector(".pc-compose")
            check("2 guest -> login: back on /chatbot-demo as a registered user", me(pg)["role"] == "user" and pg.url == base + "/chatbot-demo", pg.url)
            say(pg, "average price in DHA"); real_answer(pg, "2 after login")
            con = sqlite3.connect(dbf); left = con.execute("SELECT COUNT(*) FROM users WHERE id=?", (gid,)).fetchone()[0]; con.close()
            check("2 the old guest account/session was revoked by the login", left == 0)
            ctx.close()

            # 3. registered user, first party, directly
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg); enter_as_user(pg, base, password=PW)
            open_widget(pg, base + "/chatbot-demo"); say(pg, "average price in DHA"); real_answer(pg, "3 registered user on /chatbot-demo")
            check("3 registered user: composer stays usable", not pg.is_disabled(".pc-input"))
            ctx.close()

            # 4. third party: logged in on KPT in the same browser, widget embedded on another origin
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg); enter_as_user(pg, base, password=PW)
            check("4 precondition: this browser IS logged in on KPT", me(pg)["role"] == "user")
            tpg = ctx.new_page(); cookies_sent = []
            tpg.on("request", lambda r: cookies_sent.append(r.headers.get("cookie")) if "/api/chat" in r.url and r.method == "POST" else None)
            open_widget(tpg, TP); say(tpg, "average price in DHA"); tpg.wait_for_selector(".pc-login", timeout=15000); c = card(tpg)
            check("4 third party: fixed Login required card even though the visitor is logged in on KPT", (c["title"], c["text"], c["action"]) == ("Login required", "Create an account or log in to use this feature.", "Log in / Sign up"), c)
            check("4 third party: link = KPT origin + fixed next (not the embedding site), new tab", c["href"] == LOGIN and c["target"] == "_blank" and "localhost" not in c["href"], c)
            check("4 third party: explains the embedded assistant is not signed in by being logged in here", c["note"] and "does not sign in this embedded assistant" in c["note"], c["note"])
            check("4 third party: the KPT session cookie was NOT sent cross-origin (no credentialed CORS)", cookies_sent and not any(cookies_sent), cookies_sent)
            check("4 third party: one request, no retry, embedding page intact", len(cookies_sent) == 1 and tpg.inner_text("h1") == "Acme Realty")
            with ctx.expect_page() as newp: tpg.click(".pc-login-btn")
            np_ = newp.value; np_.wait_for_load_state("commit")
            check("4 third party: the CTA opens the KPT site", np_.url.startswith(base + "/"), np_.url)
            ctx.close()
            b.close()
        check("Z no console errors / page errors / CSP violations", not problems, problems[:5])
    finally:
        srv.terminate(); tp.shutdown()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed of {len(RESULTS)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
