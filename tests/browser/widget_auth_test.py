"""G4b: embedded chatbot widget (frontend/widget/chatbot.js) authorization behaviour, with a MOCKED API (no server, no AI credentials).
Run:  python tests/browser/widget_auth_test.py

The real widget, CSS and demo page are served from the working tree under two fake hosts: http://kpt.test (the KPT application, first party)
and http://thirdparty.test (an unrelated site embedding the widget). Every /api/chat answer is scripted, so each status/code is exercised exactly.
Covers: 401 auth_required, 403 guest_not_allowed (fixed Login required card, exact text/action, KPT-origin link with a fixed safe `next`, no raw
backend text, no assistant bubble, no Try again, composer locked, no resend, one prompt), 403 password_change_required (existing /login?change=1),
unrelated errors (403 forbidden / csrf_failed, 429, 500, network failure, timeout) keep ordinary handling with Try again, a registered user's normal
chat, Start new chat unlocking, widget configuration (title/greeting/chips/apiUrl) still working, third-party embedding (link opens KPT, never the
embedding site or cfg.apiUrl; explicit not-signed-in-here note), and the card at 1280/390/360/320 px."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
W = ROOT / "frontend" / "widget"
KPT, TP = "http://kpt.test", "http://thirdparty.test"
RAW = ["Please log in to continue.", "Create an account or log in to use this feature.", "You must change your password before continuing."]
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(detail)) if not cond and detail else ""))


class Scenario:
    def __init__(self): self.mode = "ok"; self.calls = []; self.pending = []

    def answer(self):
        m = self.mode
        table = {
            "401": (401, {"error": "Please log in to continue.", "code": "auth_required"}),
            "guest": (403, {"error": "Create an account or log in to use this feature.", "code": "guest_not_allowed"}),
            "password": (403, {"error": "You must change your password before continuing.", "code": "password_change_required"}),
            "forbidden": (403, {"error": "You do not have permission to do that.", "code": "forbidden"}),
            "csrf": (403, {"error": "CSRF check failed.", "code": "csrf_failed"}),
            "403plain": (403, {"error": "Something else was refused."}),
            "401other": (401, {"error": "Token expired somewhere else.", "code": "other_code"}),
            "429": (429, {"error": "Too many requests. Please wait a moment.", "code": "rate_limited"}),
            "500": (500, {"error": "Internal error.", "code": "server_error"}),
            "ok": (200, {"reply": "Median prices in DHA are about 4.2 crore.", "source": "offline", "from_data": True, "message_id": "m12345678"}),
        }
        return table[m]


def install(ctx, sc):
    def handler(route):
        req = route.request; u = req.url; cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "POST, GET, OPTIONS"}
        path = u.split("//", 1)[1].split("/", 1)[1].split("?")[0] if "//" in u else ""
        if req.method == "OPTIONS": return route.fulfill(status=204, headers=cors)
        if u.startswith(KPT) and path in ("static/chatbot.js", "static/chatbot.css"):
            return route.fulfill(status=200, content_type="text/javascript" if path.endswith(".js") else "text/css", headers=cors, body=(W / path.split("/")[1]).read_text(encoding="utf-8"))
        if u.startswith(KPT) and path == "chatbot-demo":
            return route.fulfill(status=200, content_type="text/html", body=(W / "demo.html").read_text(encoding="utf-8"))
        if path in ("api/chat", "custom-chat"):
            sc.calls.append((u, json.loads(req.post_data or "{}")))
            if sc.mode == "network": return route.abort()
            if sc.mode == "hang": sc.pending.append(route); return  # never answers (released at the end of the test)
            st, body = sc.answer()
            return route.fulfill(status=st, content_type="application/json", headers=cors, body=json.dumps(body))
        if u.startswith(TP) and path == "":
            return route.fulfill(status=200, content_type="text/html", body=f'<!doctype html><title>Third party</title><h1>Acme Realty</h1><script src="{KPT}/static/chatbot.js" defer></script>')
        return route.fulfill(status=200, content_type="text/plain", body="")
    ctx.route("**/*", handler)


def open_widget(b, url, sc, init=None, vp=None, clock=False):
    ctx = b.new_context(viewport=vp or {"width": 1280, "height": 800}); install(ctx, sc)
    pg = ctx.new_page(); errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    if init: pg.add_init_script(init)
    if clock: pg.clock.install()
    pg.goto(url); pg.wait_for_selector(".pc-launcher"); pg.click(".pc-launcher"); pg.wait_for_selector(".pc-compose")
    return ctx, pg, errors


def say(pg, text):
    pg.fill(".pc-input", text); pg.keyboard.press("Enter")


def card(pg):
    return pg.evaluate("""() => { const c = document.querySelector('.pc-login'); if (!c) return null; const a = c.querySelector('a');
      return {n: document.querySelectorAll('.pc-login').length, title: c.querySelector('.pc-login-title').textContent, text: c.querySelector('.pc-login-text').textContent,
      action: a.textContent, href: a.href, target: a.getAttribute('target'), rel: a.getAttribute('rel'), note: (c.querySelector('.pc-login-note') || {}).textContent || null}; }""")


def body_text(pg): return pg.evaluate("() => document.querySelector('.pc-root').innerText")


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch()
        LOGIN = KPT + "/login?next=%2Fchatbot-demo"

        # ---- first party: both authorization failures ----
        for mode, label in (("401", "anonymous 401 auth_required"), ("guest", "guest 403 guest_not_allowed")):
            sc = Scenario(); sc.mode = mode
            ctx, pg, errs = open_widget(b, KPT + "/chatbot-demo", sc)
            say(pg, "average price in DHA"); pg.wait_for_selector(".pc-login")
            c = card(pg)
            check(f"{label}: fixed title, message and action", (c["title"], c["text"], c["action"]) == ("Login required", "Create an account or log in to use this feature.", "Log in / Sign up"), c)
            check(f"{label}: link is the KPT login with the fixed safe destination", c["href"] == LOGIN, c["href"])
            check(f"{label}: first-party link opens in the same tab, no third-party note", c["target"] is None and c["note"] is None, c)
            txt = body_text(pg)
            check(f"{label}: no raw backend wording shown outside the fixed text" if mode == "guest" else f"{label}: no raw backend wording", "Please log in to continue." not in txt, txt[:200])
            check(f"{label}: no assistant bubble, no error row, no Try again", pg.locator(".pc-row.bot:not(:has(.pc-typing))").count() == 1 and pg.locator(".pc-row.err").count() == 0 and pg.locator(".pc-retry").count() == 0,
                  pg.locator(".pc-row").count())
            check(f"{label}: the rejected message is not kept as a sent message", pg.locator(".pc-row.user").count() == 0)
            check(f"{label}: composer locked", pg.is_disabled(".pc-input") and pg.is_disabled(".pc-send"))
            # force more attempts the page could make: form submit and chip click
            pg.evaluate("() => { const i = document.querySelector('.pc-input'); i.disabled = false; i.value = 'again'; document.querySelector('.pc-compose').requestSubmit(); }"); pg.wait_for_timeout(300)
            check(f"{label}: nothing is resent and there is still exactly one prompt", len(sc.calls) == 1 and card(pg)["n"] == 1, (len(sc.calls), card(pg)))
            pg.reload(); pg.wait_for_selector(".pc-launcher")
            check(f"{label}: no stale prompt or retry text is persisted across a reload", pg.locator(".pc-login").count() == 0 and "average price" not in pg.evaluate("() => sessionStorage.getItem('pc-state')"))
            check(f"{label}: no page errors", not errs, errs)
            ctx.close()

        # ---- Start new chat unlocks; registered user chats normally ----
        sc = Scenario(); sc.mode = "401"
        ctx, pg, errs = open_widget(b, KPT + "/chatbot-demo", sc)
        say(pg, "hello"); pg.wait_for_selector(".pc-login")
        sc.mode = "ok"; pg.click("[data-a=reset]")
        check("Start new chat removes the card and re-enables the composer", pg.locator(".pc-login").count() == 0 and not pg.is_disabled(".pc-input"))
        say(pg, "average price in DHA"); pg.wait_for_selector(".pc-row.bot:not(.err) .pc-bubble:has-text('Median prices')")
        meta = pg.locator(".pc-row.bot:not(.err) .pc-meta").inner_text()
        check("registered user: normal answer, meta line, no card, no error row", "property data" in meta.lower() and pg.locator(".pc-login").count() == 0 and pg.locator(".pc-row.err").count() == 0, meta)
        check("registered user: the request carried session_id and message only", set(sc.calls[-1][1]) == {"session_id", "message"}, sc.calls[-1][1])
        ctx.close()

        # ---- password change ----
        sc = Scenario(); sc.mode = "password"
        ctx, pg, errs = open_widget(b, KPT + "/chatbot-demo", sc)
        say(pg, "hello"); pg.wait_for_selector(".pc-login"); c = card(pg)
        check("403 password_change_required: Change password card to the existing screen", (c["title"], c["action"], c["href"]) == ("Password change required", "Change password", KPT + "/login?change=1"), c)
        check("403 password_change_required: not the login-required text, no auto-navigation", c["text"] != "Create an account or log in to use this feature." and pg.url.endswith("/chatbot-demo"))
        ctx.close()

        # ---- unrelated errors keep ordinary handling (Try again allowed) ----
        for mode, shown in (("forbidden", "You do not have permission to do that."), ("csrf", "CSRF check failed."), ("403plain", "Something else was refused."),
                            ("401other", "Token expired somewhere else."), ("429", "Too many requests. Please wait a moment."), ("500", "Internal error."), ("network", "couldn't reach the server")):
            sc = Scenario(); sc.mode = mode
            ctx, pg, errs = open_widget(b, KPT + "/chatbot-demo", sc)
            say(pg, "estimate a plot"); pg.wait_for_selector(".pc-row.err")
            check(f"unrelated error '{mode}': ordinary error row with Try again, no login card", pg.locator(".pc-login").count() == 0 and pg.locator(".pc-retry").count() == 1 and shown in pg.locator(".pc-row.err").inner_text(), pg.locator(".pc-row.err").inner_text())
            sc.mode = "ok"; pg.click(".pc-retry"); pg.wait_for_selector(".pc-row.bot:not(.err) .pc-bubble:has-text('Median prices')")
            check(f"unrelated error '{mode}': Try again still works for non-authorization errors", len(sc.calls) == 2 and sc.calls[0][1]["message"] == sc.calls[1][1]["message"])
            ctx.close()
        sc = Scenario(); sc.mode = "hang"
        ctx, pg, errs = open_widget(b, KPT + "/chatbot-demo", sc, clock=True)
        say(pg, "slow question"); pg.wait_for_timeout(200); pg.clock.fast_forward(61000)
        pg.wait_for_selector(".pc-row.err")
        check("timeout: friendly timeout row, no login card", "took too long" in pg.locator(".pc-row.err").inner_text() and pg.locator(".pc-login").count() == 0)
        [r.abort() for r in sc.pending]; ctx.close()

        # ---- configuration still honoured; login origin never taken from config ----
        cfgjs = "window.PropertyChatConfig = {title:'Acme Bot', brandText:'Acme', greeting:'Welcome to Acme!', chips:['Chip one','Chip two'], apiUrl:'%s/custom-chat', poweredBy:'AcmeAI'};" % KPT
        sc = Scenario(); sc.mode = "ok"
        ctx, pg, errs = open_widget(b, KPT + "/chatbot-demo", sc, init=cfgjs)
        check("config: title, brand, greeting, chips, poweredBy applied", pg.inner_text(".pc-title") == "Acme Bot" and pg.inner_text(".pc-brand") == "Acme" and "Welcome to Acme!" in body_text(pg)
              and pg.locator(".pc-chip").count() == 2 and "AcmeAI" in pg.inner_text(".pc-foot"))
        pg.click(".pc-chip >> nth=0"); pg.wait_for_selector(".pc-row.bot:not(.err) .pc-bubble:has-text('Median prices')")
        check("config: custom apiUrl is the endpoint that is called", sc.calls[0][0] == KPT + "/custom-chat", sc.calls[0][0])
        ctx.close()
        evil = "window.PropertyChatConfig = {apiUrl:'http://evil.example/custom-chat'};"
        sc = Scenario(); sc.mode = "401"
        ctx, pg, errs = open_widget(b, KPT + "/chatbot-demo", sc, init=evil)
        ctx.route("http://evil.example/**", lambda r: r.fulfill(status=401, content_type="application/json", headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type"}, body='{"error":"x","code":"auth_required"}'))
        say(pg, "hi"); pg.wait_for_selector(".pc-login")
        check("login link ignores a page-supplied apiUrl (stays on the KPT origin)", card(pg)["href"] == LOGIN, card(pg))
        ctx.close()

        # ---- third-party embedding ----
        for mode in ("401", "guest"):
            sc = Scenario(); sc.mode = mode
            ctx, pg, errs = open_widget(b, TP + "/", sc)
            say(pg, "average price in DHA"); pg.wait_for_selector(".pc-login"); c = card(pg)
            check(f"third party ({mode}): fixed title/message/action", (c["title"], c["text"], c["action"]) == ("Login required", "Create an account or log in to use this feature.", "Log in / Sign up"), c)
            check(f"third party ({mode}): link opens the KPT origin (not the embedding site), new tab, noopener", c["href"] == LOGIN and c["target"] == "_blank" and "noopener" in (c["rel"] or ""), c)
            check(f"third party ({mode}): explains that being logged in on this site does not sign the widget in", c["note"] and "does not sign in this embedded assistant" in c["note"] and "Karachi Property Trust website" in c["note"], c["note"])
            check(f"third party ({mode}): nothing was resent, one prompt", len(sc.calls) == 1 and c["n"] == 1)
            check(f"third party ({mode}): the embedding page's own content is untouched", pg.inner_text("h1") == "Acme Realty")
            ctx.close()
        sc = Scenario(); sc.mode = "ok"
        ctx, pg, errs = open_widget(b, TP + "/", sc)
        say(pg, "hello"); pg.wait_for_selector(".pc-row.bot:not(.err) .pc-bubble:has-text('Median prices')")
        check("third party: when the API does answer, chat works exactly as before", pg.locator(".pc-login").count() == 0)
        ctx.close()

        # ---- layout of the card ----
        for w in (1280, 390, 360, 320):
            sc = Scenario(); sc.mode = "guest"
            ctx, pg, errs = open_widget(b, TP + "/", sc, vp={"width": w, "height": 640})
            say(pg, "hi"); pg.wait_for_selector(".pc-login"); pg.wait_for_timeout(600)   # let the panel's open animation finish before measuring
            m = pg.evaluate("""() => { const c = document.querySelector('.pc-login').getBoundingClientRect(), a = document.querySelector('.pc-login-btn').getBoundingClientRect(), p = document.querySelector('.pc-panel').getBoundingClientRect();
              return {cl: c.left, cr: c.right, pl: p.left, pr: p.right, ah: a.height, sw: document.documentElement.scrollWidth, iw: innerWidth}; }""")
            check(f"card layout at {w}px: inside the panel and viewport, tap target >= 44px, no sideways scroll",
                  m["cl"] >= m["pl"] - 0.5 and m["cr"] <= m["pr"] + 0.5 and m["pr"] <= m["iw"] and m["ah"] >= 44 and m["sw"] <= m["iw"], m)
            ctx.close()
        b.close()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed of {len(RESULTS)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
