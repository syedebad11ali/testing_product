"""Basic accessibility regression checks (NOT Lighthouse and NOT a WCAG audit): on every page, <html lang>, a non-empty <title>,
exactly one <h1>, an accessible name for every visible form control / button / link / dialog, and alt text on images.
Run: python tests/browser/a11y_basics_test.py   (Playwright + Chromium; throwaway database)."""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ADMIN_PW, USER_PW = "local-demo-admin-pass", "correct-horse-battery"
CHECK = """() => {
  const vis = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const name = (e) => {
    if (e.getAttribute('aria-label')?.trim()) return true;
    const lb = e.getAttribute('aria-labelledby');
    if (lb && lb.split(/\\s+/).some((id) => document.getElementById(id)?.textContent.trim())) return true;
    if (e.id && document.querySelector(`label[for="${CSS.escape(e.id)}"]`)?.textContent.trim()) return true;
    if (e.closest('label')?.textContent.trim()) return true;
    if (e.title?.trim()) return true;
    return false;
  };
  const out = [];
  if (!document.documentElement.lang) out.push('missing <html lang>');
  if (!document.title.trim()) out.push('empty <title>');
  const h1 = [...document.querySelectorAll('h1, [role=heading][aria-level="1"]')].filter(vis).length;
  if (h1 !== 1) out.push(`visible h1 count is ${h1}`);
  for (const e of document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')) {
    if (vis(e) && !name(e) && !e.placeholder) out.push(`unnamed control <${e.tagName.toLowerCase()} id=${e.id} type=${e.type}>`);
  }
  for (const e of document.querySelectorAll('button, [role=button]')) {
    if (vis(e) && !e.textContent.trim() && !name(e)) out.push(`unnamed button id=${e.id} class=${e.className}`);
  }
  for (const e of document.querySelectorAll('a[href]')) {
    if (vis(e) && !e.textContent.trim() && !name(e) && !e.querySelector('img[alt]:not([alt=""])')) out.push(`unnamed link ${e.getAttribute('href')}`);
  }
  for (const e of document.querySelectorAll('img')) if (!e.hasAttribute('alt')) out.push(`img without alt: ${(e.getAttribute('src') || '').slice(0, 60)}`);
  for (const e of document.querySelectorAll('dialog')) if (!e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby')) out.push(`dialog without a name id=${e.id}`);
  return out;
}"""


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
    base, bad = f"http://127.0.0.1:{port}", {}
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch()

            def audit(ctx, path, ready):
                pg = ctx.new_page(); pg.goto(base + path); pg.wait_for_selector(ready, state="attached"); pg.wait_for_load_state("networkidle")
                found = pg.evaluate(CHECK)
                print(("PASS " if not found else "FAIL ") + path, found if found else "")
                if found: bad[path] = found
                pg.close()

            anon = b.new_context()
            guest = b.new_context(); gp = guest.new_page(); enter_as_guest(gp, base); gp.close()   # "/" and "/listings" need a session since T4
            for path, ready in (("/login", "form"), ("/signup", "form"), ("/privacy", "h1"), ("/", "body"), ("/listings", "#browse"), ("/nice-try", "h1")):
                audit(guest if path in ("/", "/listings") else anon, path, ready)
            def audit_view(label, steps, start="/"):
                """Single-page-app views have no URL of their own: open the start page and click through to the view."""
                pg = guest.new_page(); pg.goto(base + start); pg.wait_for_selector("#app *", state="attached"); pg.wait_for_load_state("networkidle")
                for sel in steps:
                    pg.locator(sel).first.dispatch_event("click"); pg.wait_for_load_state("networkidle")
                found = pg.evaluate(CHECK)
                print(("PASS " if not found else "FAIL ") + label, found if found else "")
                if found: bad[label] = found
                pg.close()

            audit_view("view: property detail", ["[data-onclick^=\"nav('detail'\"]"])
            audit_view("view: document verification", ["[data-onclick^=\"nav('detail'\"]", "[data-onclick^=\"nav('verify'\"]"])
            audit_view("view: dataset listing", [], start="/#/plot/DEMO-KPT-8103")
            audit_view("view: owner verification", ["[data-onclick*=\"ownerverify\"]"], start="/#/plot/DEMO-KPT-8103")
            user = b.new_context(); up = user.new_page(); up.goto(base + "/login")
            api(up, "/api/v1/auth/signup", {"name": "Ayesha A11y", "email": "ayesha@example.com", "password": USER_PW})
            for path, ready in (("/messages", "h1"), ("/listings", "#create-form:not([hidden])")):
                audit(user, path, ready)
            adm = b.new_context(); ap = adm.new_page(); ap.goto(base + "/login")
            api(ap, "/api/v1/auth/login", {"identifier": "admin_001", "password": ADMIN_PW})
            audit(adm, "/admin", "#users tbody tr")
            b.close()
    finally:
        srv.terminate()
    if bad:
        print("FAILED pages:", list(bad)); return 1
    print("a11y basics OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
