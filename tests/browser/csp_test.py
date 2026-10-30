"""Strict-style CSP browser test (Playwright). Run:  python tests/browser/csp_test.py

Loads every HTML page (main app page, login, signup, privacy, nice-try, 404, plus messages, listings and
admin when signed in), all served without style-src 'unsafe-inline', and fails on ANY securitypolicyviolation or console CSP error. Also proves enforcement: an injected
inline style attribute IS blocked on a strict page. Throwaway database; needs a browser, so not part of `npm run test:all`."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ADMIN_PW, USER_PW = "local-demo-admin-pass", "correct-horse-battery"
HOOK = """() => { window.__csp = []; document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.effectiveDirective + ' ' + e.blockedURI)); }"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def api(pg, path, body):
    return pg.evaluate("""async ([path, body]) => {
        const c = await (await fetch('/api/v1/auth/csrf')).json();
        const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': c.csrf_token}, body: JSON.stringify(body)});
        return r.status; }""", [path, body])


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
           "LOGIN_RATE_LIMIT_PER_MIN": "100", "RATE_LIMIT_PER_MIN": "1000", "ADMIN_001_PASSWORD": ADMIN_PW}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, failures, console = f"http://127.0.0.1:{port}", [], []
    check = lambda ok, what: (print(("PASS " if ok else "FAIL ") + what), None if ok else failures.append(what))
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()

            def visit(ctx, path, what, watch=True):
                pg = ctx.new_page(); pg.add_init_script("(" + HOOK + ")()")
                if watch:  # the enforcement probe below is SUPPOSED to produce a CSP console error
                    pg.on("console", lambda m: console.append((path, m.text)) if m.type == "error" and "Content Security Policy" in m.text else None)
                resp = pg.goto(base + path); pg.wait_for_load_state("networkidle")
                csp = resp.headers.get("content-security-policy", "")
                style = [d for d in csp.split(";") if d.strip().startswith("style-src")][0]
                check("'unsafe-inline'" not in style, f"{what}: served without style-src 'unsafe-inline'")
                check(pg.evaluate("() => window.__csp") == [], f"{what}: no CSP violations on load")
                return pg

            anon = b.new_context()
            for path, what in (("/login", "login"), ("/signup", "signup"), ("/privacy", "privacy"), ("/nice-try", "nice-try"), ("/chatbot-demo", "chatbot demo"), ("/no-such-page", "404")):
                pg = visit(anon, path, what)
                if path == "/chatbot-demo":
                    pg.click(".pc-launcher"); pg.wait_for_selector(".pc-compose")
                    pg.fill(".pc-compose input, .pc-compose textarea", "average price in DHA"); pg.keyboard.press("Enter")
                    pg.wait_for_selector(".pc-row.bot", timeout=15000)
                    check(pg.evaluate("() => window.__csp") == [] and pg.locator(".pc-row.bot").count() >= 1, "chatbot demo: widget opens, answers a question, no violations")
                if path == "/privacy":
                    pg.click("[data-choice=customise]"); check(pg.evaluate("() => window.__csp") == [], "privacy: banner customise opens without violations")
                if path == "/login":
                    pg.fill("#password, input[type=password]", "x"); pg.keyboard.press("Tab"); check(pg.evaluate("() => window.__csp") == [], "login: strength meter (CSSOM width) causes no violation")

            # enforcement proof: an inline style attribute injected into a strict page is blocked
            pg = visit(anon, "/privacy", "privacy (enforcement)", watch=False)
            pg.evaluate("() => document.body.insertAdjacentHTML('beforeend', '<i id=probe style=\"color:red\">x</i>')")
            pg.wait_for_timeout(200)
            blocked = pg.evaluate("() => window.__csp")
            check(any(v.startswith("style-src") for v in blocked), "an injected inline style attribute is blocked on a strict page")

            user = b.new_context(); up = user.new_page(); up.goto(base + "/login")
            check(api(up, "/api/v1/auth/signup", {"name": "Sana Strict", "email": "sana@example.com", "password": USER_PW}) in (200, 201), "user signs up")
            for path, what in (("/messages", "messages"), ("/listings", "listings")):
                pg = visit(user, path, what)
                if path == "/listings": pg.wait_for_selector("form, #newListing, h1")
            adm = b.new_context(); ap = adm.new_page(); ap.goto(base + "/login")
            check(api(ap, "/api/v1/auth/login", {"identifier": "admin_001", "password": ADMIN_PW}) == 200, "admin logs in")
            pg = visit(adm, "/admin", "admin"); pg.wait_for_selector("#users tbody tr")
            check(pg.evaluate("() => window.__csp") == [], "admin: tables render without violations")

            # main app page: strict too, and the migrated (former inline) styles still take effect
            gctx = b.new_context(); enter_as_guest(gctx.new_page(), base, dismiss=False)   # the app page needs a session since T4
            hp = visit(gctx, "/", "main app page")
            hp.wait_for_selector("[data-onclick=\"nav('detail','p1')\"]")
            hp.click("[data-choice=reject]")
            thumb_bg = hp.evaluate("() => getComputedStyle(document.querySelector('.thumb.bg-photo')).backgroundImage")
            check("url(" in thumb_bg, "home: card photo applied through the CSSOM variable (no inline style)")
            img_url = hp.evaluate("() => (/url\\(\"?([^\")]+)\"?\\)\\s*$/.exec(getComputedStyle(document.querySelector('.thumb.bg-photo')).backgroundImage) || [])[1]")
            check(img_url.startswith(base + "/assets/") and "/css/" not in img_url, f"home: photo URL resolves against the page, not the stylesheet ({img_url})")
            # the demo photos are not in every archive, so prove the loading path with an asset that always exists
            hp.evaluate("() => document.body.insertAdjacentHTML('beforeend', '<div id=probe class=\"bg-photo\" data-bg=\"assets/logo-icon.png\" data-w=\"150\"></div>')")
            probe_url = hp.evaluate("() => (/url\\(\"?([^\")]+)\"?\\)/.exec(getComputedStyle(document.getElementById('probe')).backgroundImage) || [])[1]")
            status = hp.evaluate("async (u) => (await fetch(u)).status", probe_url)
            check(status == 200, f"observer applies data-bg to newly added elements and the image loads ({status})")
            check(hp.evaluate("() => document.getElementById('probe').style.width") == "100%", "data-w is clamped to 100%")
            hp.click("[data-onclick=\"nav('detail','p1')\"]"); hp.wait_for_selector(".hero.bg-photo")
            check("url(" in hp.evaluate("() => getComputedStyle(document.querySelector('.hero')).backgroundImage"), "detail: hero photo applied")
            check(hp.evaluate("() => document.querySelector('.d-stat[class*=\"tone-\"]') !== null"), "detail: tone class replaces inline colour")
            check(hp.evaluate("() => window.__csp") == [], "main page: home + detail views, no CSP violations")
            hp.click("text=Verify This Property"); hp.wait_for_selector(".progress-fill")
            width = hp.evaluate("() => document.querySelector('.progress-fill').style.width")
            check(width.endswith("%"), f"verify: progress width set via CSSOM ({width})")
            hp.goto(base + "/#verify-document"); hp.wait_for_load_state("networkidle")
            hp.goto(base + "/#owner-verification"); hp.wait_for_load_state("networkidle")
            check(hp.evaluate("() => window.__csp") == [], "main page: verify / owner-verification views, no CSP violations")
            b.close()
        check(console == [], f"no console CSP errors ({console[:2]})")
    finally:
        srv.terminate()
    print("OK" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
