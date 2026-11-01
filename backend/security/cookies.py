"""Cookie helpers. One place decides names and flags so every Set-Cookie is deliberate.

With ``cookie_secure`` (production / https) names get the ``__Host-`` prefix (browser then enforces
Secure + Path=/ + no Domain). Plain http local development uses un-prefixed names because browsers
reject ``__Host-`` cookies without Secure.
"""
from __future__ import annotations

from flask import Request, Response

from backend.config import Settings


def cookie_name(settings: Settings, base: str) -> str:
    return f"__Host-kpt_{base}" if settings.cookie_secure else f"kpt_{base}"


def set_cookie(resp: Response, settings: Settings, base: str, value: str, *, max_age: int | None = None,
               http_only: bool = True) -> None:
    resp.set_cookie(cookie_name(settings, base), value, max_age=max_age, secure=settings.cookie_secure,
                    httponly=http_only, samesite="Lax", path="/")


def clear_cookie(resp: Response, settings: Settings, base: str) -> None:
    resp.set_cookie(cookie_name(settings, base), "", max_age=0, expires=0, secure=settings.cookie_secure,
                    httponly=True, samesite="Lax", path="/")


def read_cookie(request: Request, settings: Settings, base: str) -> str:
    return request.cookies.get(cookie_name(settings, base), "")
