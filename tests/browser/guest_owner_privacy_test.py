"""G6.2a-3: owner details on the property DETAIL page against the REAL local backend. Run: python tests/browser/guest_owner_privacy_test.py
A guest never sees an owner name, initials or role on any of the 8 detail pages (a neutral "Listed by ..." card with a login button instead);
the button opens the shared login dialog; a registered user sees the (synthetic) owner card, also when the page is loaded fresh (re-render hook);
the served data file holds only synthetic values; no console / CSP errors. Display-only protection: properties.js is still a public file."""
import os, re, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import enter_as_guest, enter_as_user  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS, problems = [], []
OWNERS = ["Demo Person Alpha", "Demo Person Bravo", "Demo Person Charlie", "Demo Person Delta", "Demo Company Echo", "Demo Person Foxtrot", "Demo Company Golf", "Demo Person Hotel"]


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(detail)) if not cond and detail else ""))


def act(pg, call):
    pg.evaluate("(c) => { const b = document.createElement('button'); b.setAttribute('data-onclick', c); document.body.appendChild(b); b.click(); b.remove(); }", call)


def open_detail(pg, pid):
    act(pg, f"nav('detail','{pid}')"); pg.wait_for_selector(".owner-card", timeout=8000)


def main() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    tmp = Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
           "LOGIN_RATE_LIMIT_PER_MIN": "300", "RATE_LIMIT_PER_MIN": "300"}
    env.pop("GOOGLE_CLIENT_ID", None)
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    watch = lambda pg: (pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None),
                        pg.on("pageerror", lambda e: problems.append(f"pageerror: {str(e)[:200]}")))
    try:
        for _ in range(80):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()

            # the served data file itself
            c0 = b.new_context(); pg0 = c0.new_page(); watch(pg0); pg0.goto(base + "/login")
            text = pg0.evaluate("fetch('/js/data/properties.js').then(r => r.text())")
            cn = re.findall(r"(?<!\d)\d{5}-[\d*]{7}-\d(?!\d)", text); ow = re.findall(r"owner:'([^']*)'", text)
            check("served properties.js: only 00000- CNICs and 'Demo ...' owners", cn and all(x.startswith("00000-") for x in cn) and len(ow) == 8 and all(o.startswith("Demo ") for o in ow), (len(cn), ow))
            c0.close()

            # guest
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg); enter_as_guest(pg, base); pg.wait_for_selector("#app *", state="attached")
            for i in range(1, 9):
                open_detail(pg, f"p{i}")
                body = pg.inner_text("#app"); html = pg.inner_html("#app")
                check(f"guest p{i}: no owner name, initials block or CNIC", not any(o in body or o in html for o in OWNERS) and pg.locator(".owner-avatar").count() == 0 and not re.search(r"\d{5}-\d{7}-\d", html), body[:80])
                check(f"guest p{i}: neutral card with the login note; price and title still shown", pg.locator("[data-owner-hidden]").count() == 1 and "Log in or sign up to see the owner details." in body
                      and "Listed by" in body and "PKR" in body and "Verify This Property" in body)
            pg.locator("[data-owner-hidden] button").click(); pg.wait_for_selector(".login-prompt", timeout=5000)
            check("guest: the card's button opens the shared Login required dialog (one, no navigation)", pg.locator(".login-prompt").count() == 1 and pg.url == base + "/")
            me = pg.evaluate("fetch('/api/v1/auth/me').then(r=>r.json())")["user"]
            check("guest: still a guest after the dialog (session not deleted)", me["role"] == "guest")
            pg.keyboard.press("Escape")
            ctx.close()

            # registered user, loaded fresh
            ctx = b.new_context(); pg = ctx.new_page(); watch(pg); enter_as_user(pg, base); pg.goto(base + "/"); pg.wait_for_selector("#app *", state="attached")
            open_detail(pg, "p1")
            pg.wait_for_function("() => document.querySelector('.owner-name') && !document.querySelector('[data-owner-hidden]')", timeout=8000)
            check("user: owner card with the synthetic owner, initials and role", pg.inner_text(".owner-name") == "Demo Person Alpha" and pg.inner_text(".owner-avatar") == "DP" and "·" in pg.inner_text(".owner-role"))
            # a detail page opened BEFORE the session answer arrives re-renders into the owner card (hook in main.js)
            pg.reload(); pg.wait_for_selector("#app *", state="attached"); open_detail(pg, "p2")
            pg.wait_for_function("() => !document.querySelector('[data-owner-hidden]') && document.querySelector('.owner-name')", timeout=8000)
            check("user: after a reload the owner card is shown (neutral card never sticks)", pg.inner_text(".owner-name") == "Demo Person Bravo")
            ctx.close()
            b.close()
        check("no console errors, page errors or CSP violations", not problems, problems[:4])
    finally:
        srv.terminate()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed of {len(RESULTS)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
