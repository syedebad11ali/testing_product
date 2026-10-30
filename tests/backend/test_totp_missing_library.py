"""A missing ``pyotp`` package must disable TOTP (fail closed), never take the whole application down at import time.
This module deliberately does not import pyotp, so it runs (and must pass) in an environment that lacks the package."""
import subprocess
import sys
import unittest
import warnings
from pathlib import Path
from unittest import mock

warnings.filterwarnings("ignore")

from backend.services import totp_service  # noqa: E402
from tests.backend.test_auth import ADMIN_PW  # noqa: E402
from tests.backend.test_moderation_messaging import uid, world  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class MissingLibraryTests(unittest.TestCase):
    def test_application_imports_when_pyotp_is_not_installed(self):
        code = "import sys; sys.modules['pyotp'] = None; import backend.app, backend.api.admin, backend.api.admin_totp; print('ok')"
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "ok"), out.stderr[-400:])

    def test_totp_routes_fail_closed_with_503_and_non_totp_admin_work_continues(self):
        from cryptography.fernet import Fernet
        with mock.patch.object(totp_service, "pyotp", None):
            admin, people = world(totp_encryption_key=Fernet.generate_key().decode())
            self.assertFalse(admin.get("/api/v1/admin/totp/status").get_json()["configured"])
            r = admin.post("/api/v1/admin/totp/enroll/start", {"password": ADMIN_PW})
            self.assertEqual((r.status_code, r.get_json()["code"]), (503, "totp_unavailable"))
            db = admin.app.extensions["kpt"].database()
            self.assertIsNone(db.one("SELECT 1 AS x FROM admin_totp"))  # nothing was stored
            # TOTP is optional by default, so the rest of the admin panel (and login) keeps working
            bid = uid(admin, "buyer@example.com")
            ok = admin.post(f"/api/v1/admin/users/{bid}/ban", {"kind": "permanent", "reason": "library missing test", "password": ADMIN_PW})
            self.assertEqual(ok.status_code, 200, ok.get_json())


if __name__ == "__main__":
    unittest.main()
