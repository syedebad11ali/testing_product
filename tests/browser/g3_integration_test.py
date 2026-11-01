"""G3 completion review: end-to-end browser journeys for the guest browse-only login flow. Run:  python tests/browser/g3_integration_test.py

A  guest opens an account-only feature -> dialog -> /login?next=... -> real login -> intended destination; the old guest session is revoked
   (the old guest cookie is replayed from a fresh context and must be signed out); hash deep link, signup and keyboard behaviour included.
B  failed login keeps the guest session, opens nothing restricted.
C  normal browsing (home, search, filter, detail, back) never shows the dialog.
D  Google: the GIS script is a STUB served by the test (no network, not live Google) and the server uses a fake verifier;
   success lands on the intended destination and revokes the old guest, a rejected credential keeps the guest.
L  dialog layout at 1280 / 390 / 360 / 320 px, light and dark: inside the viewport, no horizontal scroll, touch-size buttons.
Throwaway databases; needs a browser so it is not part of `npm run test:all`."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PW = "correct-horse-battery"
GIS_STUB = """
window.google = {accounts: {id: {
  initialize(cfg) { window.__gis = cfg; },
  renderButton(box) { const b = document.createElement('button'); b.type = 'button'; b.id = 'fake-g'; b.textContent = 'Fake Google';
    b.addEventListener('click', () => window.__gis.callback({credential: window.__gmode === 'bad' ? 'not-the-nonce' : window.__gis.nonce})); box.appendChild(b); }
}}};
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def start(port, tmp, fake_google=False, **extra):
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "LOCAL_DB_PATH": str(tmp / f"{port}.sqlite3"), "APP_ENV": "development",
           "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOGIN_RATE_LIMIT_PER_MIN": "1000", "RATE_LIMIT_PER_MIN": "1000", "PYTHONPATH": str(ROOT), **extra}
    cmd = [sys.executable, "tests/browser/helpers/fake_google_server.py"] if fake_google else [sys.executable, "-m", "backend.app"]
    srv = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError: time.sleep(0.25)
    return srv


