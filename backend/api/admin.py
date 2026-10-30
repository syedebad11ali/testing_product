"""Admin API (v1 only). Every route requires the ``admin`` role, decided from the server-side session.

Sensitive actions (disable/enable, role change) also re-ask for the admin's password and are audit
logged. Responses are ``no-store`` (security/headers.py). TOTP and CSV export are still TODO (HANDOFF.md).
"""
from __future__ import annotations

import re

from flask import Blueprint, Response, current_app, jsonify, request

from backend.api.auth import _body, _str
from backend.errors import ApiError
from backend.security import passwords
from backend.security.guards import current_session, role_required
from backend.services.auth_service import ADMIN_USERNAME
from backend.services.moderation_service import resolve_status

bp = Blueprint("admin", __name__)
V1_ONLY = True
ID_RE = re.compile(r"^[0-9a-f]{32}$")
ROLES = ("user", "admin")


def _kpt():
    return current_app.extensions["kpt"]


def _target(user_id: str) -> dict:
    if not ID_RE.match(user_id):
        raise ApiError("User not found.", 404, "not_found")
    row = _kpt().database().one("SELECT id, name, role, status FROM users WHERE id = ?", (user_id,))
    if not row or row["role"] == "guest":  # guest rows are temporary and not managed from the admin UI
        raise ApiError("User not found.", 404, "not_found")
    return row


def _protect(target: dict, action: str) -> None:
    """The bootstrap admin can never be disabled, banned or demoted; admins must be demoted before they can be banned;
    the last active admin cannot be removed."""
    row = _kpt().database().one("SELECT username FROM users WHERE id = ?", (target["id"],))
    if row and row["username"] == ADMIN_USERNAME:
        raise ApiError("This protected account cannot be changed this way.", 403, "protected_account")
    if target["role"] == "admin":
        if action == "ban":
            raise ApiError("Remove the admin role before banning this account.", 403, "protected_account")
        n = _kpt().database().one("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND status = 'active'")["n"]
        if n <= 1:
            raise ApiError("This is the last active admin.", 403, "last_admin")


def _reason(data: dict) -> str:
    reason = data.get("reason")
    if not isinstance(reason, str) or not (3 <= len(reason.strip()) <= 300):
        raise ApiError("A reason (3 to 300 characters) is required.", 400, "reason_required")
    return reason.strip()


def _reauth(data: dict) -> None:
    sess = current_session()
    row = _kpt().database().one("SELECT password_hash FROM users WHERE id = ?", (sess["user_id"],))
    if not passwords.verify_password(_str(data, "password", 1024, strip=False), row["password_hash"] if row else None):
        raise ApiError("Password confirmation failed.", 403, "reauth_failed")


def _need_stepup(action_class: str, data: dict) -> None:
    """Second factor for sensitive actions. With TOTP active the request must carry a valid, unused step-up proof (``stepup``)
    issued to THIS session for THIS action class. Admins without TOTP keep the password-only flow unless
    ``ADMIN_TOTP_REQUIRED`` is on, in which case they must enrol first."""
    kpt, sess = _kpt(), current_session()
    if kpt.totp().status(sess["user_id"]) == "active":
        kpt.totp().consume_proof(sess["user_id"], sess["id_hash"], action_class, data.get("stepup"))
    elif kpt.settings.admin_totp_required:
        raise ApiError("Set up two-factor authentication first (Security panel).", 403, "totp_enrollment_required")


def _audit(action: str, target: str, detail: str = "") -> None:
    k = _kpt()
    k.audit().admin_action(current_session()["user_id"], action, target, k.audit().ip_hash(request.remote_addr), detail)


SORTS = {"created": "created_at", "last_login": "COALESCE(last_login_at, 0)", "name": "LOWER(name)", "role": "role", "status": "status"}
CSV_COLUMNS = {"users": ("id", "name", "login", "method", "role", "status", "created_at", "last_login_at"),
               "login-events": ("ts", "identifier", "method", "success", "reason", "ip_hash")}


def _page() -> tuple[int, int]:
    return max(1, request.args.get("page", 1, type=int)), min(100, max(1, request.args.get("per_page", 25, type=int)))


def _user_filter() -> tuple[str, list]:
    q = f"%{request.args.get('q', '').strip().lower()[:60]}%"
    where, params = ["role <> 'guest'", "(LOWER(name) LIKE ? OR LOWER(COALESCE(email, username)) LIKE ?)"], [q, q]
    for key, allowed in (("status", ("active", "disabled", "banned")), ("role", ROLES)):
        if request.args.get(key) in allowed:
            where.append(f"{key} = ?")
            params.append(request.args[key])
    return " AND ".join(where), params


