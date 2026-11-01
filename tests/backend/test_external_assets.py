"""Inventory of third-party assets and the CSP that allows them (offline; fetches nothing).

This does NOT prove the assets are self-hosted: it records what the frontend references today and fails when a NEW host or a NEW
floating (non exact-version) CDN URL appears. When Tesseract.js is vendored (scripts/vendor_assets.py) remove the matching entry from
KNOWN_FLOATING, and remove the CDN hosts that are no longer needed from ALLOWED_HOSTS and from backend/security/headers.py.
"""
import dataclasses
import re
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from backend.app import create_app  # noqa: E402
from backend.config import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
URL = re.compile(r"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+")
IGNORED = ("w3.org", "api.example.com", "localhost", "127.0.0.1", "YOUR-HOST", "http://local")
ALLOWED_HOSTS = {"cdn.jsdelivr.net": "PDF.js + Tesseract.js (vendor them)", "fonts.googleapis.com": "web fonts CSS", "fonts.gstatic.com": "web font files",
                 "accounts.google.com": "Google Sign-In (intentionally external)"}
# Hosts that may appear ONLY as plain <a href> navigation links in HTML (never loaded as a script, style, image, font or fetch target,
# so they need no CSP entry and are asserted to be absent from the CSP below).
OUTBOUND_LINK_HOSTS = {"github.com": "Creators menu credit links (frontend/index.html)"}
KNOWN_FLOATING = {"tesseract.js@5"}   # floating major tag in frontend/index.html: pin or vendor it, then delete this entry
EXACT = re.compile(r"/npm/([a-z0-9.@/_-]+?)@(\d+\.\d+\.\d+)(?:/|$)")


def frontend_urls():
    for path in (ROOT / "frontend").rglob("*"):
        if path.suffix in {".html", ".js", ".css"} and path.is_file():
            for m in URL.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                if not any(i in m.group(0) for i in IGNORED):
                    yield path.relative_to(ROOT).as_posix(), m.group(0).rstrip(".,;)'\"")


class ExternalAssetInventory(unittest.TestCase):
    def test_only_known_third_party_hosts_are_referenced(self):
        hosts = {re.match(r"https?://([^/:?#]+)", u).group(1) for _, u in frontend_urls()}
        self.assertEqual(hosts - set(ALLOWED_HOSTS) - set(OUTBOUND_LINK_HOSTS), set(), "new third-party host in frontend files: review it and the CSP first")

    def test_outbound_link_hosts_are_only_anchor_navigation_and_stay_out_of_the_csp(self):
        for where, url in frontend_urls():
            host = re.match(r"https?://([^/:?#]+)", url).group(1)
            if host in OUTBOUND_LINK_HOSTS:
                self.assertTrue(where.endswith(".html"), f"{url} referenced from {where}: outbound-only hosts may appear in HTML links only")
                self.assertIn(f'<a href="{url}"', (ROOT / where).read_text(encoding="utf-8"), f"{url} in {where} must be a plain <a href> link")
        client = create_app(dataclasses.replace(Settings.from_env(), local_db_path=":memory:", gemini_api_key=None)).test_client()
        for path in ("/", "/login"):
            self.assertNotIn("github.com", client.get(path).headers["Content-Security-Policy"], "navigation links must not widen the CSP")

    def test_jsdelivr_urls_are_exact_versions_except_the_known_floating_one(self):
        floating = set()
        for where, url in frontend_urls():
            if "cdn.jsdelivr.net/npm/" in url and not EXACT.search(url):
                floating.add(url.split("/npm/")[1].split("/")[0])
        self.assertEqual(floating, KNOWN_FLOATING, f"floating CDN versions changed: {sorted(floating)}")

    def test_pdfjs_main_and_worker_versions_match(self):
        versions = {m.group(2) for _, u in frontend_urls() if "pdfjs-dist" in u for m in [EXACT.search(u)] if m}
        self.assertEqual(len(versions), 1, versions)


class ServedCsp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app(dataclasses.replace(Settings.from_env(), local_db_path=":memory:", gemini_api_key=None)).test_client()

    def directives(self, path):
        raw = self.client.get(path).headers["Content-Security-Policy"]
        return {d.split()[0]: d.split()[1:] for d in raw.split(";") if d.strip()}

    def test_no_unsafe_eval_or_unsafe_inline_scripts_anywhere(self):
        for path in ("/", "/login", "/signup", "/listings", "/messages", "/privacy", "/nice-try", "/chatbot-demo"):
            d = self.directives(path)
            for name in ("script-src", "script-src-attr", "default-src"):
                self.assertNotIn("'unsafe-eval'", d.get(name, []), (path, name))
                self.assertNotIn("'unsafe-inline'", d.get(name, []), (path, name))
            self.assertNotIn("'unsafe-eval'", sum(d.values(), []), path)

    def test_third_party_origins_in_csp_are_the_known_ones(self):
        allowed = set(ALLOWED_HOSTS) | {"tessdata.projectnaptha.com"}   # runtime language data fetched by Tesseract.js
        for path in ("/", "/login"):
            for name, values in self.directives(path).items():
                for v in values:
                    m = re.match(r"https?://([^/:]+)", v)
                    if m:
                        self.assertIn(m.group(1), allowed, f"{path} {name} allows an unreviewed host {v}")

    def test_styles_stay_strict_on_html_pages(self):
        for path in ("/", "/login", "/listings", "/messages", "/chatbot-demo"):
            self.assertNotIn("'unsafe-inline'", self.directives(path).get("style-src", []), path)


if __name__ == "__main__":
    unittest.main()
