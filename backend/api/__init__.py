"""HTTP API.

Routes live in one module per resource (``chat.py``, ``health.py``). Each exposes a
``bp`` blueprint. ``register_api`` mounts them under the canonical versioned prefix
``/api/v1`` and under the legacy ``/api`` prefix, which existing embeds and the
frontend still call (``POST /api/chat``, ``GET /api/health``).

To add an endpoint: create ``backend/api/<resource>.py`` with a ``bp``, add it to
``RESOURCES`` below, and put the logic in ``backend/services/`` — routes stay thin.
"""
from flask import Flask

from backend.api import account, admin, admin_totp, auth, chat, health, messages, verification

RESOURCES = (chat, health, verification, auth, account, admin, admin_totp, messages)


def register_api(app: Flask) -> None:
    for module in RESOURCES:
        app.register_blueprint(module.bp, url_prefix="/api/v1", name=f"v1_{module.bp.name}")
        if not getattr(module, "V1_ONLY", False):  # auth/admin never get a legacy alias
            app.register_blueprint(module.bp, url_prefix="/api", name=f"legacy_{module.bp.name}")
