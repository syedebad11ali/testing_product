"""G5.4a: account-owned favorites and home filters, end to end in ONE browser (Playwright, real backend, throwaway database, real sign-up / log-in /
log-out and real /api/v1/auth/prefs traffic; nothing about the behaviour under test is mocked).

  1 guest changes the home filters         -> they work on screen, are not stored (no preferences request, no cookie, gone after reload)
  2 guest tries to save a property         -> the login dialog appears, nothing is saved
  3 account A saves a property + sets filters
  4 reload                                 -> A's property and filters are restored (and are on the server)
  5 log out, then account B in the SAME browser
  6                                        -> B sees none of A's favorites or filters (screen, API, cookie)
  7 B saves a different property and other filters
  8 log back in as A (real login form)     -> A's original data is intact, B's data is not in it

Run:  python tests/browser/g5_account_data_test.py"""
import json, os, socket, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import USER_PASSWORD, dismiss_consent, enter_as_guest, enter_as_user  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development",
           "LOGIN_RATE_LIMIT_PER_MIN": "200", "RATE_LIMIT_PER_MIN": "1000"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, failures, problems, prefs_calls = f"http://127.0.0.1:{port}", [], [], []

    def check(ok, msg):
        print(("PASS " if ok else "FAIL ") + msg)
        if not ok: failures.append(msg)

    def watch(pg):
        pg.on("request", lambda r: prefs_calls.append((r.method, r.url.replace(base, ""))) if "/auth/prefs" in r.url else None)
        pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

    def api_prefs(pg):
        """The server's copy for the signed-in session (real request, same cookies as the page)."""
        return pg.evaluate("() => fetch('/api/v1/auth/prefs').then(async r => ({status: r.status, body: await r.json().catch(() => ({}))}))")

    def wait_server(pg, pred, what, timeout=12):
        end, last = time.time() + timeout, None
        while time.time() < end:
            last = api_prefs(pg)
            if last["status"] == 200 and pred(last["body"].get("prefs") or {}): return last["body"].get("prefs")
            time.sleep(0.25)
        check(False, f"timed out waiting for the server to hold: {what} (last: {last})"); return {}

    def home(pg):
        pg.goto(base + "/"); pg.wait_for_selector(".pcard .fav"); dismiss_consent(pg)

    def screen(pg):
        """What the visitor sees: the chosen area chip, type, sort and which cards are hearted."""
        return pg.evaluate("""() => ({
            area: (document.querySelector('.area-chip.active') || {}).textContent || '',
            title: document.getElementById('listTitle').textContent,
            type: document.querySelector('select[aria-label="Filter by property type"]').value,
            sort: document.querySelector('select[aria-label="Sort properties"]').value,
            saved: [...document.querySelectorAll('.pcard .fav[aria-pressed="true"]')].map(b => b.dataset.favoriteId) })""")

    def first_ids(pg, n=2):
        return pg.evaluate("(n) => [...document.querySelectorAll('.pcard .fav')].slice(0, n).map(b => b.dataset.favoriteId)", n)

    def choose(pg, area_index, type_index, sort_value):
        """Drive the real controls: an area chip, the type <select> and the sort <select>."""
        chips = [c for c in pg.locator(".area-chip").all_inner_texts() if c.strip() != "Clear"]
        area = chips[area_index]
        pg.click(f".area-chip:text-is('{area}')")
        types = pg.eval_on_selector('select[aria-label="Filter by property type"]', "s => [...s.options].map(o => o.value).filter(Boolean)")
        pg.select_option('select[aria-label="Filter by property type"]', types[type_index])
        pg.select_option('select[aria-label="Sort properties"]', sort_value)
        return area, types[type_index], sort_value

    def log_out(pg):
        pg.locator(".auth-logout:visible").first.click(); pg.wait_for_url(base + "/login*", timeout=10000)

    def log_in(pg, email):
        pg.goto(base + "/login"); pg.wait_for_selector("#form-login:not([hidden])")
        pg.fill("#login-id", email); pg.fill("#login-pw", USER_PASSWORD); pg.click("#form-login button[type=submit]")
        pg.wait_for_url(base + "/", timeout=15000); dismiss_consent(pg, wait_ms=2000); pg.wait_for_selector("#grid")

    def settle(pg):
        pg.wait_for_timeout(1500)   # the account load after /auth/me re-renders the page once

    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1200, "height": 900}); pg = ctx.new_page(); watch(pg)

            # ---------------- 1. guest changes filters
            enter_as_guest(pg, base); pg.wait_for_selector(".pcard .fav"); settle(pg)
            default = screen(pg)
            g_area, g_type, g_sort = choose(pg, 1, 1, "low"); pg.wait_for_timeout(800)
            s = screen(pg)
            check(s["area"] == g_area and s["type"] == g_type and s["sort"] == "low" and g_area in s["title"], f"1 guest: the filters work on screen ({g_area} / {g_type} / low)")
            check(prefs_calls == [], f"1 guest: no preferences request was made at all ({prefs_calls})")
            ck = {c["name"]: c["value"] for c in ctx.cookies()}.get("kpt_prefs", "")
            check(g_area.lower() not in ck.lower() and g_type.lower() not in ck.lower() and "price_asc" not in ck, "1 guest: nothing about the filters is in the shared preference cookie")
            pg.reload(); pg.wait_for_selector(".pcard .fav"); settle(pg)
            s = screen(pg)
            check(s["area"] == default["area"] and s["type"] == default["type"] == "" and s["sort"] == default["sort"] and s["title"] == "Property Listings", "1 guest: after a reload the filters are back to the defaults (not persisted)")
            check(prefs_calls == [], "1 guest: still no preferences request after the reload")

            # ---------------- 2. guest tries to save
            pg.goto(base + "/"); pg.wait_for_selector(".pcard .fav"); settle(pg)
            pid_x, pid_y = first_ids(pg)
            pg.click(f'.pcard .fav[data-favorite-id="{pid_x}"]'); pg.wait_for_selector(".login-prompt", timeout=5000)
            check(pg.locator(".login-prompt").count() == 1 and screen(pg)["saved"] == [], "2 guest: saving a property shows the login dialog and the heart stays off")
            check(prefs_calls == [], "2 guest: no preferences request was sent for the refused save")
            pg.click(".login-prompt-secondary"); pg.wait_for_selector(".login-prompt", state="detached", timeout=3000)

            # ---------------- 3. account A saves a property and changes filters
            email_a = enter_as_user(pg, base, name="Account Alpha"); pg.wait_for_selector(".pcard .fav"); settle(pg)
            a_ids = first_ids(pg); pid_a = a_ids[0]
            check(screen(pg)["saved"] == [] and screen(pg)["title"] == "Property Listings", "3 A: a brand-new account starts with no favorites and no filters")
            pg.click(f'.pcard .fav[data-favorite-id="{pid_a}"]'); pg.wait_for_selector(f'.pcard .fav[data-favorite-id="{pid_a}"][aria-pressed="true"]', timeout=8000)
            a_area, a_type, a_sort = choose(pg, 1, 1, "low")
            sa = wait_server(pg, lambda d: pid_a.lower() in [x.lower() for x in d.get("saved", [])] and d.get("area") == a_area.lower() and d.get("ptype") == a_type.lower() and d.get("sort") == "price_asc",
                             f"A's favorite {pid_a} and filters {a_area}/{a_type}/price_asc")
            check(bool(sa), "3 A: the favorite and the filters are stored on A's account (server copy)")

            # ---------------- 4. reload: A's data restored
            pg.reload(); pg.wait_for_selector("#grid"); settle(pg)
            s = screen(pg)
            check(s["area"] == a_area and s["type"] == a_type and s["sort"] == "low" and a_area in s["title"], f"4 A: after a reload the filters are restored ({s['area']} / {s['type']} / {s['sort']})")
            pg.select_option('select[aria-label="Filter by property type"]', ""); pg.click(".area-chip:text-is('Clear')")   # show every card again, only to inspect the hearts
            check(pid_a in screen(pg)["saved"], f"4 A: after a reload the saved property {pid_a} is still hearted")
            # the clearing above is part of the same test data: put A's filters back so step 8 compares against what step 3 stored
            pg.click(f".area-chip:text-is('{a_area}')"); pg.select_option('select[aria-label="Filter by property type"]', a_type); pg.select_option('select[aria-label="Sort properties"]', "low")
            wait_server(pg, lambda d: d.get("area") == a_area.lower() and d.get("ptype") == a_type.lower() and d.get("sort") == "price_asc", "A's filters stored again")

            # ---------------- 5. log out, then B in the same browser
            log_out(pg)
            ck = {c["name"]: c["value"] for c in ctx.cookies()}
            check(not any(c["name"] in ("session",) for c in ctx.cookies()), "5 logout: the session cookie is gone")
            check(a_area.lower() not in ck.get("kpt_prefs", "").lower() and "price_asc" not in ck.get("kpt_prefs", ""), "5 logout: A's filters did not leak into the shared preference cookie")
            email_b = enter_as_user(pg, base, name="Account Bravo"); pg.wait_for_selector(".pcard .fav"); settle(pg)

            # ---------------- 6. B sees nothing of A
            s = screen(pg)
            check(s["saved"] == [] and pid_a not in s["saved"], "6 B: no property is hearted (A's favorite is not shown)")
            check(s["area"] == "" and s["type"] == "" and s["title"] == "Property Listings" and s["sort"] == default["sort"], f"6 B: filters are the defaults, not A's ({s['area'] or '-'} / {s['type'] or '-'} / {s['sort']})")
            sb = api_prefs(pg)
            pb = sb["body"].get("prefs") or {}
            check(sb["status"] == 200 and not pb.get("saved") and not pb.get("area") and not pb.get("ptype") and not pb.get("sort"), f"6 B: the server copy for B holds none of A's data ({json.dumps(pb)})")
            pg.reload(); pg.wait_for_selector(".pcard .fav"); settle(pg)
            check(screen(pg)["saved"] == [] and screen(pg)["title"] == "Property Listings", "6 B: still nothing of A after a reload")

            # ---------------- 7. B saves different data
            b_ids = first_ids(pg, 3); pid_b = next(i for i in b_ids if i != pid_a)
            pg.click(f'.pcard .fav[data-favorite-id="{pid_b}"]'); pg.wait_for_selector(f'.pcard .fav[data-favorite-id="{pid_b}"][aria-pressed="true"]', timeout=8000)
            b_area, b_type, b_sort = choose(pg, 2, 2, "high")
            check((b_area, b_type) != (a_area, a_type), f"7 B: B picks different filters from A ({b_area}/{b_type}/high vs {a_area}/{a_type}/low)")
            wait_server(pg, lambda d: [x.lower() for x in d.get("saved", [])] == [pid_b.lower()] and d.get("area") == b_area.lower() and d.get("ptype") == b_type.lower() and d.get("sort") == "price_desc",
                        f"B's favorite {pid_b} and filters {b_area}/{b_type}/price_desc")
            pb = (api_prefs(pg)["body"].get("prefs") or {})
            check([x.lower() for x in pb.get("saved", [])] == [pid_b.lower()] and pid_a.lower() not in [x.lower() for x in pb.get("saved", [])], f"7 B: B's account holds only B's property ({pb.get('saved')})")

            # ---------------- 8. back to A
            log_out(pg); log_in(pg, email_a); settle(pg)
            s = screen(pg)
            check(s["area"] == a_area and s["type"] == a_type and s["sort"] == "low" and a_area in s["title"], f"8 A: logging back in restores A's original filters ({s['area']} / {s['type']} / {s['sort']})")
            pa = api_prefs(pg)["body"].get("prefs") or {}
            check([x.lower() for x in pa.get("saved", [])] == [pid_a.lower()] and pa.get("area") == a_area.lower() and pa.get("ptype") == a_type.lower() and pa.get("sort") == "price_asc",
                  f"8 A: the server copy is A's original data ({json.dumps({k: pa.get(k) for k in ('saved', 'area', 'ptype', 'sort')})})")
            # (only now clear the filters, purely to see every card and its heart)
            pg.select_option('select[aria-label="Filter by property type"]', ""); pg.click(".area-chip:text-is('Clear')")
            s = screen(pg)
            check(pid_a in s["saved"] and pid_b not in s["saved"] and len(s["saved"]) == 1, f"8 A: A's favorite is intact and B's is not there (hearted: {s['saved']})")
            ck = {c["name"]: c["value"] for c in ctx.cookies()}.get("kpt_prefs", "")
            check(not any(v.lower() in ck.lower() for v in (a_area, b_area, a_type, b_type) if v), "8: neither account's filters were ever written to the shared preference cookie")
            b.close()
    finally:
        srv.terminate()
    if problems:
        print("PAGE PROBLEMS:", *problems[:5], sep="\n  "); failures.append("page problems")
    if failures:
        print("FAILED:", *failures, sep="\n  "); return 1
    print("g5_account_data_test: OK"); return 0


if __name__ == "__main__":
    sys.exit(main())
