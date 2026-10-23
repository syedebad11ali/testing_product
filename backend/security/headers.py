"""Security response headers (one ``after_request``) and the Content-Security-Policy.

Inline scripts that must stay (the theme bootstrap in ``index.html``) are allowed by SHA-256
hash, computed at startup from the real file so the hash can never go stale.

KNOWN GAP (docs/KNOWN_ISSUES.md): ``script-src-attr`` and ``style-src`` still allow
``'unsafe-inline'`` because ~91 inline ``onclick`` handlers and inline ``style`` attributes
remain. Phase 2 (data-action migration) removes both; then delete those two tokens.
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


def build_csp(script_hashes: list[str]) -> str:
    directives = {
        "default-src": "'self'",
        "script-src": " ".join(["'self'", CDN, "'wasm-unsafe-eval'", *script_hashes]),
        "script-src-attr": "'unsafe-inline'",  # TEMPORARY, see module docstring
        "style-src": "'self' 'unsafe-inline' https://fonts.googleapis.com",  # TEMPORARY inline styles
        "font-src": "'self' https://fonts.gstatic.com",
        "img-src": "'self' data: blob:",
        "media-src": "'self' blob:",
        "connect-src": f"'self' {CDN} https://tessdata.projectnaptha.com blob: data:",
        "worker-src": "'self' blob:",
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self' https://accounts.google.com",
        "frame-ancestors": "'none'",
    }
    return "; ".join(f"{k} {v}" for k, v in directives.items())


def register_security_headers(app: Flask, settings: Settings) -> None:
    csp = build_csp(inline_script_hashes([settings.frontend_dir / "index.html"]))
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
        if request.path.startswith("/static/chatbot."):
            resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        if request.path.startswith(("/api/", "/admin", "/login", "/signup")):
            resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return resp
