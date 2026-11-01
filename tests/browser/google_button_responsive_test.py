"""Login page: the Google button fits the form on every screen width (320, 360, 768, 1280 px).

Regression for the blank/clipped Google pill on phones: Google's button is an iframe of an exact pixel width and the page used to
ask for a fixed 400 px, which overflowed a 320-360 px form. No network and no real Google: the Google script is replaced in the
browser by a stub that behaves like it (an element of exactly the requested width, clamped to Google's 200-400 px limits).
Covers: configured Google (stub) on the login and sign-up forms, redrawing after a resize and after the hidden sign-up form is
shown, no horizontal page scroll; and the placeholder button when Google is not configured.
Run: python tests/browser/google_button_responsive_test.py   (optional KPT_SHOT_DIR=<dir> saves screenshots of the form)"""
import os, socket, subprocess, sys, tempfile, time
from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
WIDTHS = (320, 360, 768, 1280)
STUB = """window.google={accounts:{id:{initialize:function(){},renderButton:function(el,o){var w=Math.max(200,Math.min(400,o.width||200));
var f=document.createElement('div');f.setAttribute('data-gsi-stub','');f.style.cssText='width:'+w+'px;height:44px;background:#fff;border:1px solid #dadce0;border-radius:999px;display:flex;align-items:center;justify-content:center;color:#1f1f1f;font:14px sans-serif;flex:none';
f.textContent='Continue with Google';el.appendChild(f);}}}};"""
MEASURE = """([form, sel]) => {
  const f = document.querySelector(form).getBoundingClientRect(), e = document.querySelector(sel).getBoundingClientRect();
  return {fl: f.left, fr: f.right, el: e.left, er: e.right, w: e.width, h: e.height, scrollW: document.documentElement.scrollWidth, inner: innerWidth};
}"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


@contextmanager
def server(extra):
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development", **extra}
    env.pop("GOOGLE_CLIENT_ID", None) if "GOOGLE_CLIENT_ID" not in extra else None
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.terminate()


def main() -> int:
    failures, shots = [], os.environ.get("KPT_SHOT_DIR")

    def check(ok, msg):
        print(("PASS " if ok else "FAIL ") + msg)
        if not ok: failures.append(msg)

    def inside(m):   # the control lies fully inside its form (0.5 px tolerance for sub-pixel layout) and the page does not scroll sideways
        return m["el"] >= m["fl"] - 0.5 and m["er"] <= m["fr"] + 0.5 and m["scrollW"] <= m["inner"]

    with sync_playwright() as p:
        b = p.chromium.launch()
        # ---- Google configured: the (stubbed) official button
        with server({"GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com"}) as base:
            for w in WIDTHS:
                ctx = b.new_context(viewport={"width": w, "height": 900}); pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
                pg.route("https://accounts.google.com/gsi/client", lambda r: r.fulfill(status=200, content_type="application/javascript", body=STUB))
                pg.goto(base + "/login"); pg.wait_for_selector("#form-login .gbox [data-gsi-stub]", timeout=10000)
                m = pg.evaluate(MEASURE, ["#form-login", "#form-login [data-gsi-stub]"])
                want = min(400, max(200, int(m["fr"] - m["fl"])))
                check(inside(m), f"{w}px login: Google button inside the form, no sideways scroll (form {m['fl']:.0f}-{m['fr']:.0f}, button {m['el']:.0f}-{m['er']:.0f})")
                check(abs(m["w"] - want) <= 1.5, f"{w}px login: button width {m['w']:.0f}px = container width capped to 200-400 (expected {want})")
                check(pg.locator("#form-login button[data-google]").is_hidden(), f"{w}px login: the placeholder is replaced, not shown twice")
                check("Continue with Google" in pg.inner_text("#form-login .gbox"), f"{w}px login: the button is not blank")
                # the sign-up form starts hidden: it must be drawn at the right width once it is shown
                pg.click("#form-login [data-switch=signup]"); pg.wait_for_selector("#form-signup .gbox [data-gsi-stub]", timeout=5000)
                s = pg.evaluate(MEASURE, ["#form-signup", "#form-signup [data-gsi-stub]"])
                check(inside(s) and abs(s["w"] - min(400, max(200, int(s["fr"] - s["fl"])))) <= 1.5, f"{w}px sign-up: drawn at the real width after being shown ({s['w']:.0f}px)")
                if shots and w in (320, 360, 1280):
                    pg.click("#form-signup [data-switch=login]"); pg.wait_for_selector("#form-login:not([hidden])")
                    Path(shots).mkdir(parents=True, exist_ok=True); pg.locator("#form-login").screenshot(path=str(Path(shots) / f"login_google_form_{w}.png"))
                check(not errs, f"{w}px: no page errors {errs}")
                ctx.close()
            # a resize or rotation redraws the button at the new width
            ctx = b.new_context(viewport={"width": 1280, "height": 900}); pg = ctx.new_page()
            pg.route("https://accounts.google.com/gsi/client", lambda r: r.fulfill(status=200, content_type="application/javascript", body=STUB))
            pg.goto(base + "/login"); pg.wait_for_selector("#form-login .gbox [data-gsi-stub]", timeout=10000)
            wide = pg.evaluate(MEASURE, ["#form-login", "#form-login [data-gsi-stub]"])["w"]
            pg.set_viewport_size({"width": 320, "height": 700}); pg.wait_for_timeout(500)
            m = pg.evaluate(MEASURE, ["#form-login", "#form-login [data-gsi-stub]"])
            check(wide == 400 and inside(m) and m["w"] < 400, f"resize 1280 -> 320: redrawn from {wide:.0f}px to {m['w']:.0f}px and still inside the form")
            check(pg.locator("#form-login [data-gsi-stub]").count() == 1, "resize: exactly one Google button (no duplicates)")
            ctx.close()
        # ---- Google not configured: the placeholder button is shown and fits
        with server({}) as base:
            for w in WIDTHS:
                ctx = b.new_context(viewport={"width": w, "height": 900}); pg = ctx.new_page()
                pg.goto(base + "/login"); pg.wait_for_selector("#form-login button[data-google]")
                m = pg.evaluate(MEASURE, ["#form-login", "#form-login button[data-google]"])
                check(inside(m) and m["h"] >= 40, f"{w}px not configured: placeholder inside the form, tall enough to tap ({m['h']:.0f}px)")
                check("Google" in pg.inner_text("#form-login button[data-google]"), f"{w}px not configured: placeholder shows its label")
                ctx.close()
            ctx = b.new_context(viewport={"width": 360, "height": 900}); pg = ctx.new_page()
            pg.goto(base + "/login"); pg.wait_for_selector("#form-login button[data-google]")
            pg.click("#form-login button[data-google]")
            check("not configured" in pg.inner_text("#form-login [data-banner]").lower(), "not configured: clicking explains it instead of doing nothing")
            ctx.close()
        b.close()
    if failures:
        print("FAILED:", *failures, sep="\n  "); return 1
    print("google_button_responsive_test: OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
