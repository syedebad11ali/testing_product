"""Camera + upload paths under the strict CSP, with the third-party libraries UNAVAILABLE (the offline case).
Document / evidence views are account-only (G3b2a, G6.1a), so the test runs as a REGISTERED user (`enter_as_user`).
Checks:
  * a guest who clicks Report A Scam gets the "Login required" dialog and no evidence button (nothing was weakened);
  * camera: the fake camera delivers frames, a frame is captured and used, and the app says the OCR engine could not be loaded;
  * upload: exactly one real `input#docfile` exists, then four uploads through it - unsupported .txt, an unreadable 1x1 PNG,
    a readable PNG, a PDF - each with its exact expected message; nothing is skipped silently (a missing control or message fails);
  * no `securitypolicyviolation` and no uncaught page error.
Requests to https://cdn.jsdelivr.net/** (Tesseract.js, PDF.js) are aborted so the \"library unavailable\" messages are the same offline and online.
It does NOT prove OCR or PDF reading work (that needs the libraries; see docs/KNOWN_ISSUES.md).
The expected wording follows services/ocr.js and features/verifyDocument/flow.js; changing that text requires updating this test.
Run: python tests/browser/camera_upload_test.py   (Playwright + Chromium; throwaway database)"""
import os, socket, struct, subprocess, sys, tempfile, time, zlib
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from session_entry import dismiss_consent, enter_as_guest, enter_as_user  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WATCH = """() => { window.__csp = []; document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI)); }"""
# 1x1 PNG (too small to read: the quality gate refuses it)
PNG_1X1 = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")

MSG_UNSUPPORTED = "Unsupported file. Please upload a PDF, JPG or PNG."
MSG_UNREADABLE = "too dark, too bright, blank, or too low-resolution"
MSG_NO_OCR = "The OCR engine could not be loaded"
MSG_NO_PDF = "PDF reader could not be loaded"


def readable_png(width=240, height=160):
    """A white page with black bars (standard library only): passes the quality gate (size >= 50 px, mean > 12, variance > 15)."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter type: none
        dark = (y // 10) % 2 == 0 and 20 <= y < height - 20
        for x in range(width):
            rows.append(0 if dark and 20 <= x < width - 20 else 255)
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit greyscale
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def wait_for_text(pg, text, timeout=15000, selector="body"):
    """Fail (TimeoutError) unless `text` appears; never skips."""
    try:
        pg.wait_for_function("([sel, t]) => { const n = document.querySelector(sel); return !!n && n.innerText.includes(t); }", arg=[selector, text], timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"expected text not shown: {text!r}; page says: {pg.inner_text('body')[:400]!r}") from exc


def open_evidence_upload(pg, base):
    """Report A Scam -> Upload Evidence -> choose the first document type -> the upload form. Returns the real file input."""
    pg.goto(base + "/"); pg.wait_for_selector("#app *", state="attached")
    dismiss_consent(pg)
    pg.locator('[data-onclick*="reportslist"]').first.dispatch_event("click")
    pg.locator('[data-onclick*="openReportEvidenceUpload"]').first.dispatch_event("click")
    pg.locator('[data-onclick^="docPickAutoType"]').first.dispatch_event("click")
    pg.wait_for_selector("input#docfile", state="attached", timeout=10000)
    inputs = pg.locator("input#docfile")
    assert inputs.count() == 1, f"expected exactly one input#docfile, found {inputs.count()}"
    return inputs


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

            def new_page():
                ctx = b.new_context(permissions=["camera"]); pg = ctx.new_page()
                pg.on("pageerror", lambda e: errors.append(f"pageerror: {str(e)[:200]}"))
                pg.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())   # Tesseract.js / PDF.js unavailable, deterministically
                pg.add_init_script(f"({WATCH})()")
                return pg

            # 1. a guest cannot reach the evidence actions
            gp = new_page()
            enter_as_guest(gp, base); gp.wait_for_selector("#app *", state="attached")
            gp.locator('[data-onclick*="reportslist"]').first.dispatch_event("click")
            wait_for_text(gp, "Login required")
            assert gp.locator('[data-onclick*="openReportEvidenceCamera"]').count() == 0, "guest sees the camera button"
            assert gp.locator('[data-onclick*="openReportEvidenceUpload"]').count() == 0, "guest sees the upload button"
            print("guest refused: login dialog, no evidence buttons")
            violations = gp.evaluate("() => window.__csp || []")

            # 2. a registered user: camera path (real capture)
            pg = new_page()
            enter_as_user(pg, base); pg.wait_for_selector("#app *", state="attached")
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
            wait_for_text(pg, MSG_NO_OCR, selector="#app")
            print("camera: frame captured and used ->", MSG_NO_OCR)

            # 3. upload path through the real file input; every case must show its exact message
            files = open_evidence_upload(pg, base)
            txt = tmp / "evidence.txt"; txt.write_text("not a document", encoding="utf-8")
            files.first.set_input_files(str(txt))
            wait_for_text(pg, MSG_UNSUPPORTED, selector="#app")
            print("upload: unsupported file refused")

            files = open_evidence_upload(pg, base)
            files.first.set_input_files({"name": "evidence.png", "mimeType": "image/png", "buffer": PNG_1X1})
            wait_for_text(pg, MSG_UNREADABLE, selector="#app")
            print("upload: unreadable image refused with a clear message")

            files = open_evidence_upload(pg, base)
            files.first.set_input_files({"name": "evidence.png", "mimeType": "image/png", "buffer": readable_png()})
            wait_for_text(pg, MSG_NO_OCR, selector="#app")
            print("upload: readable PNG accepted ->", MSG_NO_OCR)

            files = open_evidence_upload(pg, base)
            pdf = tmp / "evidence.pdf"; pdf.write_bytes(b"%PDF-1.4\n%fake\n")
            files.first.set_input_files(str(pdf))
            wait_for_text(pg, MSG_NO_PDF, selector="#app")
            print("upload: PDF accepted ->", MSG_NO_PDF)

            violations += pg.evaluate("() => window.__csp || []")
            b.close()
        assert not violations, f"CSP violations: {violations}"
        assert not errors, errors
        print("camera_upload_test OK"); return 0
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
