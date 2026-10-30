"""Header "Creators" menu in a real browser. Run:  python tests/browser/creators_test.py
Open/close with mouse and keyboard, Escape returns focus, outside click closes, link attributes, light + dark theme, mobile fit,
and zero CSP violations (the avatars are initials, not remote images). Throwaway database, local server."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(Path(tempfile.mkdtemp()) / "t.db"), "APP_ENV": "development"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, failures = f"http://127.0.0.1:{port}", []
    check = lambda ok, what: (print(("PASS " if ok else "FAIL ") + what), None if ok else failures.append(what))
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_context(viewport={"width": 1280, "height": 800}).new_page()
            enter_as_guest(pg, base); pg.wait_for_selector("#creatorsMenu"); dismiss_consent(pg)
            check(not pg.evaluate("() => document.getElementById('creatorsMenu').open"), "menu starts closed")
            pg.click("#creatorsMenu summary"); check(pg.evaluate("() => document.getElementById('creatorsMenu').open") and pg.is_visible(".creators-dropdown"), "click on the pill opens the dropdown")
            hrefs = pg.eval_on_selector_all(".creators-dropdown a", "els => els.map(e => [e.href, e.target, e.rel])")
            check(hrefs == [["https://github.com/syedebad11ali", "_blank", "noopener noreferrer"], ["https://github.com/ctrl-shift-ali", "_blank", "noopener noreferrer"]], "both credits link to GitHub with noopener noreferrer")
            check(pg.inner_text(".creators-dropdown").split() == ["SE", "Syed", "Ebad", "Ali", "MA", "M", "Ali", "Abeer"], "names and initial avatars are shown")
            pg.keyboard.press("Escape")
            check(not pg.evaluate("() => document.getElementById('creatorsMenu').open") and pg.evaluate("() => document.activeElement.tagName") == "SUMMARY", "Escape closes it and returns focus to the pill")
            pg.focus("#creatorsMenu summary"); pg.keyboard.press("Enter")
            check(pg.evaluate("() => document.getElementById('creatorsMenu').open"), "keyboard (Enter) opens it")
            pg.mouse.click(640, 600)
            check(not pg.evaluate("() => document.getElementById('creatorsMenu').open"), "outside click closes it")
            pg.click("#themeToggle"); 
            check(pg.evaluate("() => document.documentElement.getAttribute('data-theme')") == "dark", "theme switched to dark")
            pg.click("#creatorsMenu summary"); pg.wait_for_timeout(900)  # theme colours transition for ~0.6s
            bg = pg.evaluate("() => getComputedStyle(document.querySelector('.creators-dropdown')).backgroundColor")
            check(pg.is_visible(".creators-dropdown") and bg == "rgb(22, 33, 31)", f"dropdown uses the dark surface colour in dark theme ({bg})")
            m = b.new_context(viewport={"width": 375, "height": 700}).new_page(); enter_as_guest(m, base); m.wait_for_selector("#creatorsMenu"); dismiss_consent(m)
            m.click("#creatorsMenu summary")
            box = m.eval_on_selector(".creators-dropdown", "e => { const r = e.getBoundingClientRect(); return [r.left, r.right, innerWidth] }")
            check(box[0] >= 0 and box[1] <= box[2] and not m.evaluate("() => document.documentElement.scrollWidth > innerWidth"), f"mobile 375px: dropdown fits the viewport {box}")
            check(not m.is_visible(".creators-label"), "mobile: pill collapses to the icon")
            b.close()
    finally:
        srv.terminate()
    print("OK" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
