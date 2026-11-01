"""Browser test: featured properties carousel on the home page (Playwright). Run:  python tests/browser/featured_test.py
Covers next/previous/dots (wrap-around), automatic rotation, the Pause button, keyboard activation, reduced motion (no rotation),
strict-CSP cleanliness and no horizontal scroll on a phone. Takes about 40 s because it waits for real rotations."""
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
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "APP_ENV": "development", "RATE_LIMIT_PER_MIN": "1000"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, problems = f"http://127.0.0.1:{port}", []
    watch = lambda pg: (pg.on("console", lambda m: problems.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None),
                        pg.on("pageerror", lambda e: problems.append(f"pageerror on {pg.url}: {str(e.stack)[:300]}")))

    def title(pg):
        return pg.inner_text("#fcSlot .fc-title")

    def open_home(browser, **ctx_args):
        ctx = browser.new_context(**ctx_args); pg = ctx.new_page(); watch(pg)
        enter_as_guest(pg, base); pg.wait_for_selector("#fcRoot")
        pg.mouse.move(0, 0)   # keep the pointer off the carousel so hover does not pause rotation
        return ctx, pg

    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx, pg = open_home(b, viewport={"width": 1100, "height": 900})
            assert pg.locator(".fc-dot").count() == 4, "expected 4 dots"
            assert pg.locator(".fc-dot.active").count() == 1 and pg.get_attribute(".fc-dot.active", "aria-current") == "true"
            assert pg.get_attribute("#fcRoot", "aria-roledescription") == "carousel"
            first = title(pg)
            bg = pg.eval_on_selector("#fcSlot .fc-media", "e => getComputedStyle(e).backgroundImage")
            assert "assets/Property" in bg, f"slide image missing under strict CSP: {bg[:80]}"

            # next / previous / wrap-around / dots
            pg.click("[aria-label='Next featured property']"); pg.wait_for_selector(f"#fcSlot .fc-title:not(:text-is('{first}'))"); second = title(pg)
            assert second != first and "2 / 4" in pg.inner_text("#fcDots")
            pg.click("[aria-label='Previous featured property']"); pg.wait_for_selector(f"#fcSlot .fc-title:text-is('{first}')")
            pg.click("[aria-label='Previous featured property']"); pg.wait_for_selector(f"#fcSlot .fc-title:not(:text-is('{first}'))")
            assert "4 / 4" in pg.inner_text("#fcDots"), "previous from the first slide must wrap to the last"
            pg.click(".fc-dot >> nth=0"); pg.wait_for_selector(f"#fcSlot .fc-title:text-is('{first}')")
            assert pg.get_attribute("#fcSlot", "aria-live") == "polite", "visitor-initiated change should be announced"

            # automatic rotation, then Pause stops it and Play resumes it
            pg.mouse.move(0, 0); pg.wait_for_timeout(500)
            pg.wait_for_selector(f"#fcSlot .fc-title:not(:text-is('{first}'))", timeout=12000)
            pg.click("#fcPause"); assert pg.get_attribute("#fcPause", "aria-pressed") == "true" and "Play" in pg.inner_text("#fcPause")
            held = title(pg); pg.mouse.move(0, 0); pg.wait_for_timeout(7500)
            assert title(pg) == held, "rotation must stay stopped while paused"
            pg.click("#fcPause"); assert pg.get_attribute("#fcPause", "aria-pressed") == "false"
            pg.mouse.move(0, 0); pg.wait_for_selector(f"#fcSlot .fc-title:not(:text-is('{held}'))", timeout=12000)

            # keyboard: the call-to-action is a real button; Enter opens the property
            pg.focus("#fcSlot .fc-cta"); name = title(pg); pg.keyboard.press("Enter")
            pg.wait_for_selector("#fcRoot", state="detached", timeout=8000)
            assert name in pg.inner_text("#app"), "detail page for the featured property did not open"
            ctx.close()

            # reduced motion: no pause button (nothing rotates) and no automatic change
            ctx, pg = open_home(b, viewport={"width": 1100, "height": 900}, reduced_motion="reduce")
            assert pg.locator("#fcPause").count() == 0, "pause button should not appear when rotation never runs"
            still = title(pg); pg.wait_for_timeout(7500); assert title(pg) == still, "must not rotate under prefers-reduced-motion"
            pg.click("[aria-label='Next featured property']"); pg.wait_for_selector(f"#fcSlot .fc-title:not(:text-is('{still}'))")
            ctx.close()

            # phone: no sideways scroll
            ctx, pg = open_home(b, viewport={"width": 360, "height": 740})
            assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "horizontal scroll on a phone"
            ctx.close(); b.close()
    finally:
        srv.terminate()
    for x in problems: print("PROBLEM:", x)
    print("featured:", "FAIL" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
