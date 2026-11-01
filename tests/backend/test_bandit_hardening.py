"""Regression tests for the Bandit review: URL scheme/host checks, SQL identifier whitelists and the dev-server bind address."""
import dataclasses
import os
import unittest
import warnings
from urllib.parse import quote

warnings.filterwarnings("ignore")

from backend.config import Settings  # noqa: E402
from backend.middleware import build_store  # noqa: E402
from backend.security.ratelimit_store import MemoryStore, UpstashStore, validate_rest_url  # noqa: E402
from backend.services.retention_service import RetentionService  # noqa: E402
from tests.backend.test_auth import ADMIN_PW, Client  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RestUrlTests(unittest.TestCase):
    def test_https_and_loopback_http_are_accepted(self):
        self.assertEqual(validate_rest_url("https://example-123.upstash.io/"), "https://example-123.upstash.io")
        for u in ("http://127.0.0.1:9", "http://localhost:8080/x", "http://[::1]:9"):
            self.assertTrue(validate_rest_url(u))

    def test_unsafe_urls_are_refused(self):
        bad = ["file:///etc/passwd", "ftp://example.com/x", "http://example.com", "gopher://example.com", "javascript:alert(1)",
               "https://", "//example.com", "example.com", "", None, "https://user:secret@example.com", "http://127.0.0.1.evil.com"]
        for u in bad:
            with self.assertRaises(ValueError, msg=repr(u)):
                validate_rest_url(u)

    def test_error_message_never_echoes_the_url(self):
        with self.assertRaises(ValueError) as cm:
            validate_rest_url("https://user:s3cret-token@example.com")
        self.assertNotIn("s3cret", str(cm.exception))

    def test_store_refuses_bad_url_and_factory_falls_back_to_memory(self):
        with self.assertRaises(ValueError):
            UpstashStore("file:///etc/passwd", "t")
        s = dataclasses.replace(Settings.from_env(), redis_rest_url="file:///etc/passwd", redis_rest_token="t")
        with self.assertLogs("kpt.ratelimit", level="ERROR"):
            self.assertIsInstance(build_store(s), MemoryStore)
        good = dataclasses.replace(Settings.from_env(), redis_rest_url="https://example-123.upstash.io", redis_rest_token="t")
        self.assertIsInstance(build_store(good), UpstashStore)


class RetentionWhitelistTests(unittest.TestCase):
    class Db:
        def __init__(self): self.sql = []
        def execute(self, sql, params=()): self.sql.append(sql)

    def test_only_retention_tables_can_be_deleted_from(self):
        db = self.Db(); svc = RetentionService(db)
        for table in ("users", "sessions", "messages; DROP TABLE users", "messages --", ""):
            with self.assertRaises(ValueError, msg=table):
                svc._delete(table, ["a"])
        self.assertEqual(db.sql, [], "nothing may run for a refused table")
        for table in ("message_reports", "messages", "conversations"):
            svc._delete(table, ["a", "b"])
        self.assertEqual(len(db.sql), 3)
        self.assertTrue(all("IN (?,?)" in q for q in db.sql))   # ids are placeholders, never inlined


class AdminSqlWhitelistTests(unittest.TestCase):
    """Hostile query-string values must never reach SQL text: unknown sort/status/role fall back to defaults, q is a bound parameter."""
    HOSTILE = ["created_at; DROP TABLE users--", "name) UNION SELECT password_hash FROM users--", "' OR '1'='1", "1; DELETE FROM users"]

    def setUp(self):
        self.cl = Client()
        self.assertEqual(self.cl.login("admin_001", ADMIN_PW).status_code, 200)

    def users(self, **qs):
        r = self.cl.get("/api/v1/admin/users?" + "&".join(f"{k}={quote(v)}" for k, v in qs.items()))
        self.assertEqual(r.status_code, 200, qs)
        return r.get_json()

    def test_users_endpoint_ignores_hostile_sort_status_role_and_dir(self):
        base = self.users()
        for h in self.HOSTILE:
            got = self.users(sort=h, status=h, role=h, dir=h, q=h)
            self.assertIn("users", got)
        self.assertEqual(self.users()["total"], base["total"], "the table must be intact and unchanged")
        self.assertEqual(self.users(status="active")["total"], base["total"])   # a valid value still filters

    def test_unknown_sort_matches_the_default_order(self):
        self.assertEqual(self.users(sort="nope; --")["users"], self.users()["users"])

    def test_q_is_a_bound_parameter(self):
        self.assertEqual(self.users(q="%' OR 1=1 --")["total"], 0)

    def test_login_events_filters_are_bound(self):
        for h in self.HOSTILE:
            r = self.cl.get("/api/v1/admin/login-events?" + f"q={quote(h)}&outcome={quote(h)}&method={quote(h)}")
            self.assertEqual(r.status_code, 200)


class DevServerBindTests(unittest.TestCase):
    def test_dev_server_binds_loopback_unless_kpt_host_is_set(self):
        with open(os.path.join(ROOT, "backend", "app.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('host=os.getenv("KPT_HOST", "127.0.0.1")', src)
        self.assertNotIn('host="0.0.0.0"', src)


if __name__ == "__main__":
    unittest.main()


class DevServerEntrypointTests(unittest.TestCase):
    def test_module_entrypoint_imports_what_it_uses(self):
        # Regression: `python -m backend.app` crashed with NameError (os not imported) after the bind-address change.
        import ast
        from pathlib import Path
        tree = ast.parse(Path("backend/app.py").read_text(encoding="utf-8"))
        imported = {a.asname or a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        used = {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
        if "os" in used:
            self.assertIn("os", imported)
