"""POST /chat — one conversational turn."""
from __future__ import annotations

import uuid

from flask import Blueprint, current_app, jsonify, request

from backend.errors import ApiError

bp = Blueprint("chat", __name__)


def _read_message(max_len: int) -> tuple[str, str]:
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
    return session_id, message


@bp.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return "", 204
    kpt = current_app.extensions["kpt"]
    kpt.rate_limiter.check(request.remote_addr or "unknown")
    session_id, message = _read_message(kpt.settings.max_message_len)
    return jsonify(kpt.chat_service().reply(session_id, message))