def main() -> int:
    tmp, failures = Path(tempfile.mkdtemp()), []
    def check(cond, msg):
        if cond: print("PASS", msg)
        else: failures.append(msg); print("FAIL", msg)
    port, gport = free_port(), free_port()
    srv = start(port, tmp)
    gsrv = start(gport, tmp, fake_google=True, GOOGLE_CLIENT_ID="test-client.apps.googleusercontent.com")
    base, gbase = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{gport}"
    me = lambda pg: pg.evaluate("() => fetch('/api/v1/auth/me').then(r => r.json())")
    dialog = lambda pg: pg.locator(".login-prompt")
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()

            # an existing test account (created through the real sign-up form; also proves sign-up works)
            ctx = b.new_context(); pg = ctx.new_page()
            pg.goto(base + "/login"); pg.click("#nav-signup")
            pg.fill("#su-name", "G3 Tester"); pg.fill("#su-email", "g3tester@example.com"); pg.fill("#su-pw", PW); pg.fill("#su-confirm", PW)
            pg.click("#form-signup button[type=submit]"); pg.wait_for_url(base + "/", timeout=10000)
            check(me(pg)["user"]["role"] == "user", "setup: the test account exists and is a registered user")
            ctx.close()

            # ---------------- Journey A: guest login ----------------
            ctx = b.new_context(); pg = ctx.new_page(); errors = []
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "401" not in m.text and "403" not in m.text else None)
            enter_as_guest(pg, base)
            guest_before = me(pg)["user"]
            check(guest_before and guest_before["role"] == "guest", "A1 start as a guest")
            old_cookies = ctx.cookies()
            pg.click(".topnav-menu"); pg.click("#drawerNav >> text=Owner Verification System")
            pg.wait_for_selector(".login-prompt")
            check(dialog(pg).count() == 1 and pg.inner_text(".login-prompt-title") == "Login required", "A2 opening an account-only feature shows the dialog")
            check(pg.inner_text(".login-prompt-text") == "Create an account or log in to use this feature." and "Log in / Sign up" in pg.inner_text(".login-prompt-primary"), "A3 consistent message and button")
            check("Find a Property Record" not in pg.inner_text("#app") and pg.evaluate("location.hash") == "", "A4 the restricted view was not opened, the refused hash is not left in the URL")
            check(pg.evaluate("document.activeElement.classList.contains('login-prompt-primary')"), "A5 focus starts on the primary action")
            pg.keyboard.press("Tab"); check(pg.evaluate("document.activeElement.classList.contains('login-prompt-secondary')"), "A6 Tab moves inside the dialog")
            pg.keyboard.press("Tab"); check(pg.evaluate("document.activeElement.classList.contains('login-prompt-primary')"), "A7 focus is trapped (wraps to the first action)")
            pg.keyboard.press("Escape"); check(dialog(pg).count() == 0, "A8 Escape closes the dialog")
            check(pg.evaluate("document.activeElement.classList.contains('topnav-menu') && !document.activeElement.closest('#drawer')"), "A8b after a fast Escape from a dialog opened in the drawer, focus is on the menu button, not the sliding drawer item")
            check(me(pg)["user"]["role"] == "guest", "A9 closing the dialog does not touch the guest session")
            pg.click(".topnav-menu"); pg.click("#drawerNav >> text=Owner Verification System"); pg.wait_for_selector(".login-prompt")
            check(dialog(pg).count() == 1, "A10 the same feature can be tried again")
            href = pg.get_attribute(".login-prompt-primary", "href"); q = urlparse(href)
            check(q.path == "/login" and parse_qs(q.query).get("next") == ["/#owner-verification"], "A11 the dialog link carries next=/#owner-verification")
            pg.click(".login-prompt-primary"); pg.wait_for_url("**/login?next=*")
            check(parse_qs(urlparse(pg.url).query).get("next") == ["/#owner-verification"], "A12 the login URL contains the correct next")
            pg.fill("#login-id", "g3tester@example.com"); pg.fill("#login-pw", PW)
            pg.click("#form-login button[type=submit]"); pg.wait_for_url(base + "/#owner-verification", timeout=10000)
            pg.wait_for_selector("#app")
            check(pg.url == base + "/#owner-verification", "A13 login arrives at the intended destination (SPA hash route)")
            check(me(pg)["user"]["role"] == "user", "A14 the browser is now a registered user")
            pg.wait_for_function("document.querySelector('#app').innerText.includes('Find a Property Record')", timeout=10000); check(dialog(pg).count() == 0, "A15 no login dialog for the signed-in user; the owner-verification view opened")
            ghost = b.new_context(); ghost.add_cookies(old_cookies); gp = ghost.new_page(); gp.goto(base + "/login")
            check(me(gp)["user"] is None, "A16 the OLD guest cookie replayed from a fresh browser context is signed out (guest session revoked)")
            ghost.close()
            # direct hash navigation as a guest
            enter_ctx = b.new_context(); ep = enter_ctx.new_page(); enter_as_guest(ep, base)
            ep.goto(base + "/#verify-document"); ep.wait_for_selector(".login-prompt")
            check(dialog(ep).count() == 1 and ep.evaluate("location.hash") == "", "A17 direct hash navigation to an account-only view shows the dialog and is not applied")
            q = parse_qs(urlparse(ep.get_attribute(".login-prompt-primary", "href")).query)
            check(q.get("next") == ["/#verify-document"], "A18 the hash deep link keeps its destination in next")
            ep.keyboard.press("Escape")
            ep.evaluate("location.hash = '#owner-verification'"); ep.wait_for_selector(".login-prompt")
            check(dialog(ep).count() == 1, "A19 hashchange after load is gated too")
            ep.keyboard.press("Escape")
            ep.evaluate("location.hash = '#verify-document'; location.hash = '#owner-verification'; location.hash = '#/plot/ABC-123'"); ep.wait_for_timeout(600)
            check("Find a Property Record" not in ep.inner_text("#app"), "A20 rapid hash changes never open the restricted view for a guest")
            check(ep.locator(".login-prompt").count() <= 1, "A21 at most one dialog after racing navigations")
            enter_ctx.close()
            # signup from the dialog
            sctx = b.new_context(); sp = sctx.new_page(); enter_as_guest(sp, base)
            sp.click(".topnav-menu"); sp.click("#drawerNav >> text=Verify Your Document"); sp.wait_for_selector(".login-prompt")
            sp.click(".login-prompt-primary"); sp.wait_for_url("**/login?next=*")
            check(parse_qs(urlparse(sp.url).query).get("next") == ["/#verify-document"], "A22 verify-document keeps its own destination")
            sp.click("#nav-signup"); sp.fill("#su-name", "G3 Signup"); sp.fill("#su-email", "g3signup@example.com"); sp.fill("#su-pw", PW); sp.fill("#su-confirm", PW)
            sp.click("#form-signup button[type=submit]"); sp.wait_for_url(base + "/#verify-document", timeout=10000)
            check(me(sp)["user"]["role"] == "user" and sp.url == base + "/#verify-document", "A23 sign-up from the dialog lands on the intended destination")
            sctx.close()
            check(not [e for e in errors if "Content Security Policy" in e or "securitypolicy" in e.lower()], "A24 no CSP console errors during the journey")
            ctx.close()

            # ---------------- Journey B: failed login ----------------
            ctx = b.new_context(); pg = ctx.new_page(); enter_as_guest(pg, base)
            gid = me(pg)["user"]["id"]
            pg.click(".topnav-menu"); pg.click("#drawerNav >> text=Owner Verification System"); pg.wait_for_selector(".login-prompt")
            pg.click(".login-prompt-primary"); pg.wait_for_url("**/login?next=*")
            pg.fill("#login-id", "g3tester@example.com"); pg.fill("#login-pw", "definitely-wrong-password")
            pg.click("#form-login button[type=submit]"); pg.wait_for_timeout(1500)
            check(urlparse(pg.url).path == "/login" and "#owner-verification" not in pg.url, "B1 invalid credentials stay on /login; no restricted page opens")
            check(me(pg)["user"] and me(pg)["user"]["id"] == gid and me(pg)["user"]["role"] == "guest", "B2 the guest session is still the same active guest")
            check(pg.locator("#form-login [role=alert], #form-login .err, #form-login [data-banner]").count() > 0, "B3 an error is shown")
            pg.goto(base + "/#owner-verification"); pg.wait_for_selector(".login-prompt")
            check(dialog(pg).count() == 1, "B4 the restricted view is still refused afterwards")
            ctx.close()

            # ---------------- Journey E: hostile next values never leave the site ----------------
            for hostile in ("//evil.example/x", "https://evil.example/", "/\\evil.example", "javascript:alert(1)", "/login", "/%2e%2e/login"):
                ctx = b.new_context(); pg = ctx.new_page()
                from urllib.parse import quote
                pg.goto(base + "/login?next=" + quote(hostile, safe="")); pg.fill("#login-id", "g3tester@example.com"); pg.fill("#login-pw", PW)
                pg.click("#form-login button[type=submit]"); pg.wait_for_url(base + "/", timeout=10000)
                check(urlparse(pg.url).netloc == f"127.0.0.1:{port}" and urlparse(pg.url).path == "/", f"E next={hostile!r} lands on the home page of this site")
                ctx.close()

            # ---------------- Journey C: browsing ----------------
            ctx = b.new_context(); pg = ctx.new_page(); enter_as_guest(pg, base)
            pg.wait_for_selector("[data-onclick^=\"nav('detail'\"]")
            cards0 = pg.locator("[data-onclick^=\"nav('detail'\"]").count()
            pg.fill("input[placeholder^='Search area']", "Clifton"); pg.wait_for_timeout(400)
            check(dialog(pg).count() == 0, "C1 searching shows no login prompt")
            pg.fill("input[placeholder^='Search area']", ""); pg.wait_for_timeout(300)
            sel = pg.locator("select[aria-label='Filter by property type']"); opts = sel.locator("option").all_inner_texts()
            if len(opts) > 1: sel.select_option(index=1)
            pg.locator("select[aria-label='Sort properties']").select_option(index=1) if pg.locator("select[aria-label='Sort properties'] option").count() > 1 else None
            pg.wait_for_timeout(300); check(dialog(pg).count() == 0, "C2 filtering and sorting show no login prompt")
            if len(opts) > 1: sel.select_option(index=0)
            pg.locator("[data-onclick^=\"nav('detail'\"]").first.click(); pg.wait_for_timeout(500)
            check(dialog(pg).count() == 0 and pg.locator(".backbtn").count() == 1, "C3 a property detail opens without a prompt (guest)")
            pg.click(".backbtn"); pg.wait_for_timeout(300)
            check(pg.locator("[data-onclick^=\"nav('detail'\"]").count() >= 1 and dialog(pg).count() == 0, "C4 back to the listings without a prompt")
            pg.locator("[data-onclick^=\"nav('detail'\"]").nth(1).click(); pg.wait_for_timeout(400)
            check(dialog(pg).count() == 0, "C5 a second property opens without a prompt")
            pg.goto(base + "/#/plot/ABC-123"); pg.wait_for_timeout(600)
            check(dialog(pg).count() == 0, "C6 a listing deep link opens without a prompt")
            pg.goto(base + "/listings"); pg.wait_for_selector("#create-card"); pg.wait_for_timeout(800)
            check(dialog(pg).count() == 0 and urlparse(pg.url).path == "/listings", "C7 the public listings page loads without a prompt")
            ctx.close()

            # ---------------- Journey D: Google (stub GIS + fake verifier; NOT live Google) ----------------
            def gctx(mode):
                c = b.new_context(); c.route("https://accounts.google.com/gsi/client", lambda r: r.fulfill(status=200, content_type="text/javascript", body=GIS_STUB))
                pg = c.new_page(); pg.add_init_script(f"window.__gmode = '{mode}'"); return c, pg
            c, pg = gctx("ok"); enter_as_guest(pg, gbase)
            old = c.cookies(); gid = me(pg)["user"]["id"]
            pg.click(".topnav-menu"); pg.click("#drawerNav >> text=Owner Verification System"); pg.wait_for_selector(".login-prompt")
            pg.click(".login-prompt-primary"); pg.wait_for_url("**/login?next=*"); pg.wait_for_selector("#fake-g")
            pg.click("#fake-g"); pg.wait_for_url(gbase + "/#owner-verification", timeout=10000)
            u = me(pg)["user"]
            check(u and u["role"] == "user" and u["name"] == "Google Consent", "D1 mocked Google success signs in and lands on the intended destination")
            g2 = b.new_context(); g2.add_cookies(old); gp = g2.new_page(); gp.goto(gbase + "/login")
            check(me(gp)["user"] is None, "D2 Google success revokes the old guest session of that browser")
            g2.close(); c.close()
            c, pg = gctx("bad"); enter_as_guest(pg, gbase); gid = me(pg)["user"]["id"]
            pg.click(".topnav-menu"); pg.click("#drawerNav >> text=Owner Verification System"); pg.wait_for_selector(".login-prompt")
            pg.click(".login-prompt-primary"); pg.wait_for_url("**/login?next=*"); pg.wait_for_selector("#fake-g")
            pg.click("#fake-g"); pg.wait_for_timeout(2000)
            check(urlparse(pg.url).path == "/login", "D3 a rejected Google credential does not redirect")
            u = me(pg)["user"]
            check(u and u["id"] == gid and u["role"] == "guest", "D4 a rejected Google credential keeps the guest session")
            c.close()

            # ---------------- Layouts ----------------
            for theme in ("light", "dark"):
                for w, h in ((1280, 800), (390, 844), (360, 740), (320, 568)):
                    c = b.new_context(viewport={"width": w, "height": h}); pg = c.new_page(); enter_as_guest(pg, base)
                    pg.evaluate(f"document.documentElement.dataset.theme = '{theme}'")
                    pg.evaluate("window.location.hash = '#owner-verification'"); pg.wait_for_selector(".login-prompt")
                    pg.wait_for_timeout(350)
                    r = pg.evaluate("""() => { const q = s => document.querySelector(s).getBoundingClientRect();
                      const box = q('.login-prompt'), a = q('.login-prompt-primary'), n = q('.login-prompt-secondary');
                      const top = document.elementFromPoint(a.x + a.width / 2, a.y + a.height / 2);
                      return {box: [box.left, box.top, box.right, box.bottom], vw: innerWidth, vh: innerHeight, hs: document.documentElement.scrollWidth > innerWidth,
                              ah: a.height, nh: n.height, overlap: a.bottom > n.top + 1, hit: !!top && top.closest('.login-prompt-primary') !== null,
                              color: getComputedStyle(document.querySelector('.login-prompt-title')).color, bg: getComputedStyle(document.querySelector('.login-prompt')).backgroundColor}; }""")
                    tag = f"L {theme} {w}px"
                    check(r["box"][0] >= 0 and r["box"][2] <= r["vw"] and r["box"][1] >= 0 and r["box"][3] <= r["vh"], f"{tag}: dialog inside the viewport")
                    check(not r["hs"] and r["ah"] >= 44 and r["nh"] >= 44 and not r["overlap"] and r["hit"], f"{tag}: no horizontal scroll, touch-size buttons, nothing covers the primary button")
                    check(r["color"] != r["bg"], f"{tag}: text colour differs from the dialog background ({r['color']} on {r['bg']})")
                    c.close()
            b.close()
    finally:
        for s in (srv, gsrv): s.terminate()
    print(f"\n{len(failures)} failure(s)")
    for f in failures: print(" -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
