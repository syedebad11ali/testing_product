"""CSRF protection: Origin check + double-submit token, for every state-changing auth-bearing route.

The token is a random value stored in a (JS-readable) cookie and echoed by the frontend in the
``X-CSRF-Token`` header; a cross-site page can neither read the cookie nor set the header. The
``__Host-`` cookie prefix stops sibling subdomains from planting a token. The public chat endpoint is
deliberately exempt (anonymous, no cookies used) because third-party sites embed the widget.
"""
from __future__ import annotations

import hmac
import re
import secrets

from flask import Flask, jsonify, request

from backend.config import Settings
from backend.errors import ApiError
from backend.security.cookies import cookie_name, set_cookie

PROTECTED = re.compile(r"^/api(?:/v1)?/(?:auth|admin|verification|messages|listings)/")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _origin_ok(settings: Settings) -> bool:
    origin = request.headers.get("Origin")
    if not origin:  # non-browser client or same-origin GET-style navigation; the token check still applies
        return True
    return origin == request.host_url.rstrip("/") or origin in settings.allowed_origins


def register_csrf(app: Flask, settings: Settings) -> None:
    @app.before_request
    def _guard():
        if request.method in SAFE_METHODS or not PROTECTED.match(request.path):
            return None
        if not _origin_ok(settings):
            raise ApiError("Cross-site request blocked.", 403, "csrf_failed")
        cookie = request.cookies.get(cookie_name(settings, "csrf"), "")
        header = request.headers.get("X-CSRF-Token", "")
        if not cookie or not hmac.compare_digest(cookie.encode(), header.encode()):
            raise ApiError("Security token missing or expired. Please reload the page.", 403, "csrf_failed")
        return None

    @app.get("/api/v1/auth/csrf")
    def csrf_token():
        token = request.cookies.get(cookie_name(settings, "csrf"), "")
        fresh = not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", token)
        if fresh:
            token = secrets.token_urlsafe(32)
        resp = jsonify(csrf_token=token)
        if fresh:
            set_cookie(resp, settings, "csrf", token, http_only=False)  # JS must read it (double submit)
        return resp
