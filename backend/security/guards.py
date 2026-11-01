"""Route guards: ``login_required`` and ``role_required``. Authorisation is decided here, on the server.

The session cookie is resolved once per request into ``g.session`` (a dict with user id, role, ...).
"""
from __future__ import annotations

from functools import wraps

from flask import Flask, current_app, g, request

from backend.errors import ApiError
from backend.security.cookies import clear_cookie, read_cookie, set_cookie


def current_session() -> dict | None:
    if not hasattr(g, "_session"):
        kpt = current_app.extensions["kpt"]
        raw = read_cookie(request, kpt.settings, "session")
        g._session = kpt.sessions().lookup(raw) if raw else None
        g.session_raw = raw
        if g._session is None and read_cookie(request, kpt.settings, "remember"):
            _restore_from_remember(kpt)
    return g._session


def _restore_from_remember(kpt) -> None:
    """No valid session but a remember cookie: validate + rotate it and start a fresh (non-admin) session.

    The new cookies are attached to the response by ``register_session_cookies``. A rotated-token replay
    revokes everything for that user (see ``RememberService.redeem``) and clears the cookie."""
    from backend.errors import ApiError
    try:
        remember = kpt.remember()
    except ApiError:
        return
    raw_cookie = read_cookie(request, kpt.settings, "remember")
    ua = request.headers.get("User-Agent", "")
    result = remember.redeem(raw_cookie, ua)
    if result is None:
        g.clear_remember = True
        return
    user = kpt.database().one("SELECT id, name, email, username, role, status, must_change_password FROM users WHERE id = ?", (result.user_id,))
    raw = kpt.sessions().create(user, kpt.audit().ip_hash(request.remote_addr), ua)
    kpt.audit().login_event(identifier=user["email"] or user["username"] or "", method="remember", success=True,
                            ip_hash=kpt.audit().ip_hash(request.remote_addr), user_agent=ua, user_id=user["id"], reason="remember_token")
    g.new_session_raw, g.new_remember_value = raw, result.cookie_value
    g._session, g.session_raw = kpt.sessions().lookup(raw), raw


def register_session_cookies(app: Flask) -> None:
    """Attach cookies produced while resolving the session (remember rotation / clearing)."""
    @app.after_request
    def _attach(resp):
        kpt = current_app.extensions["kpt"]
        if getattr(g, "new_session_raw", None):
            set_cookie(resp, kpt.settings, "session", g.new_session_raw, max_age=None)
            set_cookie(resp, kpt.settings, "remember", g.new_remember_value, max_age=kpt.settings.remember_days * 86400)
        elif getattr(g, "clear_remember", False):
            clear_cookie(resp, kpt.settings, "remember")
        return resp


def _check_account(allow_pending_password_change: bool, allow_guest: bool) -> dict:
    """The one implementation of the account checks, shared by ``login_required`` and ``require_account``:
    anonymous -> 401 ``auth_required``; pending password change -> 403 ``password_change_required``;
    guest -> 403 ``guest_not_allowed``. Returns the session of a registered user or admin."""
    sess = current_session()
    if not sess:
        raise ApiError("Please log in to continue.", 401, "auth_required")
    if sess["must_change_password"] and not allow_pending_password_change:
        raise ApiError("You must change your password before continuing.", 403, "password_change_required")
    if sess["role"] == "guest" and not allow_guest:
        raise ApiError("Create an account or log in to use this feature.", 403, "guest_not_allowed")
    return sess


def login_required(allow_pending_password_change: bool = False, allow_guest: bool = False):
    """Signed-in users only. A guest session (``role == "guest"``) is rejected with 403 unless the route opts in with
    ``allow_guest=True``; so every private/write route is closed to guests by default."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            _check_account(allow_pending_password_change, allow_guest)
            return fn(*a, **kw)
        return wrapper
    return deco


def require_account(allow_pending_password_change: bool = False, allow_guest: bool = False) -> dict | None:
    """Same checks as ``login_required`` for use INSIDE a handler (routes that also serve CORS ``OPTIONS`` pre-flights,
    which carry no cookies and must keep answering). A pre-flight returns ``None`` without any check; every other method
    raises the same ``ApiError`` as the decorator and otherwise returns the session."""
    if request.method == "OPTIONS":
        return None
    return _check_account(allow_pending_password_change, allow_guest)


def role_required(*roles: str):
    def deco(fn):
        @login_required()
        @wraps(fn)
        def wrapper(*a, **kw):
            if current_session()["role"] not in roles:
                raise ApiError("You do not have permission to do that.", 403, "forbidden")
            return fn(*a, **kw)
        return wrapper
    return deco
