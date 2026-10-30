"""Admin TOTP and step-up: enrolment, fail-closed key, replay, one-time/bound proofs, enforcement, recovery.
Deterministic: a fake clock replaces wall time inside TotpService and codes come from pyotp with that clock."""
import unittest
import warnings

warnings.filterwarnings("ignore")

import pyotp  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

from backend.services.totp_service import TotpService  # noqa: E402
from scripts import reset_admin_totp  # noqa: E402
from tests.backend.test_auth import ADMIN_PW, BASE, Client  # noqa: E402
from tests.backend.test_moderation_messaging import PW, Peer, uid, world  # noqa: E402

KEY = Fernet.generate_key().decode()
T0 = 1_900_000_020  # on a 30 s boundary


class Clock:
    def __init__(self):
        self.t = float(T0)

    def __call__(self):
        return self.t


def setup(**overrides):
    admin, people = world(totp_encryption_key=KEY, **overrides)
    kpt = admin.app.extensions["kpt"]
    clock = Clock()
    kpt._totp = TotpService(kpt.database(), KEY, "KPT Test", 120, now=clock)
    return admin, people, kpt, clock


def enrol(admin, clock):
    started = admin.post("/api/v1/admin/totp/enroll/start", {"password": ADMIN_PW})
    assert started.status_code == 200, started.get_json()
    secret = started.get_json()["secret"]
    code = pyotp.TOTP(secret).at(clock())
    assert admin.post("/api/v1/admin/totp/enroll/confirm", {"code": code}).status_code == 200
    return secret, code


def second_admin(admin, people):
    """buyer becomes a second admin with its own browser session."""
    kpt = admin.app.extensions["kpt"]
    kpt.database().execute("UPDATE users SET role = 'admin' WHERE email = 'buyer@example.com'")
    return people["buyer"]


class TotpAccessTests(unittest.TestCase):
    def test_only_authenticated_admins_can_use_totp_routes(self):
        admin, people, kpt, clock = setup()
        for who in (Peer(admin), people["seller"]):
            self.assertIn(who.get("/api/v1/admin/totp/status").status_code, (401, 403))
            for path, body in (("enroll/start", {"password": PW}), ("enroll/confirm", {"code": "123456"}),
                               ("disable", {"password": PW, "code": "123456"}), ("stepup", {"code": "123456", "action": "moderation"})):
                self.assertIn(who.post(f"/api/v1/admin/totp/{path}", body).status_code, (401, 403), path)

    def test_csrf_is_enforced(self):
        admin, people, kpt, clock = setup()
        r = admin.post("/api/v1/admin/totp/stepup", {"code": "123456", "action": "moderation"}, token=None)
        self.assertEqual(r.status_code, 403)

    def test_missing_or_invalid_key_fails_closed(self):
        for key in (None, "", "not-a-fernet-key"):
            admin, _ = world(totp_encryption_key=key)
            st = admin.get("/api/v1/admin/totp/status").get_json()
            self.assertFalse(st["configured"])
            r = admin.post("/api/v1/admin/totp/enroll/start", {"password": ADMIN_PW})
            self.assertEqual((r.status_code, r.get_json()["code"]), (503, "totp_unavailable"))
            kpt = admin.app.extensions["kpt"]
            self.assertIsNone(kpt.database().one("SELECT 1 AS x FROM admin_totp"))


class EnrolmentTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.people, self.kpt, self.clock = setup()

    def test_parallel_enrolment_start_loses_cleanly_with_409_not_a_server_error(self):
        import unittest.mock
        db = self.kpt.database()
        real = db.execute
        uid_ = db.one("SELECT id FROM users WHERE username = 'admin_001'")["id"]

        def racing(sql, params=()):
            n = real(sql, params)
            if sql.startswith("DELETE FROM admin_totp WHERE user_id = ? AND status = 'pending'"):   # a second request inserts first
                real("INSERT INTO admin_totp (user_id, secret_enc, status, created_at, last_step) VALUES (?, 'x', 'pending', 1, 0)", (uid_,))
            return n

        with unittest.mock.patch.object(db, "execute", side_effect=racing):
            r = self.admin.post("/api/v1/admin/totp/enroll/start", {"password": ADMIN_PW})
        self.assertEqual((r.status_code, r.get_json()["code"]), (409, "enrolment_in_progress"))
        self.assertNotIn("secret", r.get_json())

    def test_enrolment_needs_password_and_is_inactive_until_confirmed(self):
        self.assertEqual(self.admin.post("/api/v1/admin/totp/enroll/start", {"password": "wrong-password-123"}).status_code, 403)
        started = self.admin.post("/api/v1/admin/totp/enroll/start", {"password": ADMIN_PW}).get_json()
        self.assertTrue(started["otpauth_uri"].startswith("otpauth://totp/"))
        self.assertEqual(self.admin.get("/api/v1/admin/totp/status").get_json()["status"], "pending")
        # a pending secret gives no step-up and does not protect actions
        code = pyotp.TOTP(started["secret"]).at(self.clock())
        self.assertEqual(self.admin.post("/api/v1/admin/totp/stepup", {"code": code, "action": "moderation"}).status_code, 403)
        wrong = self.admin.post("/api/v1/admin/totp/enroll/confirm", {"code": "000000" if code != "000000" else "111111"})
        self.assertEqual((wrong.status_code, wrong.get_json()["code"]), (403, "invalid_code"))
        self.assertEqual(self.admin.get("/api/v1/admin/totp/status").get_json()["status"], "pending")
        self.assertEqual(self.admin.post("/api/v1/admin/totp/enroll/confirm", {"code": code}).status_code, 200)
        self.assertEqual(self.admin.get("/api/v1/admin/totp/status").get_json()["status"], "active")
        again = self.admin.post("/api/v1/admin/totp/enroll/start", {"password": ADMIN_PW})
        self.assertEqual((again.status_code, again.get_json()["code"]), (409, "already_enrolled"))

    def test_secret_is_encrypted_at_rest_and_never_in_status_or_audit(self):
        secret, code = enrol(self.admin, self.clock)
        row = self.kpt.database().one("SELECT secret_enc FROM admin_totp")
        self.assertNotIn(secret, row["secret_enc"])
        self.assertEqual(Fernet(KEY.encode()).decrypt(row["secret_enc"].encode()).decode(), secret)
        text = str(self.admin.get("/api/v1/admin/totp/status").get_json()) + str(self.kpt.database().all("SELECT * FROM audit_log"))
        self.assertNotIn(secret, text)
        self.assertNotIn(code, text)
        actions = [r["action"] for r in self.kpt.database().all("SELECT action FROM audit_log")]
        self.assertIn("totp_enroll_started", actions)
        self.assertIn("totp_enabled", actions)

    def test_wrong_key_after_rotation_requires_reenrolment_not_a_bypass(self):
        secret, _ = enrol(self.admin, self.clock)
        self.kpt._totp = TotpService(self.kpt.database(), Fernet.generate_key().decode(), "x", 120, now=self.clock)
        self.clock.t += 30
        r = self.admin.post("/api/v1/admin/totp/stepup", {"code": pyotp.TOTP(secret).at(self.clock()), "action": "moderation"})
        self.assertEqual((r.status_code, r.get_json()["code"]), (503, "totp_unavailable"))

    def test_disable_needs_password_and_a_current_code(self):
        secret, _ = enrol(self.admin, self.clock)
        self.clock.t += 30
        self.assertEqual(self.admin.post("/api/v1/admin/totp/disable", {"password": ADMIN_PW, "code": "000000"}).status_code, 403)
        self.assertEqual(self.admin.post("/api/v1/admin/totp/disable", {"password": "wrong-password-123", "code": pyotp.TOTP(secret).at(self.clock())}).status_code, 403)
        ok = self.admin.post("/api/v1/admin/totp/disable", {"password": ADMIN_PW, "code": pyotp.TOTP(secret).at(self.clock())})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.admin.get("/api/v1/admin/totp/status").get_json()["status"], "none")


class StepUpTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.people, self.kpt, self.clock = setup()
        self.secret, self.used_code = enrol(self.admin, self.clock)
        self.target = uid(self.admin, "seller@example.com")
        self.db = self.kpt.database()

    def code(self, advance=30):
        self.clock.t += advance
        return pyotp.TOTP(self.secret).at(self.clock())

    def proof(self, action="moderation", advance=30):
        r = self.admin.post("/api/v1/admin/totp/stepup", {"code": self.code(advance), "action": action})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["proof"]

    def ban(self, proof=None, who=None):
        body = {"password": ADMIN_PW, "kind": "permanent", "reason": "spam listings"}
        if proof is not None:
            body["stepup"] = proof
        return (who or self.admin).post(f"/api/v1/admin/users/{self.target}/ban", body)

    def test_replayed_code_is_rejected_and_a_new_step_works(self):
        c = self.code()
        body = {"code": c, "action": "moderation"}
        self.assertEqual(self.admin.post("/api/v1/admin/totp/stepup", body).status_code, 200)
        replay = self.admin.post("/api/v1/admin/totp/stepup", body)
        self.assertEqual((replay.status_code, replay.get_json()["code"]), (403, "invalid_code"))
        self.assertEqual(self.admin.post("/api/v1/admin/totp/stepup", {"code": self.code(30), "action": "moderation"}).status_code, 200)

    def test_code_used_for_enrolment_cannot_be_replayed_for_stepup(self):
        r = self.admin.post("/api/v1/admin/totp/stepup", {"code": self.used_code, "action": "moderation"})
        self.assertEqual(r.status_code, 403)

    def test_sensitive_actions_need_a_valid_proof(self):
        for path, body in ((f"users/{self.target}/ban", {"kind": "permanent", "reason": "spam listings"}),
                           (f"users/{self.target}/role", {"role": "admin"}),
                           (f"users/{self.target}/status", {"status": "disabled"})):
            r = self.admin.post(f"/api/v1/admin/{path}", {"password": ADMIN_PW, **body})
            self.assertEqual((r.status_code, r.get_json()["code"]), (403, "stepup_required"), path)
        self.assertEqual(self.admin.post(f"/api/v1/admin/users/{self.target}/unban", {"password": ADMIN_PW, "reason": "mistake made"}).get_json()["code"], "stepup_required")
        self.assertEqual(self.db.one("SELECT status FROM users WHERE id = ?", (self.target,))["status"], "active")

    def test_malformed_ban_requests_do_not_burn_the_one_time_proof(self):
        p = self.proof("moderation")
        bad = self.admin.post(f"/api/v1/admin/users/{self.target}/ban", {"password": ADMIN_PW, "kind": "forever", "reason": "typo test", "stepup": p})
        self.assertEqual((bad.status_code, bad.get_json()["code"]), (400, "invalid_kind"))
        days = self.admin.post(f"/api/v1/admin/users/{self.target}/ban", {"password": ADMIN_PW, "kind": "temporary", "days": 0, "reason": "typo test", "stepup": p})
        self.assertEqual(days.get_json()["code"], "invalid_days")
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM admin_stepups WHERE used_at IS NULL")["n"], 1)
        self.assertEqual(self.ban(p).status_code, 200)  # the very same proof still works for the real request
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM admin_stepups WHERE used_at IS NULL")["n"], 0)

    def test_proof_works_once(self):
        p = self.proof("moderation")
        self.assertEqual(self.ban(p).status_code, 200)
        self.assertEqual(self.db.one("SELECT status FROM users WHERE id = ?", (self.target,))["status"], "banned")
        again = self.ban(p)
        self.assertEqual(again.status_code, 403)
        self.assertEqual(again.get_json()["code"], "stepup_required")

    def test_proof_is_bound_to_the_action_class(self):
        p = self.proof("role_change")
        self.assertEqual(self.ban(p).status_code, 403)  # wrong class
        r = self.admin.post(f"/api/v1/admin/users/{self.target}/role", {"password": ADMIN_PW, "role": "admin", "stepup": p})
        self.assertEqual(r.status_code, 200, "the proof was not consumed by the failed attempt")

    def test_proof_expires(self):
        p = self.proof("moderation")
        self.clock.t += 121
        self.assertEqual(self.ban(p).get_json()["code"], "stepup_required")
        self.clock.t -= 121
        self.assertEqual(self.ban(p).status_code, 200)

    def test_proof_is_bound_to_the_session(self):
        p = self.proof("moderation")
        other = Peer(self.admin)
        self.assertEqual(other.login("admin_001", ADMIN_PW).status_code, 200)  # same admin, different session
        r = self.ban(p, who=other)
        self.assertEqual((r.status_code, r.get_json()["code"]), (403, "stepup_required"))
        self.assertEqual(self.ban(p).status_code, 200)  # still valid in the session it was issued to

    def test_garbage_proofs_fail(self):
        for bad in ("", "x" * 10, "A" * 43, 5, None, ["a"], {"a": 1}):
            self.assertEqual(self.ban(bad).status_code, 403, repr(bad))

    def test_protected_accounts_are_still_protected(self):
        admin_id = uid(self.admin, "admin_001") if False else self.db.one("SELECT id FROM users WHERE username = 'admin_001'")["id"]
        p = self.proof("moderation")
        r = self.admin.post(f"/api/v1/admin/users/{admin_id}/ban", {"password": ADMIN_PW, "kind": "permanent", "reason": "spam listings", "stepup": p})
        self.assertIn(r.status_code, (400, 403))
        self.assertNotEqual(self.db.one("SELECT status FROM users WHERE id = ?", (admin_id,))["status"], "banned")

    def test_csv_export_requires_a_post_with_proof(self):
        g = self.admin.get("/api/v1/admin/export/users.csv")
        self.assertEqual((g.status_code, g.get_json()["code"]), (403, "stepup_required"))
        self.assertEqual(self.admin.post("/api/v1/admin/export/users.csv", {}).status_code, 403)
        p = self.proof("csv_export")
        ok = self.admin.post("/api/v1/admin/export/users.csv", {"stepup": p})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.data.startswith(b"id,name"))
        self.assertEqual(self.admin.post("/api/v1/admin/export/users.csv", {"stepup": p}).status_code, 403)
        self.assertEqual(self.admin.post("/api/v1/admin/export/nope.csv", {"stepup": self.proof("csv_export")}).status_code, 404)

    def test_audit_has_success_and_failure_events_without_codes_or_proofs(self):
        p = self.proof("moderation")
        bad = "123456" if self.code(30) != "123456" else "654321"
        self.admin.post("/api/v1/admin/totp/stepup", {"code": bad, "action": "moderation"})
        self.ban(p)
        text = str(self.db.all("SELECT * FROM audit_log"))
        actions = {r["action"] for r in self.db.all("SELECT action FROM audit_log")}
        self.assertTrue({"totp_stepup_ok", "totp_failed"} <= actions)
        self.assertNotIn(p, text)
        self.assertNotIn(bad, text)

    def test_repeated_failures_are_rate_limited_and_audited(self):
        statuses = [self.admin.post("/api/v1/admin/totp/stepup", {"code": f"{i:06d}", "action": "moderation"}).status_code for i in range(11)]
        self.assertIn(429, statuses)
        self.assertNotIn(200, statuses)
        self.assertIn("totp_rate_limited", {r["action"] for r in self.db.all("SELECT action FROM audit_log")})
        # even a correct code is refused while the limiter is tripped
        self.assertEqual(self.admin.post("/api/v1/admin/totp/stepup", {"code": self.code(), "action": "moderation"}).status_code, 429)

    def test_demoting_an_admin_removes_their_second_factor(self):
        peer = second_admin(self.admin, self.people)
        other = Client_login(self.admin, "buyer@example.com")
        self.assertIsNotNone(other)
        buyer_id = uid(self.admin, "buyer@example.com")
        self.db.execute("INSERT INTO admin_totp (user_id, secret_enc, status, created_at, last_step) VALUES (?, 'x', 'active', 1, 0)", (buyer_id,))
        p = self.proof("role_change")
        r = self.admin.post(f"/api/v1/admin/users/{buyer_id}/role", {"password": ADMIN_PW, "role": "user", "stepup": p})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIsNone(self.db.one("SELECT 1 AS x FROM admin_totp WHERE user_id = ?", (buyer_id,)))


