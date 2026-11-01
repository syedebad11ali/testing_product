"""Auth endpoints (v1 only): csrf token (see security/csrf.py), signup, login, logout, me, change-password.

Thin: validation + cookies here, all rules in ``services/auth_service.py``.
``POST /auth/login`` for ``admin_001`` with a wrong password answers ``200 {"redirect": "/nice-try"}``
every time (same body, same work), never creates a session, and is logged + counted toward lockout.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.errors import ApiError
from backend.security import consent
from backend.security.cookies import clear_cookie, read_cookie, set_cookie
from backend.security.guards import current_session, login_required
from backend.services import dev_skip
from backend.services.auth_service import public_user

bp = Blueprint("auth", __name__)
V1_ONLY = True
INVALID = ("Invalid email or password.", 401, "invalid_credentials")


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")
    return data


def _str(data: dict, key: str, max_len: int, *, strip: bool = True) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ApiError(f"'{key}' must be text.", 400, f"invalid_{key}")
    value = value.strip() if strip else value
    if not value or len(value) > max_len:
        raise ApiError(f"'{key}' is required (max {max_len} characters).", 400, f"invalid_{key}")
    return value


def _ctx():
    kpt = current_app.extensions["kpt"]
    kpt.auth_limiter.check(request.remote_addr or "unknown")  # per-IP, fail-closed store in production
    return kpt, kpt.audit().ip_hash(request.remote_addr), request.headers.get("User-Agent", "")


def _start_session(body: dict, kpt, raw: str, user: dict, remember: bool = False, status: int = 200):
    """JSON response + session cookie; with ``remember`` also a rotating remember token, if allowed.

    A remember token needs (1) the visitor's Preferences consent, (2) a non-admin account and (3) no pending
    password change. The body reports the outcome so the UI can say why it was not remembered."""
    s = kpt.settings
    if user.get("role") != "guest":  # a guest who signs up / logs in: end that guest session now (not on guest re-entry)
        prior = current_session()    # only the caller's own session cookie; other guests on the same network are untouched
        if prior and prior["role"] == "guest":
            kpt.guests().discard(prior["user_id"])
    cookie_value = None
    if remember:
        allowed = consent.allows(request, "preferences")
        cookie_value = kpt.remember().issue({**user, "id": user.get("id") or user.get("user_id")}, request.headers.get("User-Agent", "")) if allowed else None
        body = {**body, "remembered": bool(cookie_value)}
        if not cookie_value:
            body["remember_note"] = ("Not remembered: allow Preferences cookies in Privacy & cookies to stay signed in."
                                     if not allowed else "Staying signed in is not available for this account.")
    resp = jsonify(body)
    resp.status_code = status
    set_cookie(resp, s, "session", raw, max_age=None)  # browser-session cookie; server enforces idle/absolute limits
    if cookie_value:
        set_cookie(resp, s, "remember", cookie_value, max_age=s.remember_days * 86400)
    return resp


@bp.post("/auth/signup")
def signup():
    kpt, ip_hash, ua = _ctx()
    data = _body()
    user, raw = kpt.auth().signup(_str(data, "name", 80), _str(data, "email", 254), _str(data, "password", 1024, strip=False), ip_hash, ua)
    return _start_session({"ok": True, "user": public_user(user), "redirect": "/"}, kpt, raw, user, status=201)


@bp.post("/auth/login")
def login():
    kpt, ip_hash, ua = _ctx()
    data = _body()
    outcome = kpt.auth().login(_str(data, "identifier", 254), _str(data, "password", 1024, strip=False), ip_hash, ua)
    if outcome.kind == "admin_denied":
        return jsonify(redirect="/nice-try")  # identical for every wrong attempt; the server decided
    if outcome.kind != "ok":
        raise ApiError(*INVALID)
    user = outcome.user
    target = "/login?change=1" if user["must_change_password"] else ("/admin" if user["role"] == "admin" else "/")
    return _start_session({"ok": True, "user": public_user(user), "redirect": target}, kpt, outcome.session_id, user,
                          remember=data.get("remember") is True)


@bp.post("/auth/developer-login")
def developer_login():
    """Developer Login page endpoint. Only an active ADMIN account can get a session here; every other outcome
    (unknown user, wrong password, correct password of a non-admin, locked, banned) answers the same
    ``200 {"redirect": "/nice-try"}`` and never sets a session cookie. In development the legacy ``admin__01`` +
    ``DEV_ADMIN_PASSWORD`` pair is also accepted (never in production, see ``services/dev_skip.py``)."""
    kpt, ip_hash, ua = _ctx()
    data = _body()
    identifier, password = _str(data, "identifier", 254), _str(data, "password", 1024, strip=False)
    if dev_skip.available(kpt.settings) and identifier.strip().lower() == dev_skip.DEV_ADMIN_USERNAME:
        found = dev_skip.try_dev_admin(kpt, identifier, password, ip_hash, ua)
        if not found:
            return jsonify(redirect=dev_skip.TROLL_REDIRECT)
        user, raw = found
        return _start_session({"ok": True, "user": public_user(user), "redirect": "/admin"}, kpt, raw, user)
    outcome = kpt.auth().login(identifier, password, ip_hash, ua, admin_only=True)
    if outcome.kind != "ok":
        return jsonify(redirect=dev_skip.TROLL_REDIRECT)
    user = outcome.user
    target = "/login?change=1" if user["must_change_password"] else "/admin"
    return _start_session({"ok": True, "user": public_user(user), "redirect": target}, kpt, outcome.session_id, user)


@bp.post("/auth/guest")
def guest_login():
    """"Continue as guest": a restricted server-side guest session (``role == "guest"``). No credentials, no remember-me,
    never admin. Rate limited per IP like every auth route and capped per network (see ``GuestService``)."""
    kpt, ip_hash, ua = _ctx()
    user, raw = kpt.guests().create(ip_hash, ua)
    return _start_session({"ok": True, "user": public_user(user), "redirect": "/"}, kpt, raw, user, status=201)


@bp.post("/auth/dev-skip")
def dev_skip_login():
    """DEV ONLY troll button. Every attempt answers ``200 {"redirect": "/nice-try"}`` (no session) except the
    ``admin__01`` + ``DEV_ADMIN_PASSWORD`` pair, which starts a normal admin session. 404 in production."""
    kpt = current_app.extensions["kpt"]
    if not dev_skip.available(kpt.settings):
        raise ApiError("Not found.", 404, "not_found")
    kpt, ip_hash, ua = _ctx()
    data = _body()
    found = dev_skip.try_dev_admin(kpt, _str(data, "identifier", 254), _str(data, "password", 1024, strip=False), ip_hash, ua)
    if not found:
        return jsonify(redirect=dev_skip.TROLL_REDIRECT)
    user, raw = found
    return _start_session({"ok": True, "user": public_user(user), "redirect": "/admin"}, kpt, raw, user)


@bp.get("/auth/google/config")
def google_config():
    """Public client id + a fresh single-use nonce for Google Identity Services (no build step => fetched at runtime)."""
    kpt = current_app.extensions["kpt"]
    kpt.auth_limiter.check(request.remote_addr or "unknown")
    if not kpt.settings.google_client_id:
        return jsonify(configured=False)
    resp = jsonify(configured=True, client_id=kpt.settings.google_client_id, nonce=kpt.google().issue_nonce())
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/auth/google")
def google_login():
    kpt, ip_hash, ua = _ctx()
    data = _body()
    ident = kpt.google().verify(_str(data, "credential", 4096))  # 503 when unconfigured, generic 401 otherwise
    outcome = kpt.auth().google_login(ident, ip_hash, ua)
    if outcome.kind != "ok":
        raise ApiError("Google sign-in failed. Please try again.", 401, "google_invalid")
    user = outcome.user
    target = "/admin" if user["role"] == "admin" else "/"
    return _start_session({"ok": True, "user": public_user(user), "redirect": target}, kpt, outcome.session_id, user,
                          remember=data.get("remember") is True)


@bp.get("/auth/features")
def features():
    """What the login page may offer. Lets the UI say honestly that email reset is not set up yet."""
    kpt = current_app.extensions["kpt"]
    from backend.services.mailer import Mailer
    return jsonify(google=bool(kpt.settings.google_client_id), password_reset=bool(kpt.mail_sender) or Mailer(kpt.settings).enabled,
                   dev_skip=dev_skip.available(kpt.settings), developer_login=True, guest=True)


@bp.post("/auth/forgot")
def forgot_password():
    """Always 202 with the same body, whether or not the email has an account (no enumeration)."""
    kpt, ip_hash, ua = _ctx()
    kpt.password_reset().request_reset(_str(_body(), "email", 254), ip_hash, ua)
    return jsonify(ok=True, message="If that email has an account, a reset link is on its way."), 202


@bp.post("/auth/reset")
def reset_password():
    kpt, ip_hash, _ua = _ctx()
    data = _body()
    kpt.password_reset().reset(_str(data, "token", 200), _str(data, "new_password", 1024, strip=False), ip_hash)
    return jsonify(ok=True, redirect="/login")


@bp.post("/auth/logout")
def logout():
    kpt = current_app.extensions["kpt"]
    sess = current_session()
    from flask import g
    if getattr(g, "session_raw", ""):
        kpt.sessions().revoke(g.session_raw)
    if sess and sess["role"] == "guest":
        kpt.guests().discard(sess["user_id"])
    cookie = read_cookie(request, kpt.settings, "remember")
    if cookie:  # logging out ends 'remember me' on THIS device only
        kpt.remember().revoke_cookie(cookie)
    resp = jsonify(ok=True)
    clear_cookie(resp, kpt.settings, "session")
    clear_cookie(resp, kpt.settings, "remember")
    return resp


@bp.get("/auth/me")
def me():
    sess = current_session()
    return jsonify(user=public_user({**sess, "id": sess["user_id"]}) if sess else None)


@bp.post("/auth/change-password")
@login_required(allow_pending_password_change=True)
def change_password():
    from flask import g
    kpt = current_app.extensions["kpt"]
    data, sess = _body(), current_session()
    kpt.auth().change_password(sess["user_id"], _str(data, "current_password", 1024, strip=False),
                               _str(data, "new_password", 1024, strip=False), g.session_raw)
    kpt.audit().admin_action(sess["user_id"], "password_changed", sess["user_id"], kpt.audit().ip_hash(request.remote_addr))
    return jsonify(ok=True)
