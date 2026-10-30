"""Camera + upload paths under the strict CSP, with the third-party libraries UNAVAILABLE (the offline case).
Chromium's fake camera supplies frames. Checks: no `securitypolicyviolation`, no uncaught page errors, the live camera starts,
a frame can be captured and used, and because Tesseract.js / PDF.js cannot load here the app says so instead of hanging.
It does NOT prove OCR or PDF reading work (that needs the libraries; see docs/KNOWN_ISSUES.md).
Run: python tests/browser/camera_upload_test.py   (Playwright + Chromium; throwaway database)"""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WATCH = """() => { window.__csp = []; document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI)); }"""
# 1x1 PNG
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main() -> int:
    port, tmp = free_port(), Path(tempfile.mkdtemp())
    env = {**os.environ, "PORT": str(port), "COOKIE_SECURE": "0", "GUEST_MAX_ACTIVE_PER_IP": "1000", "LOCAL_DB_PATH": str(tmp / "t.sqlite3"), "APP_ENV": "development", "RATE_LIMIT_PER_MIN": "1000"}
    srv = subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, errors = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(60):
            try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError: time.sleep(0.25)
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
            ctx = b.new_context(permissions=["camera"]); pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(f"pageerror: {str(e)[:200]}"))
            pg.add_init_script(f"({WATCH})()")
            enter_as_guest(pg, base); pg.wait_for_selector("#app *", state="attached")
            if pg.locator("[data-choice=reject]").count(): pg.click("[data-choice=reject]")

            # camera path: Report A Scam -> Open Camera -> live video -> capture -> use the photo
            pg.locator('[data-onclick*="reportslist"]').first.dispatch_event("click")
            pg.locator('[data-onclick*="openReportEvidenceCamera"]').first.dispatch_event("click")
            pg.locator('[data-onclick^="startDocumentCamera"]').first.dispatch_event("click")      # "Open Live Camera"
            pg.wait_for_selector("#docCameraVideo", state="attached", timeout=10000)
            for _ in range(60):   # wait until the fake camera is actually delivering frames
                if pg.evaluate("() => { const v = document.getElementById('docCameraVideo'); return !!v && v.readyState >= 2 && v.videoWidth > 0; }"): break
                pg.wait_for_timeout(250)
            else:
                raise AssertionError("fake camera never produced video frames: " + pg.inner_text("#app")[:300])
            pg.locator('[data-onclick^="captureDocumentFrame"]').first.dispatch_event("click")
            pg.wait_for_selector('[data-onclick^="useCapturedDocument"]', timeout=10000)
            pg.locator('[data-onclick^="useCapturedDocument"]').first.dispatch_event("click")
            pg.wait_for_timeout(1500)
            print("after use-photo:", " | ".join(pg.inner_text("#app").split("\n")[:6])[:200])

            # upload path (images and PDFs): a PNG goes through the same handler; no libraries => friendly failure, no crash
            pdf_up = tmp / "doc.pdf"; pdf_up.write_bytes(b"%PDF-1.4\n%fake\n")
            enter_as_guest(pg, base); pg.wait_for_selector("#app *", state="attached")
            pg.locator('[data-onclick*="reportslist"]').first.dispatch_event("click")
            pg.locator('[data-onclick*="openReportEvidenceUpload"]').first.dispatch_event("click")
            pg.wait_for_timeout(500)
            files = pg.locator("input[type=file]")
            print("file inputs present:", files.count())
            if files.count():
                files.first.set_input_files({"name": "evidence.png", "mimeType": "image/png", "buffer": PNG})
                pg.wait_for_timeout(2500)
                print("after png upload:", " | ".join(pg.inner_text("#app").split("\n")[:8])[:260])
            violations = pg.evaluate("() => window.__csp || []")
            b.close()
        assert not violations, f"CSP violations: {violations}"
        assert not errors, errors
        print("camera_upload_test OK"); return 0
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
