"""Admin two-factor (TOTP) management and step-up proofs. Thin blueprint: logic is in ``services/totp_service.py``.

* ``GET  /admin/totp/status``          none | pending | active, whether the server key is set, whether it is enforced
* ``POST /admin/totp/enroll/start``    password re-auth, returns the secret ONCE (manual key / otpauth URI; no QR library is used)
* ``POST /admin/totp/enroll/confirm``  a correct code activates the secret
* ``POST /admin/totp/disable``         password + a current code
* ``POST /admin/totp/stepup``          a current code => short-lived, one-time proof bound to this session and one action class
All routes need the ``admin`` role and CSRF (``/admin/`` is a protected prefix). Failed codes are rate limited and audited;
secrets, codes and proofs are never logged.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.api.admin import _audit, _body, _kpt, _reauth
from backend.errors import ApiError
from backend.security.guards import current_session, role_required
from backend.services.totp_service import ACTION_CLASSES

bp = Blueprint("admin_totp", __name__)
V1_ONLY = True


def _uid() -> str:
    return current_session()["user_id"]


def _code(data: dict) -> str:
    code = data.get("code")
    if not isinstance(code, str) or not 6 <= len(code) <= 10:
        raise ApiError("Enter the 6-digit code from your authenticator app.", 400, "invalid_code")
    return code


def _throttle() -> None:
    """Count every code attempt (success or not). Audits once when the limit trips."""
    limiter = _kpt().totp_limiter()
    try:
        limiter.check(f"user:{_uid()}")
        limiter.check(f"ip:{request.remote_addr or 'unknown'}")
    except ApiError:
        _audit("totp_rate_limited", _uid(), "too many two-factor attempts")
        raise


def _check_code(data: dict, *, enrolment: bool = False) -> None:
    _throttle()
    totp = _kpt().totp()
    ok = totp.confirm_enrolment(_uid(), _code(data)) if enrolment else totp.verify_active(_uid(), _code(data))
    if not ok:
        _audit("totp_failed", _uid(), "enrolment" if enrolment else "verification")  # never the submitted code
        raise ApiError("That code is not valid. Check the time on your device and try again.", 403, "invalid_code")


@bp.get("/admin/totp/status")
@role_required("admin")
def status():
    kpt = _kpt()
    return jsonify(status=kpt.totp().status(_uid()), configured=kpt.totp().configured(), required=kpt.settings.admin_totp_required)


@bp.post("/admin/totp/enroll/start")
@role_required("admin")
def enroll_start():
    data = _body()
    _reauth(data)  # recent re-authentication
    sess = current_session()
    label = sess.get("email") or sess.get("username") or sess["name"]
    result = _kpt().totp().start_enrolment(_uid(), str(label))
    _audit("totp_enroll_started", _uid(), "")
    resp = jsonify(**result)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/admin/totp/enroll/confirm")
@role_required("admin")
def enroll_confirm():
    data = _body()
    _check_code(data, enrolment=True)
    _audit("totp_enabled", _uid(), "")
    return jsonify(ok=True, status="active")


@bp.post("/admin/totp/disable")
@role_required("admin")
def disable():
    data = _body()
    _reauth(data)
    if _kpt().totp().status(_uid()) == "active":
        _check_code(data)  # only someone holding the device can remove the second factor here (lost device: docs/ADMIN.md)
    _kpt().totp().disable(_uid())
    _audit("totp_disabled", _uid(), "")
    return jsonify(ok=True, status="none")


@bp.post("/admin/totp/stepup")
@role_required("admin")
def stepup():
    data = _body()
    action = data.get("action")
    if action not in ACTION_CLASSES:
        raise ApiError("Unknown action.", 400, "invalid_action")
    _check_code(data)
    proof = _kpt().totp().issue_proof(_uid(), current_session()["id_hash"], action)
    _audit("totp_stepup_ok", _uid(), action)
    resp = jsonify(**proof)
    resp.headers["Cache-Control"] = "no-store"
    return resp
