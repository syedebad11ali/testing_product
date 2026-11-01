"""Listings + private buyer-seller messages (v1 only). Everything needs a signed-in, non-banned user (the session guard
already rejects banned accounts). The sender is always the session user. Responses are no-store (all /api/ paths).
See docs/MESSAGING.md."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.api.auth import _body, _str
from backend.errors import ApiError
from backend.security.guards import current_session, login_required

bp = Blueprint("messages", __name__)
V1_ONLY = True


def _kpt():
    return current_app.extensions["kpt"]


def _limit(sess: dict, cost_key: str = "w") -> None:
    lim = _kpt().message_limiter()
    lim.check(f"{cost_key}:u:{sess['user_id']}")
    lim.check(f"{cost_key}:ip:{request.remote_addr or 'unknown'}")


def _int_arg(name: str) -> int | None:
    value = request.args.get(name, type=int)
    return value if value is not None and value >= 0 else None


@bp.get("/listings/by-ref/<ref>")
def listing_by_ref(ref: str):
    """Public-safe summary used to decide whether to show 'Chat with seller'. Never includes the seller."""
    sess = current_session()
    return jsonify(listing=_kpt().messaging().listing_by_ref(ref, sess["user_id"] if sess and sess["role"] != "guest" else None))


@bp.get("/listings")
def browse_listings():
    """Public, paginated summaries of active seller-created listings (no seller identity, labelled unverified)."""
    _kpt().message_limiter().check(f"browse:ip:{request.remote_addr or 'unknown'}")
    return jsonify(_kpt().messaging().list_active(request.args.get("page", 1, type=int) or 1))


@bp.get("/listings/mine")
@login_required()
def my_listings():
    page, per = request.args.get("page", 1, type=int), request.args.get("per_page", 20, type=int)
    return jsonify(**_kpt().messaging().list_mine(current_session()["user_id"], page or 1, per or 20))


@bp.post("/listings")
@login_required()
def create_listing():
    sess, data = current_session(), _body()
    _limit(sess, "listing")
    return jsonify(listing=_kpt().messaging().create_listing(sess["user_id"], _str(data, "title", 120), _str(data, "area", 80))), 201


@bp.post("/listings/<ref>/edit")
@login_required()
def edit_listing(ref: str):
    """Owner-only: change title/area. Anything else in the body (ref, seller_id, status, verified) is ignored."""
    sess, data = current_session(), _body()
    _limit(sess, "listing")
    return jsonify(listing=_kpt().messaging().update_listing(sess["user_id"], ref, data.get("title"), data.get("area")))


@bp.post("/listings/<ref>/status")
@login_required()
def listing_status(ref: str):
    """Owner-only, reversible: status 'active' (reopen) or 'closed'. There is deliberately no delete endpoint."""
    sess, data = current_session(), _body()
    _limit(sess, "listing")
    return jsonify(listing=_kpt().messaging().set_listing_status(sess["user_id"], ref, data.get("status")))


@bp.post("/messages/conversations")
@login_required()
def open_conversation():
    sess, data = current_session(), _body()
    _limit(sess, "open")
    return jsonify(conversation=_kpt().messaging().open_conversation(sess["user_id"], str(data.get("listing_id", "")))), 200


@bp.get("/messages/conversations")
@login_required()
def inbox():
    sess = current_session()
    page = max(1, request.args.get("page", 1, type=int))
    return jsonify(**_kpt().messaging().inbox(sess["user_id"], page, min(50, max(1, request.args.get("per_page", 20, type=int)))))


@bp.get("/messages/unread-count")
@login_required()
def unread_count():
    return jsonify(unread=_kpt().messaging().unread_total(current_session()["user_id"]))


@bp.get("/messages/conversations/<cid>")
@login_required()
def history(cid: str):
    return jsonify(**_kpt().messaging().history(cid, current_session()["user_id"], before=_int_arg("before"), after=_int_arg("after"),
                                                limit=request.args.get("limit", 30, type=int)))


@bp.post("/messages/conversations/<cid>/messages")
@login_required()
def send(cid: str):
    sess, data = current_session(), _body()
    _limit(sess)
    return jsonify(**_kpt().messaging().send(cid, sess["user_id"], data.get("body"), data.get("client_id"))), 201


@bp.post("/messages/conversations/<cid>/read")
@login_required()
def mark_read(cid: str):
    _kpt().messaging().mark_read(cid, current_session()["user_id"])
    return jsonify(ok=True)


@bp.post("/messages/conversations/<cid>/report")
@login_required()
def report(cid: str):
    sess, data = current_session(), _body()
    _limit(sess, "report")
    rid = _kpt().messaging().report(cid, sess["user_id"], data.get("reason"), data.get("message_id"))
    _kpt().audit().admin_action(sess["user_id"], "message_reported", cid, _kpt().audit().ip_hash(request.remote_addr), "report filed")
    return jsonify(ok=True, report_id=rid), 201


@bp.post("/messages/conversations/<cid>/block")
@login_required()
def block(cid: str):
    _kpt().messaging().block(cid, current_session()["user_id"], True)
    return jsonify(ok=True)


@bp.post("/messages/conversations/<cid>/unblock")
@login_required()
def unblock(cid: str):
    _kpt().messaging().block(cid, current_session()["user_id"], False)
    return jsonify(ok=True)
