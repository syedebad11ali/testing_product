"""GET /health (public, minimal) and GET /health/detail (token protected diagnostics)."""
from __future__ import annotations

import hmac
import logging

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("health", __name__)
log = logging.getLogger("chatbot")


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/health/detail")
def health_detail():
    """Real startup errors and data counts. TODO(phase 5): replace the token with the admin role."""
    kpt = current_app.extensions["kpt"]
    token = kpt.settings.health_detail_token
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token.encode(), supplied.encode()):
        return jsonify(error="Not found.", code="not_found"), 404
    try:
        svc = kpt.chat_service()
    except Exception as e:  # noqa: BLE001
        log.exception("Chat service failed to start")
        return jsonify(status="error", code="service_unavailable", error=f"{type(e).__name__}: {e}"), 503
    return jsonify(status="ok", gemini=svc.gemini.enabled, models=svc.gemini.models, records=len(svc.store.df),
                   model=svc.store.bundle.model_name, data_files=svc.store.files)
