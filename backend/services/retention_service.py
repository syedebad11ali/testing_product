"""Retention for private messages and resolved reports.

DISABLED unless ``MESSAGE_RETENTION_DAYS`` > 0: no legal retention period has been specified, so the owner must
choose one (see docs/MESSAGING.md). Rules, in order (each step is independent, bounded and safe to interrupt):
1. resolved reports older than ``REPORT_RETENTION_DAYS`` (by review time) are deleted;
2. messages older than ``MESSAGE_RETENTION_DAYS`` are deleted, EXCEPT messages in a conversation with an OPEN report
   and messages still referenced by any remaining report;
3. conversations left with no messages and no reports are deleted.
Never touches users; banning a user never makes their evidence eligible. Only counts are returned/logged, never bodies.
Plain parameterised SQL that runs on SQLite and PostgreSQL (``NOT EXISTS``, ``IN`` lists, ``LIMIT``).
"""
from __future__ import annotations

import logging
import time

from backend.db import Database

log = logging.getLogger("kpt.retention")
_US = 1_000_000


# The only tables retention may delete from.
_DELETABLE_TABLES = frozenset({"message_reports", "messages", "conversations"})


class RetentionService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def run(self, message_days: int, report_days: int, batch: int = 1000, apply: bool = False, now: int | None = None) -> dict:
        """Returns counts. With ``apply=False`` (dry run) nothing is deleted. ``batch`` caps rows removed per step per run."""
        now = int(now if now is not None else time.time())
        out = {"applied": apply, "enabled": message_days > 0, "reports": 0, "messages": 0, "conversations": 0}
        if message_days <= 0:
            return out
        batch = min(10_000, max(1, batch))
        report_cut = now - max(report_days, message_days) * 86400
        msg_cut_us = (now - message_days * 86400) * _US

        rep_ids = [r["id"] for r in self.db.all("SELECT id FROM message_reports WHERE status = 'resolved' AND COALESCE(reviewed_at, created_at) < ? LIMIT ?", (report_cut, batch))]
        out["reports"] = len(rep_ids)
        if apply and rep_ids:
            self._delete("message_reports", rep_ids)

        msg_ids = [r["id"] for r in self.db.all(
            "SELECT m.id FROM messages m WHERE m.ts < ? "
            "AND NOT EXISTS (SELECT 1 FROM message_reports r WHERE r.conversation_id = m.conversation_id AND r.status = 'open') "
            "AND NOT EXISTS (SELECT 1 FROM message_reports r WHERE r.message_id = m.id) LIMIT ?", (msg_cut_us, batch))]
        out["messages"] = len(msg_ids)
        if apply and msg_ids:
            self._delete("messages", msg_ids)

        conv_ids = [r["id"] for r in self.db.all(
            "SELECT c.id FROM conversations c WHERE c.created_at < ? "
            "AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id) "
            "AND NOT EXISTS (SELECT 1 FROM message_reports r WHERE r.conversation_id = c.id) LIMIT ?", (now - message_days * 86400, batch))]
        out["conversations"] = len(conv_ids)
        if apply and conv_ids:
            self._delete("conversations", conv_ids)
        log.info("retention run applied=%s reports=%d messages=%d conversations=%d", apply, out["reports"], out["messages"], out["conversations"])
        return out

    def _delete(self, table: str, ids: list[str]) -> None:
        if table not in _DELETABLE_TABLES:   # identifiers cannot be bound as parameters: whitelist them
            raise ValueError(f"retention may not delete from {table!r}")
        for i in range(0, len(ids), 200):  # small IN lists: portable, and an interrupted run just leaves the rest for next time
            chunk = ids[i:i + 200]
            self.db.execute(f"DELETE FROM {table} WHERE id IN ({','.join('?' * len(chunk))})", tuple(chunk))  # noqa: S608 - table is a fixed literal above  # nosec B608 - table is checked against _DELETABLE_TABLES above; ids bound
