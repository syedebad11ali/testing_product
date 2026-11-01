"""Outgoing email. No Flask imports, no third-party packages (stdlib ``urllib`` only).

Provider: Resend (https://resend.com) over its HTTPS API. Enabled when ``RESEND_API_KEY`` and ``MAIL_FROM`` are set.
TODO(you): create a Resend account, verify a sending domain, set RESEND_API_KEY, MAIL_FROM and APP_BASE_URL.
To use another provider, implement ``send(to, subject, text)`` and pass it to ``PasswordResetService``.
Not exercised against the live API in the sandbox (no network): tests use a fake sender.
"""
from __future__ import annotations

import json
import logging
import urllib.request

from backend.config import Settings

log = logging.getLogger("kpt.mail")


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @property
    def enabled(self) -> bool:
        return bool(self.s.resend_api_key and self.s.mail_from)

    def send(self, to: str, subject: str, text: str) -> bool:
        """Returns True if the provider accepted the message. Never raises, never logs the body."""
        if not self.enabled:
            return False
        req = urllib.request.Request(  # noqa: S310 - fixed https URL
            "https://api.resend.com/emails",
            data=json.dumps({"from": self.s.mail_from, "to": [to], "subject": subject, "text": text}).encode(),
            headers={"Authorization": f"Bearer {self.s.resend_api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            # the URL is the fixed https://api.resend.com literal above
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310  # nosec B310
                return 200 <= resp.status < 300
        except Exception as exc:  # noqa: BLE001
            log.error("mail send failed: %s", type(exc).__name__)
            return False
