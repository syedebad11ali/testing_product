"""GET /health — deployment check; surfaces the real startup error if the service cannot build."""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify

bp = Blueprint("health", __name__)
log = logging.getLogger("chatbot")


@bp.get("/health")
def health():
    try:
        svc = current_app.extensions["kpt"].chat_service()
    except Exception as e:  # report the real startup failure (e.g. model load) in the body + logs
        log.exception("Chat service failed to start")
        return jsonify(status="error", code="service_unavailable", error=f"{type(e).__name__}: {e}"), 503
    return jsonify(status="ok", gemini=svc.gemini.enabled, models=svc.gemini.models,
                   records=len(svc.store.df), model=svc.store.bundle.model_name,
                   data_files=svc.store.files)
