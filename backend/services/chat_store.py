"""Database persistence for chat conversations that are tied to the ``__Host-kpt_chat`` cookie.

Serverless functions run as several instances with no shared memory, so the in-process conversation
cache alone cannot survive a refresh. Only the *cookie's random id* identifies a row (stored as a SHA-256
hash) and only the already-sanitised history ``{role, text}`` and the memory dict (known area / type
names and numbers) are stored. Rows older than the cookie lifetime are ignored and deleted. No Flask imports.
"""
from __future__ import annotations

import hashlib
import json
import time

from backend.db import Database


def _key(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


class DbChatStore:
    def __init__(self, db: Database, ttl_s: int) -> None:
        self.db, self.ttl_s = db, ttl_s

    def load(self, sid: str) -> dict | None:
        row = self.db.one("SELECT history, memory, updated_at FROM chat_sessions WHERE sid_hash = ?", (_key(sid),))
        if not row:
            return None
        if int(time.time()) - row["updated_at"] > self.ttl_s:
            self.delete(sid)
            return None
        try:
            return {"history": json.loads(row["history"]), "memory": json.loads(row["memory"])}
        except ValueError:
            return None

    def save(self, sid: str, history: list[dict], memory: dict) -> None:
        h, m, now = json.dumps(history, ensure_ascii=False), json.dumps(memory), int(time.time())
        if self.db.execute("UPDATE chat_sessions SET history = ?, memory = ?, updated_at = ? WHERE sid_hash = ?", (h, m, now, _key(sid))) == 0:
            self.db.execute("INSERT INTO chat_sessions (sid_hash, history, memory, updated_at) VALUES (?,?,?,?)", (_key(sid), h, m, now))

    def delete(self, sid: str) -> None:
        self.db.execute("DELETE FROM chat_sessions WHERE sid_hash = ?", (_key(sid),))
