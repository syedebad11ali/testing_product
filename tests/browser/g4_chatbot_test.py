"""G4a3: the main Property Assistant in a real browser (Playwright), against the real backend with NO AI credentials
(the offline rule-based engine answers), so nothing here depends on a live model.

Guest: every launch path shows the shared login dialog, never opens the panel, sends no chat request, keeps the guest session.
Registered user: panel opens, a message gets an answer, history and continuity work (with Preferences consent).
Rejections: an expired session (real 401 from the server), a rejected /chat/session and a rejected /chat/feedback show the
dialog once, no raw error text, no assistant bubble, no retry. 403 forbidden / csrf_failed are NOT treated as a login problem.
Run: python tests/browser/g4_chatbot_test.py"""
import json, os, re, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest, enter_as_user  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ("auth_required", "guest_not_allowed", "Please log in to continue", "Create an account or log in to use this feature.", "401", "403")
CHAT_URL = re.compile(r"/api(/v1)?/chat(/|$|\?)")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"),
           "APP_ENV": "development", "LOGIN_RATE_LIMIT_PER_MIN": "200", "RATE_LIMIT_PER_MIN": "200"}
    env.pop("GEMINI_API_KEY", None); env.pop("OPENAI_API_KEY", None)
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, failures, problems = f"http://127.0.0.1:{port}", [], []

    def check(ok, msg):
        print(("PASS " if ok else "FAIL ") + msg)
        if not ok: failures.append(msg)

    def watch(pg):
        reqs = []
        pg.on("request", lambda r: reqs.append((r.method, r.url)) if CHAT_URL.search(r.url) else None)
        pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and ("Content Security" in m.text or "[kpt]" in m.text) else None)
        return reqs

    def ready(pg):
        pg.wait_for_selector("[data-onclick^=\"nav('detail'\"]", timeout=15000)

    def dialogs(pg):
        return pg.locator(".login-prompt").count()

    def close_dialog(pg):
        if dialogs(pg):
            pg.click(".login-prompt-secondary"); pg.wait_for_selector(".login-prompt", state="detached", timeout=3000)

    def me(pg):
        return pg.evaluate("fetch('/api/v1/auth/me').then(r=>r.json()).then(d=>d.user)")

    def panel_open(pg):
        return pg.locator("#chatPanel.open").count() == 1

    def bubbles(pg):
        return pg.locator("#chatBody .chat-message-bubble").count()

    def body_text(pg):
        return pg.inner_text("#chatBody") if pg.locator("#chatBody").count() else ""

    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()

            # ---------------- 1. GUEST: every launch path -> dialog, nothing else
            ctx = b.new_context(viewport={"width": 390, "height": 900}); pg = ctx.new_page(); reqs = watch(pg)
            enter_as_guest(pg, base); ready(pg)
            before = pg.evaluate("JSON.stringify([sessionStorage, localStorage])"); bubbles0 = bubbles(pg)
            pg.click("#chatFab"); pg.wait_for_selector(".login-prompt", timeout=5000)
            check(pg.inner_text(".login-prompt-title") == "Login required", "guest: floating button shows the Login required dialog")
            check(dialogs(pg) == 1 and not panel_open(pg), "guest: one dialog, the chat panel stays closed")
            check(pg.get_attribute(".login-prompt-primary", "href").startswith("/login"), "guest: the dialog links to the login page")
            close_dialog(pg)
            pg.evaluate("for (let i=0;i<3;i++) document.getElementById('chatFab').click()"); pg.wait_for_selector(".login-prompt")
            pg.wait_for_timeout(300)
            check(dialogs(pg) == 1, "guest: repeated clicks never create a second dialog"); close_dialog(pg)
            pg.click(".topnav-menu"); pg.click(".drawer-item[data-onclick^='openChat']"); pg.wait_for_selector(".login-prompt", timeout=5000)
            check(dialogs(pg) == 1 and not panel_open(pg), "guest: drawer chatbot entry shows the dialog, panel closed"); close_dialog(pg)
            pg.click(".topnav-menu"); pg.wait_for_timeout(400)   # the drawer closed itself after the previous entry
            pg.click(".drawer-mission"); pg.wait_for_selector(".login-prompt", timeout=5000)
            check(dialogs(pg) == 1 and not panel_open(pg), "guest: 'Learn how verification works' shows the dialog, panel closed"); close_dialog(pg)
            pg.locator("[data-onclick^=\"nav('detail'\"]").first.click(); pg.wait_for_selector("[data-onclick=\"openChat()\"]", timeout=8000)
            labels = [t.strip() for t in pg.locator("[data-onclick=\"openChat()\"]").all_inner_texts()]
            for i in range(pg.locator("[data-onclick=\"openChat()\"]").count()):
                pg.locator("[data-onclick=\"openChat()\"]").nth(i).click(); pg.wait_for_selector(".login-prompt", timeout=5000)
                check(dialogs(pg) == 1 and not panel_open(pg), f"guest: property page button '{labels[i]}' shows the dialog, panel closed"); close_dialog(pg)
            # 'Ask the assistant' exists only on a FOUND listing page (not on "Listing not found"), so open a real dataset listing; this step is unconditional
            pg.goto(base + "/#/plot/DEMO-KPT-1648"); pg.reload(); pg.wait_for_selector(".listing-actions", timeout=15000)
            asks = pg.locator(".listing-actions [data-onclick=\"openChat()\"]")
            check(asks.count() == 1 and asks.first.inner_text().strip() == "Ask the assistant", "guest: the listing page has its 'Ask the assistant' button")
            asks.first.click(); pg.wait_for_selector(".login-prompt", timeout=5000)
            check(dialogs(pg) == 1 and not panel_open(pg), "guest: 'Ask the assistant' shows the dialog, panel closed"); close_dialog(pg)
            check(reqs == [], f"guest: NO chat API request was sent ({reqs})")
            check((me(pg) or {}).get("role") == "guest", "guest: the guest session is still valid")
            check(pg.evaluate("JSON.stringify([sessionStorage, localStorage])") == before and bubbles(pg) == bubbles0, "guest: no chat history or stored state changed")
            ctx.close()

            # ---------------- 2. REGISTERED USER: normal chat, history, continuity
            ctx = b.new_context(viewport={"width": 390, "height": 900}); pg = ctx.new_page(); reqs = watch(pg)
            enter_as_user(pg, base, dismiss=False); pg.wait_for_selector("#consentBanner"); pg.click("[data-choice=all]"); ready(pg)
            pg.click("#chatFab"); pg.wait_for_selector("#chatPanel.open", timeout=5000)
            check(dialogs(pg) == 0 and panel_open(pg), "user: the Property Assistant opens normally")
            pg.fill(".assistant-input", "prices of houses in Gulshan"); pg.keyboard.press("Enter")
            pg.wait_for_selector(".chat-feedback", timeout=20000)
            check(pg.locator("#chatBody .chat-message-bubble").count() >= 3, "user: the question and an answer are in the transcript")
            check(any(m == "POST" for m, _ in reqs), "user: the message was sent to the chat API")
            pg.goto(base); ready(pg); pg.click("#chatFab"); pg.wait_for_selector("#chatPanel.open")
            pg.wait_for_selector("#chatBody >> text=prices of houses in Gulshan", timeout=15000)
            check(True, "user: history is restored after a reload (continuity with Preferences consent)")
            pg.goto(base + "/#/plot/DEMO-KPT-1648"); pg.reload(); pg.wait_for_selector(".listing-actions", timeout=15000)
            pg.locator(".listing-actions [data-onclick=\"openChat()\"]").first.click(); pg.wait_for_selector("#chatPanel.open", timeout=5000)
            check(dialogs(pg) == 0 and panel_open(pg), "user: 'Ask the assistant' on a listing opens the Property Assistant")
            check(dialogs(pg) == 0, "user: no login dialog at any point")
            ctx.close()

            # ---------------- 3. EXPIRED SESSION during a conversation (real 401 from the server)
            ctx = b.new_context(viewport={"width": 390, "height": 900}); pg = ctx.new_page(); reqs = watch(pg)
            enter_as_user(pg, base); ready(pg); pg.click("#chatFab"); pg.wait_for_selector("#chatPanel.open")
            pg.fill(".assistant-input", "hello"); pg.keyboard.press("Enter"); pg.wait_for_selector(".chat-feedback", timeout=20000)
            n_before, posts_before = bubbles(pg), sum(1 for m, _ in reqs if m == "POST")
            ctx.clear_cookies(name="kpt_session")                         # the session expires between two messages
            pg.fill(".assistant-input", "show me plots under 3 crore in Malir"); pg.keyboard.press("Enter")
            pg.wait_for_selector(".login-prompt", timeout=8000); pg.wait_for_timeout(1500)
            text = body_text(pg)
            check(dialogs(pg) == 1, "expired: exactly one login dialog appears")
            check(not any(w in text for w in RAW) and "Could not reach" not in text, "expired: no raw error text in the transcript")
            check(bubbles(pg) == n_before + 1, f"expired: only the visitor's own message was added, no assistant/error bubble ({bubbles(pg)} vs {n_before}+1)")
            check(sum(1 for m, _ in reqs if m == "POST") == posts_before + 1, "expired: the rejected message was not retried")
            check(pg.locator(".chat-card").count() == 0, "expired: no cards from a false answer")
            ctx.close()

            # ---------------- 4. /chat/session rejected -> dialog, no raw text
            ctx = b.new_context(viewport={"width": 390, "height": 900}); pg = ctx.new_page(); reqs = watch(pg)
            enter_as_user(pg, base, dismiss=False); pg.wait_for_selector("#consentBanner"); pg.click("[data-choice=all]"); ready(pg)
            rej = lambda route: route.fulfill(status=401, content_type="application/json", body=json.dumps({"error": "Please log in to continue.", "code": "auth_required", "request_id": "t"}))  # noqa: E731
            pg.route(re.compile(r"/api/v1/chat/session"), rej)
            pg.click("#chatFab"); pg.wait_for_selector(".login-prompt", timeout=8000); pg.wait_for_timeout(800)
            check(dialogs(pg) == 1 and not any(w in body_text(pg) for w in RAW), "session: a rejected /chat/session shows one dialog and no raw error")
            n_sess = sum(1 for m, u in reqs if m == "GET" and "/chat/session" in u)
            pg.wait_for_timeout(1200)
            check(sum(1 for m, u in reqs if m == "GET" and "/chat/session" in u) == n_sess, "session: no retry loop")
            ctx.close()

            # ---------------- 5. /chat/feedback rejected -> dialog, buttons reset; unrelated 403s are NOT login problems
            ctx = b.new_context(viewport={"width": 390, "height": 900}); pg = ctx.new_page(); reqs = watch(pg)
            enter_as_user(pg, base); ready(pg); pg.click("#chatFab"); pg.wait_for_selector("#chatPanel.open")
            pg.fill(".assistant-input", "hello"); pg.keyboard.press("Enter"); pg.wait_for_selector(".chat-feedback", timeout=20000)
            pg.route(re.compile(r"/api/v1/chat/feedback"), rej)
            pg.click(".chat-feedback button >> nth=0"); pg.wait_for_selector(".login-prompt", timeout=8000)
            check(dialogs(pg) == 1 and not any(w in body_text(pg) for w in RAW), "feedback: a rejected /chat/feedback shows one dialog and no raw error")
            check(pg.locator(".chat-feedback button[aria-pressed=true]").count() == 0 and pg.locator(".chat-feedback button:disabled").count() == 0, "feedback: the thumbs are reset, nothing looks saved")
            close_dialog(pg)
            for code in ("forbidden", "csrf_failed"):
                pg.unroute(re.compile(r"/api/v1/chat$"))
                pg.route(re.compile(r"/api/v1/chat$"), lambda route, _req, c=code: route.fulfill(status=403, content_type="application/json", body=json.dumps({"error": f"denied {c}", "code": c, "request_id": "t"})))
                pg.fill(".assistant-input", f"test {code}"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1200)
                check(dialogs(pg) == 0, f"403 {code}: NOT treated as a login problem (no dialog)")
            ctx.close()

            # ---------------- 6. desktop width: the same guest guard
            ctx = b.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page(); reqs = watch(pg)
            enter_as_guest(pg, base); ready(pg); pg.click("#chatFab"); pg.wait_for_selector(".login-prompt", timeout=5000)
            box = pg.locator(".login-prompt").bounding_box()
            check(dialogs(pg) == 1 and box and 0 <= box["x"] and box["x"] + box["width"] <= 1280 and reqs == [], "desktop 1280px: guest dialog is inside the viewport, no chat request")
            ctx.close()
            b.close()
    finally:
        srv.terminate()
    if problems:
        print("PAGE PROBLEMS:", *problems[:5], sep="\n  "); failures.append("page problems")
    if failures:
        print("FAILED:", *failures, sep="\n  "); return 1
    print("g4_chatbot_test: OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