def Client_login(admin, email):  # helper: keep the test above readable
    return Peer(admin).login(email, PW)


class GoogleOnlyAdminTests(unittest.TestCase):
    """Documented limitation: an admin who signs in only with Google has no password, so password re-authentication (and
    therefore enrolment and every sensitive action) is refused until they set one. It must fail closed, never 500."""

    def test_admin_without_a_password_cannot_enrol_or_act_and_fails_closed(self):
        admin, people, kpt, clock = setup()
        other = second_admin(admin, people)
        kpt.database().execute("UPDATE users SET password_hash = NULL WHERE email = 'buyer@example.com'")
        r = other.post("/api/v1/admin/totp/enroll/start", {"password": PW})
        self.assertEqual((r.status_code, r.get_json()["code"]), (403, "reauth_failed"))
        target = uid(admin, "seller@example.com")
        r = other.post(f"/api/v1/admin/users/{target}/ban", {"password": "", "kind": "permanent", "reason": "no password"})
        self.assertIn(r.status_code, (400, 403))
        self.assertIsNone(kpt.database().one("SELECT 1 AS x FROM admin_totp"))
        self.assertEqual(kpt.database().one("SELECT status FROM users WHERE id = ?", (target,))["status"], "active")


class EnforcementAndRecoveryTests(unittest.TestCase):
    def test_without_totp_actions_keep_working_by_default(self):
        admin, people, kpt, clock = setup()
        target = uid(admin, "seller@example.com")
        r = admin.post(f"/api/v1/admin/users/{target}/ban", {"password": ADMIN_PW, "kind": "permanent", "reason": "spam listings"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(admin.get("/api/v1/admin/export/users.csv").status_code, 200)

    def test_required_mode_blocks_unenrolled_admins_but_not_login_or_enrolment(self):
        admin, people, kpt, clock = setup(admin_totp_required=True)
        self.assertTrue(admin.get("/api/v1/admin/totp/status").get_json()["required"])
        target = uid(admin, "seller@example.com")
        r = admin.post(f"/api/v1/admin/users/{target}/ban", {"password": ADMIN_PW, "kind": "permanent", "reason": "spam listings"})
        self.assertEqual((r.status_code, r.get_json()["code"]), (403, "totp_enrollment_required"))
        self.assertEqual(admin.get("/api/v1/admin/export/users.csv").status_code, 403)
        self.assertEqual(admin.get("/api/v1/admin/users").status_code, 200, "read-only admin screens still work")
        enrol(admin, clock)
        clock.t += 30
        p = admin.post("/api/v1/admin/totp/stepup", {"code": pyotp.TOTP(kpt.database().one("SELECT secret_enc FROM admin_totp") and _plain(kpt)).at(clock()), "action": "moderation"}).get_json()["proof"]
        ok = admin.post(f"/api/v1/admin/users/{target}/ban", {"password": ADMIN_PW, "kind": "permanent", "reason": "spam listings", "stepup": p})
        self.assertEqual(ok.status_code, 200)

    def test_operator_recovery_for_admin_001(self):
        admin, people, kpt, clock = setup(admin_totp_required=True)
        enrol(admin, clock)
        db = kpt.database()
        dry = reset_admin_totp.reset(db, kpt.audit(), kpt.sessions(), "admin_001", apply=False)
        self.assertEqual((dry["two_factor"], dry["applied"]), ("active", False))
        self.assertEqual(admin.get("/api/v1/admin/totp/status").get_json()["status"], "active", "dry run changes nothing")
        done = reset_admin_totp.reset(db, kpt.audit(), kpt.sessions(), "admin_001", apply=True)
        self.assertTrue(done["ok"])
        self.assertGreaterEqual(done["sessions_revoked"], 1)
        self.assertEqual(admin.get("/api/v1/admin/totp/status").status_code, 401, "all sessions were revoked")
        fresh = Peer(admin)
        self.assertEqual(fresh.login("admin_001", ADMIN_PW).status_code, 200)       # password login still works
        self.assertEqual(fresh.get("/api/v1/admin/totp/status").get_json()["status"], "none")
        self.assertIn("totp_reset_by_operator", {r["action"] for r in db.all("SELECT action FROM audit_log")})
        enrol(fresh, clock)                                                          # and a new device can be enrolled
        self.assertEqual(fresh.get("/api/v1/admin/totp/status").get_json()["status"], "active")

    def test_recovery_refuses_non_admins_and_unknown_users(self):
        admin, people, kpt, clock = setup()
        for name in ("seller@example.com", "nobody"):
            self.assertFalse(reset_admin_totp.reset(kpt.database(), kpt.audit(), kpt.sessions(), name, apply=True)["ok"])


def _plain(kpt):
    row = kpt.database().one("SELECT secret_enc FROM admin_totp")
    return Fernet(KEY.encode()).decrypt(row["secret_enc"].encode()).decode()


if __name__ == "__main__":
    unittest.main()
