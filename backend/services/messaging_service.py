"""Buyer-seller private messaging (text only). No Flask imports; the API layer passes the authenticated user id.

Rules enforced here, on every call: the caller must be a participant (otherwise the same "not found" as a missing
id, so ids cannot be probed); the seller is always the listing's owner, never client supplied; banned/disabled or
blocked counterparts cannot be written to; bodies are length-limited plain text. Message bodies are never logged
and never sent to an AI provider.
"""
from __future__ import annotations

import re
import time
import uuid

from backend.db import Database
from backend.errors import ApiError

MAX_BODY = 2000
PAGE = 30
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ID = re.compile(r"^[0-9a-f]{32}$")
_REF = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _now_us() -> int:
    return time.time_ns() // 1000


def display_name(name: str | None) -> str:
    """First name + last initial: enough to recognise a person, not their full identity."""
    parts = (name or "").split()
    if not parts:
        return "Former user"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."


def _nf() -> ApiError:
    return ApiError("Conversation not found.", 404, "not_found")


class MessagingService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- listings ----------------------------------------------------------------------------------------
    def create_listing(self, seller_id: str, title: str, area: str, ref: str | None = None) -> dict:
        seller = self.db.one("SELECT status FROM users WHERE id = ?", (seller_id,))
        if not seller or seller["status"] != "active":
            raise ApiError("This account cannot create listings right now.", 403, "account_restricted")
        lid, now = uuid.uuid4().hex, int(time.time())
        ref = ref or f"u-{lid[:10]}"  # server-generated: users cannot squat the refs of demo properties
        self.db.execute("INSERT INTO listings (id, ref, seller_id, title, area, status, created_at) VALUES (?,?,?,?,?,?,?)",
                        (lid, ref, seller_id, title, area, "active", now))
        return {"id": lid, "ref": ref, "title": title, "area": area}

    # -- owner-only lifecycle (Session 15). Non-owners and unknown refs get the SAME 404 (no ref probing). ------------
    @staticmethod
    def _clean_text(value, field: str, lo: int, hi: int) -> str:
        if not isinstance(value, str):
            raise ApiError(f"'{field}' must be text.", 400, f"invalid_{field}")
        text = " ".join(_CONTROL.sub("", value).split())
        if not (lo <= len(text) <= hi):
            raise ApiError(f"'{field}' must be {lo} to {hi} characters.", 400, f"invalid_{field}")
        return text

    def _owned(self, seller_id: str, ref: str) -> dict:
        row = self.db.one("SELECT id, ref, title, area, status, seller_id FROM listings WHERE ref = ?", (ref,)) if _REF.match(ref or "") else None
        if not row or row["seller_id"] != seller_id:
            raise ApiError("Listing not found.", 404, "not_found")
        seller = self.db.one("SELECT status FROM users WHERE id = ?", (seller_id,))
        if not seller or seller["status"] != "active":
            raise ApiError("This account cannot change listings right now.", 403, "account_restricted")
        return row

    def update_listing(self, seller_id: str, ref: str, title, area) -> dict:
        """Owner edits ``title`` and ``area`` only. ref, id, seller_id and status are never touched here."""
        title, area = self._clean_text(title, "title", 3, 120), self._clean_text(area, "area", 2, 80)
        row = self._owned(seller_id, ref)
        self.db.execute("UPDATE listings SET title = ?, area = ? WHERE id = ? AND seller_id = ?", (title, area, row["id"], seller_id))
        return {"ref": row["ref"], "title": title, "area": area, "status": row["status"], "verified": False}

    def set_listing_status(self, seller_id: str, ref: str, status) -> dict:
        """Reversible close/reopen. Conversations, messages and reports are kept; closing only stops browse and new chats."""
        if status not in ("active", "closed"):
            raise ApiError("'status' must be 'active' or 'closed'.", 400, "invalid_status")
        row = self._owned(seller_id, ref)
        self.db.execute("UPDATE listings SET status = ? WHERE id = ? AND seller_id = ?", (status, row["id"], seller_id))
        return {"ref": row["ref"], "title": row["title"], "area": row["area"], "status": status, "verified": False}

    def list_active(self, page: int = 1, per_page: int = 20) -> dict:
        """Public browse: active listings whose seller is active. Never includes seller identity. Seller-submitted = unverified."""
        page, per_page = max(1, page), min(50, max(1, per_page))
        rows = self.db.all("SELECT l.ref, l.title, l.area, l.created_at FROM listings l JOIN users u ON u.id = l.seller_id "
                           "WHERE l.status = 'active' AND u.status = 'active' ORDER BY l.created_at DESC, l.ref DESC LIMIT ? OFFSET ?",
                           (per_page + 1, (page - 1) * per_page))
        return {"listings": [{**r, "verified": False} for r in rows[:per_page]], "page": page, "has_more": len(rows) > per_page}

    def list_mine(self, seller_id: str, page: int = 1, per_page: int = 20) -> dict:
        """The signed-in seller's own listings (any status), newest first, one bounded page at a time.
        Owner-only: the caller passes the session user id. ``page`` >= 1; ``per_page`` is clamped to 1..50."""
        per_page, page = max(1, min(int(per_page), 50)), max(1, int(page))
        rows = self.db.all("SELECT ref, title, area, status, created_at FROM listings WHERE seller_id = ? ORDER BY created_at DESC, ref DESC LIMIT ? OFFSET ?",
                           (seller_id, per_page, (page - 1) * per_page))
        total = self.db.one("SELECT COUNT(*) AS n FROM listings WHERE seller_id = ?", (seller_id,))["n"]
        return {"listings": [{**r, "verified": False} for r in rows], "total": total, "page": page, "per_page": per_page}

    def listing_by_ref(self, ref: str, viewer_id: str | None) -> dict:
        row = self.db.one("SELECT id, ref, title, area, status, seller_id FROM listings WHERE ref = ?", (ref,)) if _REF.match(ref) else None
        if not row:
            raise ApiError("Listing not found.", 404, "not_found")
        seller = self.db.one("SELECT status FROM users WHERE id = ?", (row["seller_id"],))
        return {"id": row["id"], "ref": row["ref"], "title": row["title"], "area": row["area"], "verified": False,
                "contactable": row["status"] == "active" and bool(seller) and seller["status"] == "active",
                "own": bool(viewer_id) and viewer_id == row["seller_id"]}

    # -- conversations -----------------------------------------------------------------------------------
    def open_conversation(self, buyer_id: str, listing_id: str) -> dict:
        row = self.db.one("SELECT id, seller_id, status FROM listings WHERE id = ?", (listing_id,)) if _ID.match(listing_id or "") else None
        seller = self.db.one("SELECT status FROM users WHERE id = ?", (row["seller_id"],)) if row else None
        if not row or row["status"] != "active" or not seller or seller["status"] != "active":
            raise ApiError("This listing is not available for messages.", 404, "listing_unavailable")
        if row["seller_id"] == buyer_id:
            raise ApiError("You cannot message yourself about your own listing.", 400, "own_listing")
        if self._blocked(buyer_id, row["seller_id"]):
            raise ApiError("You cannot message this seller.", 403, "blocked")
        now = int(time.time())
        existing = self.db.one("SELECT id FROM conversations WHERE listing_id = ? AND buyer_id = ?", (listing_id, buyer_id))
        if not existing:
            cid = uuid.uuid4().hex
            try:
                self.db.execute("INSERT INTO conversations (id, listing_id, buyer_id, seller_id, created_at, last_message_at) VALUES (?,?,?,?,?,?)",
                                (cid, listing_id, buyer_id, row["seller_id"], now, now))
            except Exception:  # noqa: BLE001 - lost a race on UNIQUE(listing_id, buyer_id): use the winner
                existing = self.db.one("SELECT id FROM conversations WHERE listing_id = ? AND buyer_id = ?", (listing_id, buyer_id))
                if not existing:
                    raise
                cid = existing["id"]
        else:
            cid = existing["id"]
        return self.summary(cid, buyer_id)

    def _conv(self, cid: str, user_id: str) -> dict:
        """The conversation, only if ``user_id`` is a participant. Anything else looks like a missing id."""
        row = self.db.one("SELECT * FROM conversations WHERE id = ?", (cid,)) if _ID.match(cid or "") else None
        if not row or user_id not in (row["buyer_id"], row["seller_id"]):
            raise _nf()
        return row

    def _blocked(self, a: str, b: str) -> bool:
        return bool(self.db.one("SELECT 1 AS x FROM user_blocks WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)", (a, b, b, a)))

    def summary(self, cid: str, user_id: str) -> dict:
        c = self._conv(cid, user_id)
        mine_read = c["buyer_read_ts"] if user_id == c["buyer_id"] else c["seller_read_ts"]
        other = c["seller_id"] if user_id == c["buyer_id"] else c["buyer_id"]
        listing = self.db.one("SELECT ref, title, area FROM listings WHERE id = ?", (c["listing_id"],)) or {}
        who = self.db.one("SELECT name, status FROM users WHERE id = ?", (other,))
        last = self.db.one("SELECT body, ts, sender_id FROM messages WHERE conversation_id = ? ORDER BY ts DESC, id DESC LIMIT 1", (cid,))
        unread = self.db.one("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ? AND sender_id <> ? AND ts > ?", (cid, user_id, mine_read))["n"]
        return {"id": cid, "listing": {"ref": listing.get("ref"), "title": listing.get("title"), "area": listing.get("area")},
                "counterpart": display_name(who["name"] if who else None), "role": "buyer" if user_id == c["buyer_id"] else "seller",
                "blocked_by_me": bool(self.db.one("SELECT 1 AS x FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?", (user_id, other))),
                "counterpart_available": bool(who) and who["status"] == "active" and not self._blocked(user_id, other),
                "last_message": {"preview": (last["body"][:80] if last else ""), "ts": last["ts"] if last else None, "mine": bool(last) and last["sender_id"] == user_id},
                "unread": unread, "last_message_at": c["last_message_at"]}

    def inbox(self, user_id: str, page: int = 1, per_page: int = 20) -> dict:
        rows = self.db.all("SELECT id FROM conversations WHERE buyer_id = ? OR seller_id = ? ORDER BY last_message_at DESC, id LIMIT ? OFFSET ?",
                           (user_id, user_id, per_page, (page - 1) * per_page))
        total = self.db.one("SELECT COUNT(*) AS n FROM conversations WHERE buyer_id = ? OR seller_id = ?", (user_id, user_id))["n"]
        return {"conversations": [self.summary(r["id"], user_id) for r in rows], "total": total, "page": page, "per_page": per_page}

    def unread_total(self, user_id: str) -> int:
        return self.db.one(
            "SELECT COUNT(*) AS n FROM messages m JOIN conversations c ON c.id = m.conversation_id WHERE m.sender_id <> ? AND "
            "((c.buyer_id = ? AND m.ts > c.buyer_read_ts) OR (c.seller_id = ? AND m.ts > c.seller_read_ts))", (user_id, user_id, user_id))["n"]

    # -- messages ----------------------------------------------------------------------------------------
    def history(self, cid: str, user_id: str, before: int | None = None, after: int | None = None, limit: int = PAGE) -> dict:
        """Oldest-first page. ``before`` pages backwards through history; ``after`` fetches only newer messages (polling)."""
        self._conv(cid, user_id)
        limit = min(100, max(1, limit))
        if after is not None:
            rows = self.db.all("SELECT id, sender_id, body, ts FROM messages WHERE conversation_id = ? AND ts > ? ORDER BY ts ASC, id ASC LIMIT ?", (cid, after, limit))
            more = False
        else:
            cond, params = ("AND ts < ?", (cid, before, limit + 1)) if before is not None else ("", (cid, limit + 1))
            rows = self.db.all(f"SELECT id, sender_id, body, ts FROM messages WHERE conversation_id = ? {cond} ORDER BY ts DESC, id DESC LIMIT ?", params)  # noqa: S608  # nosec B608 - cond is one of two fixed literals; values bound
            more = len(rows) > limit
            rows = list(reversed(rows[:limit]))
        return {"messages": [{"id": r["id"], "mine": r["sender_id"] == user_id, "body": r["body"], "ts": r["ts"]} for r in rows],
                "has_more": more, "conversation": self.summary(cid, user_id)}

    def send(self, cid: str, user_id: str, body: object, client_id: object = None) -> dict:
        c = self._conv(cid, user_id)
        text = _CONTROL.sub("", body).strip() if isinstance(body, str) else ""
        if not text:
            raise ApiError("Write a message first.", 400, "empty_message")
        if len(text) > MAX_BODY:
            raise ApiError(f"Messages can be up to {MAX_BODY} characters.", 400, "message_too_long")
        cid_client = client_id if isinstance(client_id, str) and _CLIENT_ID.match(client_id) else None
        other = c["seller_id"] if user_id == c["buyer_id"] else c["buyer_id"]
        who = self.db.one("SELECT status FROM users WHERE id = ?", (other,))
        listing = self.db.one("SELECT status FROM listings WHERE id = ?", (c["listing_id"],))
        if self._blocked(user_id, other):
            raise ApiError("You can no longer message this person.", 403, "blocked")
        if not who or who["status"] != "active" or not listing or listing["status"] != "active":
            raise ApiError("This conversation is no longer available for new messages.", 409, "conversation_closed")
        if cid_client:
            dup = self.db.one("SELECT id, ts FROM messages WHERE conversation_id = ? AND sender_id = ? AND client_id = ?", (cid, user_id, cid_client))
            if dup:
                return {"id": dup["id"], "ts": dup["ts"], "duplicate": True}
        mid, ts = uuid.uuid4().hex, _now_us()
        last = self.db.one("SELECT MAX(ts) AS t FROM messages WHERE conversation_id = ?", (cid,))["t"] or 0
        ts = max(ts, last + 1)  # strictly increasing per conversation: stable order and safe cursors
        self.db.execute("INSERT INTO messages (id, conversation_id, sender_id, body, ts, client_id) VALUES (?,?,?,?,?,?)", (mid, cid, user_id, text, ts, cid_client))
        mine = "buyer_read_ts" if user_id == c["buyer_id"] else "seller_read_ts"
        self.db.execute(f"UPDATE conversations SET last_message_at = ?, {mine} = ? WHERE id = ?", (int(time.time()), ts, cid))  # noqa: S608 - fixed column  # nosec B608 - mine is one of two fixed column names; values bound
        return {"id": mid, "ts": ts, "duplicate": False}

    def mark_read(self, cid: str, user_id: str) -> None:
        c = self._conv(cid, user_id)
        latest = self.db.one("SELECT MAX(ts) AS t FROM messages WHERE conversation_id = ?", (cid,))["t"] or 0
        col = "buyer_read_ts" if user_id == c["buyer_id"] else "seller_read_ts"
        self.db.execute(f"UPDATE conversations SET {col} = ? WHERE id = ? AND {col} < ?", (latest, cid, latest))  # noqa: S608 - fixed column  # nosec B608 - col is one of two fixed column names; values bound

    # -- safety ------------------------------------------------------------------------------------------
    def block(self, cid: str, user_id: str, blocked: bool = True) -> None:
        c = self._conv(cid, user_id)
        other = c["seller_id"] if user_id == c["buyer_id"] else c["buyer_id"]
        if blocked:
            if not self.db.one("SELECT 1 AS x FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?", (user_id, other)):
                self.db.execute("INSERT INTO user_blocks (blocker_id, blocked_id, created_at) VALUES (?,?,?)", (user_id, other, int(time.time())))
        else:
            self.db.execute("DELETE FROM user_blocks WHERE blocker_id = ? AND blocked_id = ?", (user_id, other))

    def report(self, cid: str, user_id: str, reason: object, message_id: object = None) -> str:
        self._conv(cid, user_id)
        if not isinstance(reason, str) or not (3 <= len(reason.strip()) <= 500):
            raise ApiError("Please describe the problem (3 to 500 characters).", 400, "reason_required")
        mid = None
        if message_id not in (None, ""):
            if not isinstance(message_id, str) or not _ID.match(message_id) or not self.db.one(
                    "SELECT 1 AS x FROM messages WHERE id = ? AND conversation_id = ?", (message_id, cid)):
                raise ApiError("That message is not part of this conversation.", 400, "invalid_message")
            mid = message_id
        rid = uuid.uuid4().hex
        self.db.execute("INSERT INTO message_reports (id, conversation_id, message_id, reporter_id, reason, created_at) VALUES (?,?,?,?,?,?)",
                        (rid, cid, mid, user_id, reason.strip(), int(time.time())))
        return rid

    # -- admin (reports only; never a browse-all-conversations capability) --------------------------------
    def reports(self, status: str = "open", page: int = 1, per_page: int = 25) -> dict:
        st = status if status in ("open", "resolved") else "open"
        rows = self.db.all("SELECT r.id, r.conversation_id, r.message_id, r.reason, r.created_at, r.status, COALESCE(u.name, 'Former user') AS reporter "
                           "FROM message_reports r LEFT JOIN users u ON u.id = r.reporter_id WHERE r.status = ? ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
                           (st, per_page, (page - 1) * per_page))
        return {"reports": rows, "total": self.db.one("SELECT COUNT(*) AS n FROM message_reports WHERE status = ?", (st,))["n"]}

    def report_thread(self, report_id: str, limit: int = 100) -> dict:
        r = self.db.one("SELECT conversation_id, message_id FROM message_reports WHERE id = ?", (report_id,)) if _ID.match(report_id or "") else None
        if not r:
            raise ApiError("Report not found.", 404, "not_found")
        c = self.db.one("SELECT buyer_id, seller_id FROM conversations WHERE id = ?", (r["conversation_id"],))
        if not c:
            raise ApiError("Conversation no longer exists.", 404, "not_found")
        name = lambda uid: display_name((self.db.one("SELECT name FROM users WHERE id = ?", (uid,)) or {}).get("name"))  # noqa: E731
        msgs = self.db.all("SELECT id, sender_id, body, ts FROM messages WHERE conversation_id = ? ORDER BY ts ASC, id ASC LIMIT ?", (r["conversation_id"], limit))
        return {"buyer": name(c["buyer_id"]), "seller": name(c["seller_id"]),
                "messages": [{"from": "buyer" if m["sender_id"] == c["buyer_id"] else "seller", "body": m["body"], "ts": m["ts"],
                              "reported": bool(r["message_id"]) and m["id"] == r["message_id"]} for m in msgs]}

    def resolve_report(self, report_id: str, admin_id: str, note: str) -> None:
        n = self.db.execute("UPDATE message_reports SET status = 'resolved', reviewed_by = ?, reviewed_at = ?, review_note = ? WHERE id = ? AND status = 'open'",
                            (admin_id, int(time.time()), note, report_id)) if _ID.match(report_id or "") else 0
        if not n:
            raise ApiError("Open report not found.", 404, "not_found")
