"""Browser smoke test (Playwright). Run:  python tests/browser/smoke.py   (needs `playwright install chromium`)

Starts the app on a free port and clicks through the delegated-handler UI. Fails on any CSP
violation, unknown action, or uncaught page error. Not part of `npm run test:all` because it
needs a browser; run it before releases."""
import os, socket, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port = free_port()
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 900})
            pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and ("Content Security" in m.text or "[kpt]" in m.text or "Refused" in m.text) else None)
            pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
            enter_as_guest(pg, base); pg.wait_for_selector("[data-onclick^=\"nav('detail'\"]", timeout=8000)
            dismiss_consent(pg)  # cookie banner (bottom of the screen) would cover the controls
            pg.click("#themeToggle"); theme = pg.evaluate("document.documentElement.getAttribute('data-theme')")
            pg.click(".topnav-menu"); assert pg.is_visible(".drawer-item"), "drawer did not open"
            pg.click("#overlayBg", position={"x": 385, "y": 800})
            pg.click("#chatFab"); assert pg.is_visible("#chatPanel, .chat-panel, [id^=chat]"), "chat did not open"
            pg.keyboard.press("Escape")
            pg.goto(base); pg.wait_for_selector("[data-onclick^=\"nav('detail'\"]")
            pg.locator("[data-onclick^=\"nav('detail'\"]").first.click()
            pg.wait_for_timeout(300); assert "Back" in pg.content() or pg.locator("[data-onclick=\"nav('home')\"]").count() > 0, "detail view missing"
            # chatbot: plot cards, deep link, refresh, feedback, start over
            pg.goto(base); pg.click("#chatFab")
            pg.fill(".assistant-input", "show me plots under 3 crore in Malir"); pg.keyboard.press("Enter")
            pg.wait_for_selector(".chat-card", timeout=15000)
            assert pg.locator(".chat-card").count() == 3, "expected 3 plot cards"
            assert pg.locator(".chat-chip").count() >= 2, "expected quick-reply chips"
            href = pg.locator(".chat-card").first.get_attribute("href"); assert href.startswith("/#/plot/DEMO-KPT-"), href
            pg.click(".chat-feedback button >> nth=0"); assert pg.locator(".chat-feedback button[aria-pressed=true]").count() == 1
            pg.locator(".chat-card").first.click(); pg.wait_for_selector(".listing h1", timeout=8000)
            assert "Plot in Malir" in pg.inner_text(".listing h1"), "listing page did not open"
            pg.reload(); pg.wait_for_selector(".listing h1", timeout=8000)  # deep link survives refresh
            pg.goto(base + "/#/plot/NOPE-1234"); pg.wait_for_selector(".listing", timeout=8000); assert "Listing not found" in pg.content()
            pg.goto(base); pg.click("#chatFab"); pg.click(".assistant-reset"); assert pg.locator(".chat-card").count() == 0
            pg.goto(f"{base}/nice-try"); assert "ap Apni na chalao apna abu ebad se pouch lu agar password nahi pata" in pg.content()
            b.close()
        print("theme after toggle:", theme)
    finally:
        srv.terminate()
    for x in problems: print("PROBLEM:", x)
    print("smoke:", "FAIL" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