@bp.get("/admin/users")
@role_required("admin")
def users():
    db, kpt = _kpt().database(), _kpt()
    page, per = _page()
    where, params = _user_filter()
    order = SORTS.get(request.args.get("sort", "created"), "created_at") + (" ASC" if request.args.get("dir") == "asc" else " DESC")
    rows = db.all(f"SELECT id, name, COALESCE(email, username) AS login, method, role, status, created_at, last_login_at FROM users "  # noqa: S608 - order/where are whitelisted  # nosec B608 - where is built only from fixed fragments with ? placeholders, order from the SORTS whitelist; values bound
                  f"WHERE {where} ORDER BY {order}, id LIMIT ? OFFSET ?", (*params, per, (page - 1) * per))
    for row in rows:
        if row["status"] == "banned":
            row["status"] = resolve_status(db, row["id"], "banned")
            row["ban"] = kpt.moderation().current(row["id"]) if row["status"] == "banned" else None
    total = db.one(f"SELECT COUNT(*) AS n FROM users WHERE {where}", params)["n"]  # noqa: S608  # nosec B608 - where is built only from fixed fragments with ? placeholders, order from the SORTS whitelist; values bound
    return jsonify(users=rows, total=total, page=page, per_page=per)


def _event_filter() -> tuple[str, list]:
    where, params = ["1=1"], []
    q = request.args.get("q", "").strip().lower()[:60]
    if q:
        where.append("LOWER(COALESCE(identifier, '')) LIKE ?")
        params.append(f"%{q}%")
    if request.args.get("outcome") in ("success", "failure"):
        where.append("success = ?")
        params.append(1 if request.args["outcome"] == "success" else 0)
    if request.args.get("method") in ("password", "google", "remember"):
        where.append("method = ?")
        params.append(request.args["method"])
    return " AND ".join(where), params


@bp.get("/admin/login-events")
@role_required("admin")
def login_events():
    """Newest first. Shows the hashed IP only (never the raw address, never the user-agent string)."""
    page, per = _page()
    where, params = _event_filter()
    db = _kpt().database()
    events = db.all(f"SELECT ts, identifier, method, success, reason, ip_hash FROM login_events WHERE {where} "  # noqa: S608  # nosec B608 - where is built only from fixed fragments with ? placeholders, order from the SORTS whitelist; values bound
                    "ORDER BY ts DESC, id LIMIT ? OFFSET ?", (*params, per, (page - 1) * per))
    total = db.one(f"SELECT COUNT(*) AS n FROM login_events WHERE {where}", params)["n"]  # noqa: S608  # nosec B608 - where is built only from fixed fragments with ? placeholders, order from the SORTS whitelist; values bound
    return jsonify(events=events, total=total, page=page, per_page=per)


@bp.get("/admin/audit")
@role_required("admin")
def audit_log():
    page, per = _page()
    db = _kpt().database()
    rows = db.all("SELECT a.ts, COALESCE(u.name, a.actor_id) AS actor, a.action, a.target, a.detail FROM audit_log a "
                  "LEFT JOIN users u ON u.id = a.actor_id ORDER BY a.ts DESC, a.id LIMIT ? OFFSET ?", (per, (page - 1) * per))
    return jsonify(entries=rows, total=db.one("SELECT COUNT(*) AS n FROM audit_log")["n"], page=page, per_page=per)


def _csv_cell(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text  # spreadsheet formula injection guard


@bp.get("/admin/export/<kind>.csv")
@role_required("admin")
def export_csv_get(kind: str):
    """Plain download link. Refused once the admin has two-factor on (or it is enforced): use the POST variant with a step-up proof."""
    if kind not in CSV_COLUMNS:
        raise ApiError("Not found.", 404, "not_found")
    if _kpt().totp().status(current_session()["user_id"]) == "active" or _kpt().settings.admin_totp_required:
        raise ApiError("Two-factor confirmation is required for this export.", 403, "stepup_required")
    return _export(kind)


@bp.post("/admin/export/<kind>.csv")
@role_required("admin")
def export_csv_post(kind: str):
    if kind not in CSV_COLUMNS:
        raise ApiError("Not found.", 404, "not_found")
    _need_stepup("csv_export", _body())
    return _export(kind)


def _export(kind: str):
    """Admin-only CSV of users or login events (hashed IPs only, no password or token fields). Every export is audited."""
    import csv
    import io
    db = _kpt().database()
    if kind == "users":
        rows = db.all("SELECT id, name, COALESCE(email, username) AS login, method, role, status, created_at, last_login_at FROM users WHERE role <> 'guest' ORDER BY created_at DESC LIMIT 10000")
    else:
        rows = db.all("SELECT ts, identifier, method, success, reason, ip_hash FROM login_events ORDER BY ts DESC LIMIT 10000")
    _audit("csv_export", kind, f"rows={len(rows)}")  # audit before the data leaves
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS[kind])
    for row in rows:
        writer.writerow([_csv_cell(row[c]) for c in CSV_COLUMNS[kind]])
    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="kpt-{kind}.csv"'
    return resp


