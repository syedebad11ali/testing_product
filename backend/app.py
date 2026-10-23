"""Application factory.

* Local:   ``python -m backend.app``  (serves the site + API on http://localhost:5000)
* Vercel:  entrypoint ``backend.app:app`` (see pyproject.toml)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from dotenv import load_dotenv
from flask import Flask

from backend.api import register_api
from backend.config import ROOT_DIR, Settings
from backend.errors import register_error_handlers
from backend.middleware import RateLimiter, register_cors
from backend.web import register_web


@dataclass
class Container:
    """Holds app-wide singletons. The chat service is built lazily (first request / health
    check) so importing the app never touches the model, the CSVs or Gemini."""

    settings: Settings
    rate_limiter: RateLimiter
    _service: object = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def chat_service(self):
        if self._service is None:
            with self._lock:
                if self._service is None:
                    from backend.services.chat_service import ChatService
                    self._service = ChatService(self.settings)
        return self._service


def create_app(settings: Settings | None = None) -> Flask:
    # Local development only: ./.env. On Vercel the variables come from Project Settings.
    load_dotenv(ROOT_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    settings = settings or Settings.from_env()

    app = Flask(__name__, static_folder=None)
    app.extensions["kpt"] = Container(settings, RateLimiter(settings.rate_limit_per_min))
    register_error_handlers(app)
    register_cors(app, settings)
    register_api(app)
    register_web(app, settings)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.extensions["kpt"].settings.port, debug=False)
