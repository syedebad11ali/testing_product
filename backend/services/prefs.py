"""Preference values: one validator for everything that arrives from a cookie or the account API.

Cookie content is untrusted input. ``sanitize`` keeps only known keys, clamps lengths and numbers,
and accepts short codes / IDs only (no names, emails, phone numbers, tokens or free text). The
browser-side twin is ``frontend/js/core/prefs.js``; both must accept and reject the same shapes
(``tests/backend/test_cookies.py`` and ``tests/frontend/cookies.test.js`` share the cases). No Flask imports.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.db import Database

THEMES = {"light", "dark"}
LANGS = {"en", "ur", "ro"}  # English, Urdu, Roman Urdu
SORTS = {"relevance", "price_asc", "price_desc", "newest", "area"}
HINTS = {"intro", "promo", "chat_nudge", "verify_tip", "demo_notice"}
_TOKEN = re.compile(r"[a-z0-9][a-z0-9 _.-]{0,39}")      # filter codes such as "gulshan e iqbal", "house"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")      # property ids such as DEMO-KPT-8103
LIST_LIMITS = {"recent": 20, "compare": 4, "saved": 30, "dismissed": 10}
MAX_PRICE = 10_000_000_000
MAX_JSON_BYTES = 3000  # well under the 4 KB cookie limit once URL-encoded


def _ids(value: Any, limit: int) -> list[str]:
    out: list[str] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str) and _ID.fullmatch(item) and item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _money(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return int(min(max(value, 0), MAX_PRICE))


def sanitize(raw: Any) -> dict:
    """Return only valid, clamped preference values from ``raw`` (anything else is dropped)."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    if raw.get("theme") in THEMES: out["theme"] = raw["theme"]
    if raw.get("lang") in LANGS: out["lang"] = raw["lang"]
    if raw.get("sort") in SORTS: out["sort"] = raw["sort"]
    for key in ("area", "ptype"):
        value = raw.get(key)
        if isinstance(value, str) and _TOKEN.fullmatch(value.strip().lower()):
            out[key] = value.strip().lower()
    for key in ("min_price", "max_price"):
        number = _money(raw.get(key))
        if number is not None: out[key] = number
    for key, limit in LIST_LIMITS.items():
        items = _ids(raw.get(key), limit)
        if key == "dismissed": items = [i for i in items if i in HINTS]
        if items: out[key] = items
    while len(json.dumps(out, separators=(",", ":"))) > MAX_JSON_BYTES and out.get("saved"):
        out["saved"].pop()
    return out


def merge(account: dict, cookie: dict) -> dict:
    """Combine account and cookie prefs on login: cookie scalars win (most recent device choice),
    lists are unioned with cookie items first, then re-clamped by ``sanitize``."""
    a, c = sanitize(account), sanitize(cookie)
    merged = {**a, **c}
    for key in LIST_LIMITS:
        merged_list = list(dict.fromkeys([*c.get(key, []), *a.get(key, [])]))
        if merged_list: merged[key] = merged_list
    return sanitize(merged)


class PrefsService:
    """Per-account copy of the preferences so they follow a user across devices."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, user_id: str) -> dict:
        row = self.db.one("SELECT prefs FROM user_prefs WHERE user_id = ?", (user_id,))
        try:
            return sanitize(json.loads(row["prefs"])) if row else {}
        except ValueError:
            return {}

    def set(self, user_id: str, prefs: Any) -> dict:
        clean, now = sanitize(prefs), int(time.time())
        text = json.dumps(clean, separators=(",", ":"))
        if self.db.execute("UPDATE user_prefs SET prefs = ?, updated_at = ? WHERE user_id = ?", (text, now, user_id)) == 0:
            self.db.execute("INSERT INTO user_prefs (user_id, prefs, updated_at) VALUES (?,?,?)", (user_id, text, now))
        return clean
