"""GET /health (public, minimal) and GET /health/detail (admin-session diagnostics)."""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify

from backend.errors import ApiError
from backend.security.guards import current_session

bp = Blueprint("health", __name__)
log = logging.getLogger("chatbot")


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/health/detail")
def health_detail():
    """Real startup errors and data counts. Admin session only; everyone else gets the same 404 as a missing route."""
    kpt = current_app.extensions["kpt"]
    try:
        sess = current_session()
    except ApiError:
        sess = None
    if not sess or sess["role"] != "admin":
        return jsonify(error="Not found.", code="not_found"), 404
    try:
        svc = kpt.chat_service()
    except Exception as e:  # noqa: BLE001
        log.exception("Chat service failed to start")
        return jsonify(status="error", code="service_unavailable", error=f"{type(e).__name__}: {e}"), 503
    return jsonify(status="ok", gemini=svc.gemini.enabled, models=svc.gemini.models, records=len(svc.store.df),
                   model=svc.store.bundle.model_name, data_files=svc.store.files, agents=svc.agents.status(), gemini_status=svc.gemini.status())
