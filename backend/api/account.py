"""Account-side privacy endpoints (v1 only; all under ``/auth/`` so they inherit CSRF protection).

* ``GET  /auth/devices``           remember-me devices of the signed-in user
* ``POST /auth/devices/revoke``    revoke one device
* ``POST /auth/logout-all``        sign out everywhere (sessions + remember tokens)
* ``GET|PUT /auth/prefs``          account copy of the preference cookie values (follow the user across devices)
* ``POST /auth/forget-device``     clear this device's non-essential server-side state (works signed out too)
* ``POST /auth/delete-account``    delete the account and its data (password re-authentication required)

Thin: validation here, rules in ``services/``.
"""
from __future__ import annotations

import re

from flask import Blueprint, current_app, jsonify, request

from backend.errors import ApiError
from backend.security.cookies import clear_cookie, read_cookie
from backend.security.guards import current_session, login_required
from backend.services import prefs as prefs_mod

bp = Blueprint("account", __name__)
V1_ONLY = True


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")
    return data


def _selector(kpt) -> str:
    raw = read_cookie(request, kpt.settings, "remember")
    return raw.split(".")[0] if "." in raw else ""


@bp.get("/auth/devices")
@login_required()
def devices():
    kpt, sess = current_app.extensions["kpt"], current_session()
    resp = jsonify(devices=kpt.remember().devices(sess["user_id"], _selector(kpt)))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/auth/devices/revoke")
@login_required()
def revoke_device():
    kpt, sess = current_app.extensions["kpt"], current_session()
    token_id = _body().get("id")
    if not isinstance(token_id, str) or not re.fullmatch(r"[0-9a-f]{32}", token_id):
        raise ApiError("'id' is required.", 400, "invalid_id")
    if not kpt.remember().revoke_one(sess["user_id"], token_id):
        raise ApiError("Device not found.", 404, "not_found")
    return jsonify(ok=True)


@bp.post("/auth/logout-all")
@login_required()
def logout_all():
    kpt, sess = current_app.extensions["kpt"], current_session()
    kpt.remember().revoke_user(sess["user_id"])
    resp = jsonify(ok=True)
    for name in ("session", "remember"):
        clear_cookie(resp, kpt.settings, name)
    return resp


@bp.get("/auth/prefs")
@login_required()
def get_prefs():
    kpt, sess = current_app.extensions["kpt"], current_session()
    resp = jsonify(prefs=kpt.prefs().get(sess["user_id"]))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.put("/auth/prefs")
@login_required()
def put_prefs():
    """Store (merged with what is already saved) the sanitised preference values; returns the result."""
    kpt, sess = current_app.extensions["kpt"], current_session()
    incoming = _body().get("prefs")
    if not isinstance(incoming, dict):
        raise ApiError("'prefs' must be an object.", 400, "invalid_prefs")
    merged = prefs_mod.merge(kpt.prefs().get(sess["user_id"]), incoming)
    return jsonify(prefs=kpt.prefs().set(sess["user_id"], merged))


@bp.post("/auth/forget-device")
def forget_device():
    """Drop this device's remember token, chat conversation and optional cookies. Essential cookies stay."""
    kpt = current_app.extensions["kpt"]
    resp = jsonify(ok=True)
    try:
        cookie = read_cookie(request, kpt.settings, "remember")
        if cookie:
            kpt.remember().revoke_cookie(cookie)
        chat = read_cookie(request, kpt.settings, "chat")
        if re.fullmatch(r"[0-9a-f]{32}", chat) and (store := kpt.chat_store()):
            store.delete(chat)
    except ApiError:
        pass  # no database configured: nothing server-side to forget
    for name in ("remember", "chat"):
        clear_cookie(resp, kpt.settings, name)
    return resp


@bp.post("/auth/delete-account")
@login_required()
def delete_account():
    kpt, sess = current_app.extensions["kpt"], current_session()
    data = _body()
    if data.get("confirm") != "DELETE":
        raise ApiError("Type DELETE to confirm.", 400, "confirm_required")
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    kpt.auth().delete_account(sess["user_id"], password, kpt.audit().ip_hash(request.remote_addr))
    resp = jsonify(ok=True)
    for name in ("session", "remember", "chat"):
        clear_cookie(resp, kpt.settings, name)
    return resp
