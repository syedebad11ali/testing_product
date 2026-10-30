"""Browser test: Home filters/sort are remembered only with Preferences consent. Run: python tests/browser/prefs_test.py"""
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
    base, problems = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()
            for choice in ("all", "reject"):
                ctx = b.new_context(); pg = ctx.new_page()
                pg.on("pageerror", lambda e: problems.append(str(e)[:200]))
                enter_as_guest(pg, base, dismiss=False); pg.wait_for_selector("#consentBanner"); pg.click(f"[data-choice={choice}]")  # T5a: banner after guest entry
                pg.select_option(".filters-row select >> nth=0", "House"); pg.select_option(".filters-row select >> nth=1", "high")
                pg.reload(); pg.wait_for_selector(".filters-row")
                type_val = pg.locator(".filters-row select >> nth=0").input_value(); sort_val = pg.locator(".filters-row select >> nth=1").input_value()
                if choice == "all":
                    assert (type_val, sort_val) == ("House", "high"), (type_val, sort_val)
                    prefs = {c["name"]: c["value"] for c in ctx.cookies()}.get("kpt_prefs", "")
                    assert "price_desc" in prefs and "house" in prefs, prefs
                else:
                    assert (type_val, sort_val) == ("", "newest"), "choice leaked past a rejected Preferences consent"
                    assert "kpt_prefs" not in {c["name"] for c in ctx.cookies()}
                ctx.close()
            # tampered cookie is ignored, page still renders
            ctx = b.new_context(); pg = ctx.new_page(); enter_as_guest(pg, base, dismiss=False); pg.wait_for_selector("#consentBanner"); pg.click("[data-choice=all]")
            ctx.add_cookies([{"name": "kpt_prefs", "value": "%7B%22ptype%22%3A%22%3Cscript%3E%22%2C%22sort%22%3A%22x%22%7D", "url": base}])
            pg.reload(); pg.wait_for_selector(".filters-row")
            assert pg.locator(".filters-row select >> nth=0").input_value() == ""
            b.close()
        assert not problems, problems
        print("prefs_test OK"); return 0
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
