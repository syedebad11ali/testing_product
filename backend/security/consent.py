"""Cookie consent as the server sees it.

The browser banner writes the ``kpt_consent`` cookie (JS-readable, 12 months) as
``v=<policy version>&p=<0|1>&a=<0|1>`` (p = Preferences, a = Analytics). Essential cookies (session,
CSRF, the consent record itself) never need consent. Anything else is only *set by the server* when this
module says the category is allowed. A missing, malformed or out-of-date (older policy version) record
means "no choice yet" = nothing optional. No Flask imports besides the request type.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

from flask import Request

CONSENT_COOKIE = "kpt_consent"
COOKIE_POLICY_VERSION = 1  # bump when the cookie table changes; visitors are asked again
CATEGORIES = {"preferences": "p", "analytics": "a"}
_RECORD = re.compile(r"v=(\d{1,4})&p=([01])&a=([01])")


def parse(raw: str) -> dict | None:
    """``{"version", "preferences", "analytics"}`` for a valid, current record, else ``None``."""
    m = _RECORD.fullmatch(unquote(raw or "")[:40])
    if not m or int(m.group(1)) != COOKIE_POLICY_VERSION:
        return None
    return {"version": int(m.group(1)), "preferences": m.group(2) == "1", "analytics": m.group(3) == "1"}


def allows(request: Request, category: str) -> bool:
    """True only if the visitor has made a current choice that includes ``category``."""
    record = parse(request.cookies.get(CONSENT_COOKIE, ""))
    return bool(record and record.get(category))
