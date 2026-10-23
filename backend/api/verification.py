"""POST /verification/check — compare a claimed owner name with the registered one.

Returns only match / mismatch / unable_to_verify. TODO(phase 4): require a logged-in user.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.errors import ApiError

bp = Blueprint("verification", __name__)


def _text(data: dict, key: str, max_len: int) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ApiError(f"'{key}' must be text.", 400, f"invalid_{key}")
    value = value.strip()
    if not value or len(value) > max_len:
        raise ApiError(f"'{key}' is required (max {max_len} characters).", 400, f"invalid_{key}")
    return value


@bp.post("/verification/check")
def check():
    kpt = current_app.extensions["kpt"]
    kpt.verify_limiter.check(request.remote_addr or "unknown")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")
    return jsonify(kpt.verification_service().check(_text(data, "property_id", 40), _text(data, "owner_name", 120),
                                                    actor=request.remote_addr or "unknown"))
