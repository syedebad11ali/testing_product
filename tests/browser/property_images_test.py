"""Every property photo the UI requests is served (HTTP 200, image/*) and decodes. Run: python tests/browser/property_images_test.py"""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development", "RATE_LIMIT_PER_MIN": "1000"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, bad, seen = f"http://127.0.0.1:{port}", [], set()
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page()
            def on_response(r):
                if "Property%20Images" in r.url or "Property Images" in r.url:
                    seen.add(r.url)
                    if r.status != 200 or not r.headers.get("content-type", "").startswith("image/"): bad.append((r.url, r.status))
            pg.on("response", on_response)
            enter_as_guest(pg, base); pg.wait_for_selector("#app *", state="attached")
            if pg.locator("[data-choice=reject]").count(): pg.click("[data-choice=reject]")
            pg.wait_for_load_state("networkidle")
            for _ in range(8):                       # scroll so lazy-loaded cards request their photos
                pg.mouse.wheel(0, 900); pg.wait_for_timeout(250)
            pg.locator("[data-onclick^=\"nav('detail'\"]").first.dispatch_event("click"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(500)
            broken = pg.evaluate("() => [...document.images].filter(i => i.src && i.complete && i.naturalWidth === 0).map(i => i.src)")
            b.close()
        assert seen, "the UI requested no property photos at all"
        assert not bad, bad
        assert not broken, broken
        print(f"property_images_test OK ({len(seen)} photos served)"); return 0
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
