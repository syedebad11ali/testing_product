"""Browser test for cookies, consent and remember-me (Playwright). Run:  python tests/browser/cookies_test.py

Covers (T5a): no banner on /login, /signup, /developer-login, /nice-try; banner after sign-up, password login, guest entry and Google
(fake verifier, not live Google); a saved choice is not asked again. Also: banner choices (reject / accept), nothing optional before consent, theme persisted only with consent,
sign-up + Remember me round trip (token rotates, survives loss of the session cookie), chat continuity in a
new tab, Privacy page (devices, Forget me clears everything), no console errors or CSP violations.
Throwaway database; not part of `npm run test:all` because it needs a browser."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def names(ctx):
    return {c["name"]: c["value"] for c in ctx.cookies()}


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
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

            # 0. T5a: no banner on any entry page; it appears on the first page after sign-up / login / guest entry
            def quiet(pg, path, ready):
                pg.goto(base + path); pg.wait_for_selector(ready); pg.wait_for_timeout(400)
                assert pg.locator("#consentBanner").count() == 0, f"consent banner shown too early on {path}"
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg)
            quiet(pg, "/login", "#guest-btn"); quiet(pg, "/signup", "#form-signup")
            quiet(pg, "/developer-login", "form"); quiet(pg, "/nice-try", "body")
            assert "kpt_consent" not in names(ctx)
            pg.goto(f"{base}/signup"); pg.fill("#su-name", "Entry Tester"); pg.fill("#su-email", "entry@example.com")
            pg.fill("#su-pw", "correct-horse-battery-9"); pg.fill("#su-confirm", "correct-horse-battery-9")
            pg.click("#form-signup button[type=submit]"); pg.wait_for_url(f"{base}/", wait_until="commit")
            pg.wait_for_selector("#consentBanner"); ctx.close()
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg)       # password login, no choice recorded yet
            pg.goto(f"{base}/login"); pg.wait_for_selector("#form-login:not([hidden])"); pg.fill("#login-id", "entry@example.com")
            pg.fill("#login-pw", "correct-horse-battery-9"); pg.click("#form-login button[type=submit]")
            pg.wait_for_url(f"{base}/", wait_until="commit"); pg.wait_for_selector("#consentBanner")
            pg.click("[data-choice=reject]"); assert pg.locator("#consentBanner").count() == 0 and "kpt_consent" in names(ctx)
            pg.evaluate("fetch('/api/v1/auth/logout',{method:'POST',headers:{'X-CSRF-Token':document.cookie.match(/kpt_csrf=([^;]+)/)?.[1]||''}})")
            quiet(pg, "/login", "#guest-btn")                               # saved choice: still nothing on /login
            pg.fill("#login-id", "entry@example.com"); pg.fill("#login-pw", "correct-horse-battery-9"); pg.click("#form-login button[type=submit]")
            pg.wait_for_url(f"{base}/", wait_until="commit"); pg.wait_for_selector("[data-onclick^=\"nav('detail'\"]", timeout=15000); pg.wait_for_timeout(400)
            assert pg.locator("#consentBanner").count() == 0, "banner reopened although a choice is saved"
            ctx.close()
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg)       # guest entry, no choice recorded yet
            pg.goto(f"{base}/login"); pg.click("#guest-btn"); pg.wait_for_url(f"{base}/", timeout=8000)
            pg.wait_for_selector("#consentBanner"); assert pg.evaluate("fetch('/api/v1/auth/me').then(r=>r.json())")["user"]["role"] == "guest"
            pg.click("[data-choice=all]"); assert pg.locator("#consentBanner").count() == 0 and "p%3D1" in names(ctx)["kpt_consent"]
            ctx.close()

            # 1. reject: banner goes away, only the consent record exists, theme is not persisted
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg)
            enter_as_guest(pg, base, dismiss=False); pg.wait_for_selector("#consentBanner")   # T5a: the banner appears after guest entry
            assert not {"kpt_prefs", "kpt_remember", "kpt_chat"} & set(names(ctx)), "optional cookie before consent"
            room = pg.evaluate("() => ({pad: parseFloat(getComputedStyle(document.body).paddingBottom), h: document.getElementById('consentBanner').offsetHeight, cls: document.body.classList.contains('has-consent')})")
            assert room["cls"] and room["pad"] >= room["h"], f"page bottom is not reserved while the banner is open: {room}"
            a, r = pg.locator("[data-choice=all]").bounding_box(), pg.locator("[data-choice=reject]").bounding_box()
            assert a["height"] == r["height"] and abs(a["width"] - r["width"]) < 2, "Accept and Reject must be equally prominent"
            pg.set_viewport_size({"width": 360, "height": 640}); pg.click("[data-choice=customise]")
            assert pg.evaluate("() => document.getElementById('consentBanner').getBoundingClientRect().bottom <= window.innerHeight"), "expanded banner overflows the viewport"
            assert pg.evaluate("() => parseFloat(getComputedStyle(document.body).paddingBottom) >= document.getElementById('consentBanner').offsetHeight"), "reserve did not follow the banner height"
            pg.set_viewport_size({"width": 1280, "height": 720})
            pg.click("[data-choice=reject]") if pg.locator("[data-choice=reject]").is_visible() else pg.click("[data-choice=customise]")
            assert pg.locator("#consentBanner").count() == 0
            assert not pg.evaluate("() => document.body.classList.contains('has-consent') || document.documentElement.style.getPropertyValue('--consent-h')"), "space stayed reserved after the choice"
            assert names(ctx).get("kpt_consent") and "p%3D0" in names(ctx)["kpt_consent"] + "p%3D0" and "kpt_prefs" not in names(ctx)
            pg.click("#themeToggle"); assert pg.evaluate("document.documentElement.dataset.theme") == "dark"
            assert "kpt_prefs" not in names(ctx), "theme must not be stored without Preferences consent"
            pg.reload(); assert pg.locator("#consentBanner").count() == 0, "banner asked again after a choice"
            assert pg.evaluate("document.documentElement.dataset.theme") == "light"
            ctx.close()

            # 2. accept all: theme persists across reload (applied before first paint by theme-init.js)
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg)
            enter_as_guest(pg, base, dismiss=False); pg.wait_for_selector("#consentBanner"); pg.click("[data-choice=all]")   # T5a: choice made on the first app page
            pg.click("#themeToggle"); assert "dark" in names(ctx).get("kpt_prefs", "")
            pg.reload(); assert pg.evaluate("document.documentElement.dataset.theme") == "dark", "saved theme not applied"

            # 3. sign up, log out, log in with Remember me; token rotates and survives losing the session cookie
            pg.goto(f"{base}/signup"); pg.fill("#su-name", "Cookie Tester"); pg.fill("#su-email", "cookie@example.com")
            pg.fill("#su-pw", "correct-horse-battery-9"); pg.fill("#su-confirm", "correct-horse-battery-9")
            pg.click("#form-signup button[type=submit]"); pg.wait_for_url(f"{base}/", wait_until="commit")
            pg.evaluate("fetch('/api/v1/auth/logout',{method:'POST',headers:{'X-CSRF-Token':document.cookie.match(/kpt_csrf=([^;]+)/)?.[1]||''}})")
            pg.goto(f"{base}/login"); pg.wait_for_selector("#form-login:not([hidden])")
            pg.fill("#login-id", "cookie@example.com"); pg.fill("#login-pw", "correct-horse-battery-9"); pg.check("#login-remember")
            pg.click("#form-login button[type=submit]"); pg.wait_for_url(f"{base}/", wait_until="commit")
            first = names(ctx).get("kpt_remember"); assert first, "no remember cookie after ticking Remember me"
            ctx.clear_cookies(name="kpt_session")
            who = pg.evaluate("fetch('/api/v1/auth/me').then(r=>r.json())")
            assert who.get("user") and who["user"]["name"] == "Cookie Tester", f"remember token did not restore the session: {who}"
            assert names(ctx).get("kpt_remember") != first, "remember token was not rotated"

            # 4. chat continuity in a brand-new tab (sessionStorage is empty there)
            pg.wait_for_selector("[data-onclick^=\"nav('detail'\"]", timeout=15000)  # app scripts are running
            pg.click("#chatFab"); pg.fill(".assistant-input", "prices in Gulshan"); pg.keyboard.press("Enter")
            pg.wait_for_selector(".chat-feedback", timeout=20000)  # only replies carry feedback buttons
            assert "kpt_chat" in names(ctx), "chat cookie missing after Preferences consent"
            pg.goto(f"{base}/#/plot/DEMO-KPT-8103"); pg.wait_for_selector(".listing h1", timeout=15000)
            assert "DEMO-KPT-8103" in names(ctx).get("kpt_prefs", ""), "recently viewed listing not recorded"
            tab = ctx.new_page(); watch(tab); tab.goto(base); tab.wait_for_selector("[data-onclick^=\"nav('detail'\"]", timeout=15000); tab.click("#chatFab")
            tab.wait_for_selector("text=Welcome back", timeout=10000)
            assert "prices in Gulshan" in tab.inner_text(".assistant-thread"), "conversation not restored"
            assert "Cookie" in tab.inner_text(".assistant-thread"), "signed-in first name missing from welcome"
            assert tab.locator(".chat-chip", has_text="Continue with").count() == 1, "last-viewed chip missing"
            tab.close()

            # 5. privacy page: devices listed, Forget me clears everything non-essential
            pg.goto(f"{base}/privacy"); pg.wait_for_selector("#account:not([hidden])")
            pg.wait_for_selector("#devices li", timeout=8000)
            pg.click("#forget"); pg.wait_for_selector("text=Non-essential cookies were removed")
            left = set(names(ctx)); assert not ({"kpt_prefs", "kpt_consent", "kpt_remember", "kpt_chat"} & left), left
            # 6. Google: second server with a FAKE verifier (no network, not live Google). The Google button script cannot load
            # offline, so the callback is driven through the real endpoints; the landing page is the same "/" the callback opens.
            gport = free_port()
            genv = {**env, "PORT": str(gport), "LOCAL_DB_PATH": str(tmp / "g.sqlite3"), "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com"}
            gsrv = subprocess.Popen([sys.executable, "tests/browser/helpers/fake_google_server.py"], cwd=ROOT, env={**genv, "PYTHONPATH": str(ROOT)},
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(60):
                    try: socket.create_connection(("127.0.0.1", gport), 0.2).close(); break
                    except OSError: time.sleep(0.25)
                gbase = f"http://127.0.0.1:{gport}"
                ctx = b.new_context(); pg = ctx.new_page(); watch(pg)
                quiet_g = lambda: (pg.wait_for_selector("#guest-btn"), pg.wait_for_timeout(400), pg.locator("#consentBanner").count() == 0)
                pg.goto(gbase + "/login"); assert quiet_g()[2], "banner on /login (Google configured)"
                res = pg.evaluate("""async () => {
                  const cfg = await (await fetch('/api/v1/auth/google/config')).json();
                  const csrf = (await (await fetch('/api/v1/auth/csrf')).json()).csrf_token;
                  const r = await fetch('/api/v1/auth/google', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
                                                                 body: JSON.stringify({credential: cfg.nonce})});
                  return {configured: cfg.configured, status: r.status, body: await r.json()}; }""")
                assert res["configured"] and res["status"] == 200 and res["body"].get("redirect") == "/", res
                pg.goto(gbase + res["body"]["redirect"]); pg.wait_for_selector("#consentBanner")
                assert pg.evaluate("fetch('/api/v1/auth/me').then(r=>r.json())")["user"]["name"] == "Google Consent"
                pg.click("[data-choice=reject]"); pg.reload(); pg.wait_for_timeout(400)
                assert pg.locator("#consentBanner").count() == 0, "banner reopened after Google sign-in with a saved choice"
                ctx.close()
            finally:
                gsrv.terminate()
            b.close()
    finally:
        srv.terminate()
    for x in problems: print("PROBLEM:", x)
    print("cookies:", "FAIL" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
