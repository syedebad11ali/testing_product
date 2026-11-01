"""Security response headers (one ``after_request``) and the Content-Security-Policy.

Inline scripts that must stay (the theme bootstrap in ``index.html``) are allowed by SHA-256
hash, computed at startup from the real file so the hash can never go stale.

STRICT STYLES (docs/KNOWN_ISSUES.md): every HTML page is served with a ``style-src`` that has NO ``'unsafe-inline'``
(``STRICT_STYLE_PATHS`` plus HTML 404s). tests/frontend/strictStyles.test.js proves each page's HTML and every module it
loads contain no inline style markup, and tests/browser/csp_test.py loads them all watching for CSP violations. Computed
styles are applied through the CSSOM (ui/dataStyle.js), which CSP allows. ``/chatbot-demo`` is strict too (session 17: its
one inline <style> block moved to css/widget-demo.css; the widget itself only writes styles through the CSSOM). The embeddable
widget runs under the EMBEDDING site's CSP when used elsewhere, which this file cannot control. Inline event handlers are
forbidden too (``script-src-attr 'none'``).
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from flask import Flask, g, request

from backend.config import Settings

_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)
CDN = "https://cdn.jsdelivr.net"


def inline_script_hashes(html_files: list[Path]) -> list[str]:
    """CSP ``'sha256-…'`` sources for every inline ``<script>`` in the given HTML files."""
    out: list[str] = []
    for path in html_files:
        if not path.is_file():
            continue
        for body in _INLINE_SCRIPT.findall(path.read_text(encoding="utf-8")):
            if body.strip():
                digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
                out.append(f"'sha256-{digest}'")
    return out


INLINE_STYLE = "'unsafe-inline' "  # only for paths outside STRICT_STYLE_PATHS (none of the HTML pages today)
GIS = "https://accounts.google.com/gsi/"  # the only Google sign-in surface the CSP opens


# Pages verified free of inline styles (HTML + the whole module graph they load). Add a path here only together with
# its entry scripts in tests/frontend/strictStyles.test.js, which fails if any covered file gains inline style markup.
STRICT_STYLE_PATHS = frozenset({
    "/", "/index.html", "/login", "/signup", "/admin", "/admin.html", "/privacy", "/privacy.html", "/messages", "/messages.html",
    "/listings", "/listings.html", "/nice-try", "/nice-try.html", "/chatbot-demo",
})


def build_csp(script_hashes: list[str], strict_styles: bool = False) -> str:
    directives = {
        "default-src": "'self'",
        "script-src": " ".join(["'self'", CDN, GIS + "client", "'wasm-unsafe-eval'", *script_hashes]),
        "script-src-attr": "'none'",  # inline on*="" handlers are gone (ui/dispatch.js)
        "style-src": f"'self' {'' if strict_styles else INLINE_STYLE}https://fonts.googleapis.com {GIS}style",
        "font-src": "'self' https://fonts.gstatic.com",
        "img-src": "'self' data: blob:",
        "media-src": "'self' blob:",
        "connect-src": f"'self' {CDN} https://tessdata.projectnaptha.com {GIS} blob: data:",
        "frame-src": GIS,  # Google Identity Services button / FedCM iframe
        "worker-src": "'self' blob:",
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self' https://accounts.google.com",
        "frame-ancestors": "'none'",
    }
    return "; ".join(f"{k} {v}" for k, v in directives.items())


def register_security_headers(app: Flask, settings: Settings) -> None:
    hashes = inline_script_hashes([settings.frontend_dir / "index.html"])
    csp, strict_csp = build_csp(hashes), build_csp(hashes, strict_styles=True)
    static = {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        # Camera is needed by document verification (self only); everything else off.
        "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), payment=(), usb=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-site",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    }

    @app.before_request
    def _request_id():
        supplied = request.headers.get("X-Request-ID", "")
        g.request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{8,64}", supplied) else __import__("uuid").uuid4().hex[:16]

    @app.after_request
    def _headers(resp):
        for name, value in static.items():
            resp.headers.setdefault(name, value)
        # The widget script is embedded cross-site by <script>, which CORP same-site would block.
        if request.path in STRICT_STYLE_PATHS or (resp.status_code == 404 and resp.mimetype == "text/html"):
            resp.headers["Content-Security-Policy"] = strict_csp
        if request.path.startswith("/static/chatbot."):
            resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        if request.path in ("/login", "/signup"):  # Google's button popup needs window.opener; only these pages
            resp.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        if request.path.startswith(("/api/", "/admin", "/login", "/signup")):
            resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return resp
