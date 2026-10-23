"""Uniform JSON error responses.

Every API error has the shape ``{"error": "<human message>", "code": "<machine_code>"}``.
Unexpected exceptions are logged with a short ``error_id`` and returned as a generic
message, so internal details (paths, library errors) never leak to the browser.
"""
from __future__ import annotations

import logging
import uuid

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

log = logging.getLogger("chatbot")


class ApiError(Exception):
    """Raise from a route/service to return a clean JSON error."""

    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def _payload(message: str, code: str, **extra):
    return {"error": message, "code": code, **extra}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return jsonify(_payload(e.message, e.code)), e.status

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        # API paths always get JSON; HTML pages keep Flask's default response.
        from flask import request
        if request.path.startswith("/api/"):
            return jsonify(_payload(e.description or e.name, e.name.lower().replace(" ", "_"))), e.code
        return e

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        error_id = uuid.uuid4().hex[:8]
        log.exception("Unhandled error [%s]", error_id)
        return jsonify(_payload("Something went wrong on our side. Please try again.",
                                "internal_error", error_id=error_id)), 500