@bp.get("/admin/sessions")
@role_required("admin")
def sessions():
    return jsonify(sessions=_kpt().sessions().active_for_admin())


@bp.post("/admin/users/<user_id>/status")
@role_required("admin")
def set_status(user_id: str):
    data, target = _body(), _target(user_id)
    status = data.get("status")
    if status not in ("active", "disabled"):
        raise ApiError("status must be 'active' or 'disabled'.", 400, "invalid_status")
    if target["id"] == current_session()["user_id"]:
        raise ApiError("You cannot change your own status.", 400, "self_action")
    if target["status"] == "banned":
        raise ApiError("This account is banned. Use Reinstate instead.", 409, "banned")
    if status == "disabled":
        _protect(target, "disable")
    _reauth(data)
    _need_stepup("moderation", data)
    _kpt().database().execute("UPDATE users SET status = ? WHERE id = ?", (status, target["id"]))
    if status == "disabled":
        _kpt().sessions().revoke_user(target["id"])
    _audit(f"user_{status}", target["id"], str(data.get("reason", ""))[:150])
    return jsonify(ok=True)


@bp.post("/admin/users/<user_id>/role")
@role_required("admin")
def set_role(user_id: str):
    data, target = _body(), _target(user_id)
    role = data.get("role")
    if role not in ROLES:
        raise ApiError("role must be 'user' or 'admin'.", 400, "invalid_role")
    if target["id"] == current_session()["user_id"]:
        raise ApiError("You cannot change your own role.", 400, "self_action")
    if role != target["role"]:
        _protect(target, "role")
    _reauth(data)
    _need_stepup("role_change", data)
    _kpt().database().execute("UPDATE users SET role = ? WHERE id = ?", (role, target["id"]))
    if role != "admin":
        _kpt().totp().disable(target["id"])  # a demoted admin keeps no second-factor secret
    _kpt().sessions().revoke_user(target["id"])  # privilege change => old sessions must not survive
    _audit("role_changed", target["id"], f"{target['role']}->{role}")
    return jsonify(ok=True)


@bp.post("/admin/users/<user_id>/logout")
@role_required("admin")
def force_logout(user_id: str):
    target = _target(user_id)
    n = _kpt().sessions().revoke_user(target["id"])
    _audit("force_logout", target["id"], f"sessions={n}")
    return jsonify(ok=True, revoked=n)


@bp.post("/admin/users/<user_id>/ban")
@role_required("admin")
def ban_user(user_id: str):
    """Temporary suspension (``days``) or permanent ban. Needs a reason and the admin's password; revokes sessions at once."""
    data, target = _body(), _target(user_id)
    if target["id"] == current_session()["user_id"]:
        raise ApiError("You cannot ban yourself.", 400, "self_action")
    reason = _reason(data)
    _protect(target, "ban")
    _kpt().moderation().validate_ban_request(data.get("kind"), data.get("days"))  # request shape, before the one-time proof is consumed
    _reauth(data)
    _need_stepup("moderation", data)
    result = _kpt().moderation().ban(current_session()["user_id"], target, data.get("kind"), reason, data.get("days"),
                                     _kpt().audit().ip_hash(request.remote_addr))
    return jsonify(ok=True, **result)


@bp.post("/admin/users/<user_id>/unban")
@role_required("admin")
def unban_user(user_id: str):
    data, target = _body(), _target(user_id)
    reason = _reason(data)
    _reauth(data)
    _need_stepup("moderation", data)
    _kpt().moderation().unban(current_session()["user_id"], target, reason, _kpt().audit().ip_hash(request.remote_addr))
    return jsonify(ok=True)


@bp.get("/admin/reports")
@role_required("admin")
def message_reports():
    """Reported private conversations only: the queue shows the reason, never message text."""
    page, per = _page()
    return jsonify(**_kpt().messaging().reports(request.args.get("status", "open"), page, per))


@bp.get("/admin/reports/<report_id>/thread")
@role_required("admin")
def report_thread(report_id: str):
    """Message text of ONE reported conversation. The access is audited before any content is returned."""
    _audit("report_thread_viewed", report_id, "moderation review")
    return jsonify(**_kpt().messaging().report_thread(report_id))


@bp.post("/admin/reports/<report_id>/resolve")
@role_required("admin")
def resolve_report(report_id: str):
    note = _reason(_body())
    _audit("report_resolved", report_id, note[:150])
    _kpt().messaging().resolve_report(report_id, current_session()["user_id"], note)
    return jsonify(ok=True)
