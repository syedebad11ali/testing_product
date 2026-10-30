"""POST /chat — one conversational turn. POST /chat/feedback — thumbs up/down on one answer."""
from __future__ import annotations

import json
import re
import time
import uuid
from urllib.parse import unquote

from flask import Blueprint, current_app, jsonify, request

from backend.errors import ApiError
from backend.security import consent
from backend.security.cookies import clear_cookie, read_cookie, set_cookie
from backend.security.guards import current_session
from backend.services import prefs as prefs_mod

bp = Blueprint("chat", __name__)


def _read_message(max_len: int) -> tuple[str, str, bool]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")
    raw = data.get("message", "")
    if not isinstance(raw, str):
        raise ApiError("'message' must be text.", 400, "invalid_message")
    message = raw.strip()
    if not message:
        raise ApiError("Message is empty.", 400, "empty_message")
    if len(message) > max_len:
        raise ApiError(f"Message is too long (max {max_len} characters).", 400, "message_too_long")
    session_id = str(data.get("session_id") or uuid.uuid4())[:64]
    return session_id, message, data.get("reset") is True


@bp.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return "", 204
    kpt = current_app.extensions["kpt"]
    kpt.rate_limiter.check(request.remote_addr or "unknown")
    session_id, message, reset = _read_message(kpt.settings.max_message_len)
    sid, issue = _continuity_id(kpt)
    result = kpt.chat_service().reply(sid or session_id, message, reset=reset, persist=bool(sid))
    resp = jsonify({**result, "continuity": bool(sid)})
    if issue:
        set_cookie(resp, kpt.settings, "chat", sid, max_age=kpt.settings.chat_cookie_days * 86400)
    return resp


def _continuity_id(kpt) -> tuple[str, bool]:
    """Chat id from the ``__Host-kpt_chat`` cookie, only with Preferences consent. ``(id, must_set_cookie)``.

    Without consent (or the cookie) the client's own per-visit ``session_id`` is used and nothing is stored."""
    if not consent.allows(request, "preferences"):
        return "", False
    existing = read_cookie(request, kpt.settings, "chat")
    if re.fullmatch(r"[0-9a-f]{32}", existing):
        kpt.chat_store()  # attach persistence when a database is available
        return existing, False
    kpt.chat_store()
    return uuid.uuid4().hex, True


@bp.get("/chat/session")
def chat_session():
    """Restore the chat window after a refresh / return visit, plus a welcome-back message.

    Only the cookie's own conversation is returned (never another visitor's). First name appears only for
    a signed-in user; anonymous visitors get a generic greeting and a last-viewed-property chip."""
    kpt = current_app.extensions["kpt"]
    kpt.rate_limiter.check(request.remote_addr or "unknown")
    sid, _ = _continuity_id(kpt)
    existing = read_cookie(request, kpt.settings, "chat")
    if not sid or not re.fullmatch(r"[0-9a-f]{32}", existing):
        return jsonify(continuity=False, history=[], memory={}, welcome=None)
    snap = kpt.chat_service().snapshot(sid, persisted=True)
    first, sess = "", None
    try:
        sess = current_session()
    except ApiError:
        sess = None
    if sess and sess["role"] != "guest":
        first = (sess["name"] or "").split(" ")[0][:40]
    recent = prefs_mod.sanitize(_prefs_cookie()).get("recent", [])
    welcome = kpt.chat_service().welcome(first, recent[0] if recent else "", bool(snap["history"])) if (snap["history"] or first or recent) else None
    resp = jsonify(continuity=True, history=snap["history"], memory=snap["memory"], welcome=welcome)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _prefs_cookie() -> dict:
    """The JS-readable ``kpt_prefs`` cookie as untrusted JSON (read only with Preferences consent)."""
    if not consent.allows(request, "preferences"):
        return {}
    try:
        return json.loads(unquote(request.cookies.get("kpt_prefs", ""))[:4000])
    except ValueError:
        return {}


@bp.route("/chat/feedback", methods=["POST", "OPTIONS"])
def feedback():
    """Store a thumbs rating. Only the question text (truncated) and intent are kept, for admin analytics."""
    if request.method == "OPTIONS":
        return "", 204
    kpt = current_app.extensions["kpt"]
    kpt.rate_limiter.check(request.remote_addr or "unknown")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")
    message_id, rating = data.get("message_id"), data.get("rating")
    if not isinstance(message_id, str) or not 8 <= len(message_id) <= 64:
        raise ApiError("'message_id' is required.", 400, "invalid_message_id")
    if rating not in ("up", "down"):
        raise ApiError("'rating' must be 'up' or 'down'.", 400, "invalid_rating")
    info = kpt.chat_service().turn_info(message_id)
    kpt.database().execute(
        "INSERT INTO chat_feedback (id, ts, message_id, rating, intent, question, answered) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, int(time.time()), message_id, rating, info.get("intent"), info.get("question"), 1 if info.get("answered", True) else 0))
    return jsonify(ok=True)
