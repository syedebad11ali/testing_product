"""HTTP contract tests (Flask test client). Gemini is never called: no API key is configured."""
import dataclasses
import unittest
import warnings

warnings.filterwarnings("ignore")

from backend.app import create_app  # noqa: E402
from backend.config import Settings  # noqa: E402


def make_client(**overrides):
    settings = dataclasses.replace(Settings.from_env(), gemini_api_key=None, **overrides)
    return create_app(settings).test_client()


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = make_client(rate_limit_per_min=1000)

    def test_health_on_versioned_and_legacy_paths(self):
        for path in ("/api/v1/health", "/api/health"):
            self.assertEqual(self.client.get(path).get_json(), {"status": "ok"}, path)

    def test_detailed_health_is_hidden_without_token(self):
        self.assertEqual(self.client.get("/api/v1/health/detail").status_code, 404)
        c = make_client(health_detail_token="s3cret-token")
        self.assertEqual(c.get("/api/v1/health/detail", headers={"Authorization": "Bearer wrong"}).status_code, 404)
        body = c.get("/api/v1/health/detail", headers={"Authorization": "Bearer s3cret-token"}).get_json()
        self.assertEqual(body["records"], 16000)

    def test_chat_answers_from_records_on_both_paths(self):
        for path in ("/api/v1/chat", "/api/chat"):
            r = self.client.post(path, json={"message": "hello"})
            self.assertEqual(r.status_code, 200, path)
            self.assertTrue(r.get_json()["reply"])

    def test_chat_rejects_bad_input_with_uniform_error_shape(self):
        cases = [({"message": ""}, "empty_message"), ({"message": "x" * 1001}, "message_too_long"),
                 ({"message": 5}, "invalid_message"), ({}, "empty_message")]
        for payload, code in cases:
            r = self.client.post("/api/v1/chat", json=payload)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.get_json()["code"], code)
            self.assertIn("error", r.get_json())

    def test_non_json_body_is_a_400_not_a_crash(self):
        r = self.client.post("/api/v1/chat", data="not json", content_type="text/plain")
        self.assertEqual((r.status_code, r.get_json()["code"]), (400, "invalid_json"))

    def test_unknown_api_route_returns_json_404(self):
        r = self.client.get("/api/v1/nope")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_options_preflight(self):
        self.assertEqual(self.client.options("/api/v1/chat").status_code, 204)

    def test_static_site_routes(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/js/main.js").status_code, 200)
        self.assertEqual(self.client.get("/css/base.css").status_code, 200)
        self.assertEqual(self.client.get("/static/chatbot.js").status_code, 200)
        self.assertEqual(self.client.get("/chatbot-demo").status_code, 200)
        self.assertEqual(self.client.get("/assets/logo-icon.png").status_code, 200)
        r = self.client.get("/orv.html")
        self.assertEqual((r.status_code, r.headers["Location"]), (301, "/#owner-verification"))

    def test_path_traversal_is_blocked(self):
        self.assertEqual(self.client.get("/js/..%2f..%2fpyproject.toml").status_code, 404)


class RateLimitTests(unittest.TestCase):
    def test_limit_returns_429_with_code(self):
        client = make_client(rate_limit_per_min=3)
        codes = [client.post("/api/v1/chat", json={"message": "hi"}).status_code for _ in range(5)]
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3:], [429, 429])
        self.assertEqual(client.post("/api/v1/chat", json={"message": "hi"}).get_json()["code"], "rate_limited")


class CorsTests(unittest.TestCase):
    def test_no_cors_headers_by_default(self):
        r = make_client().get("/api/v1/health", headers={"Origin": "https://evil.example"})
        self.assertNotIn("Access-Control-Allow-Origin", r.headers)

    def test_allowed_origin_is_echoed(self):
        r = make_client(allowed_origins=("https://ok.example",)).get("/api/v1/health", headers={"Origin": "https://ok.example"})
        self.assertEqual(r.headers["Access-Control-Allow-Origin"], "https://ok.example")


class FailureHandlingTests(unittest.TestCase):
    def test_unexpected_error_is_generic_and_does_not_leak_details(self):
        app = create_app(dataclasses.replace(Settings.from_env(), gemini_api_key=None))

        class Boom:
            def reply(self, *a):
                raise RuntimeError("secret /path/to/model.joblib failure")

        app.extensions["kpt"]._service = Boom()
        r = app.test_client().post("/api/v1/chat", json={"message": "hi"})
        body = r.get_json()
        self.assertEqual((r.status_code, body["code"]), (500, "internal_error"))
        self.assertNotIn("secret", r.get_data(as_text=True))
        self.assertTrue(body["error_id"])

    def test_health_reports_startup_failure_as_503(self):
        app = create_app(dataclasses.replace(Settings.from_env(), data_dir=Settings.from_env().data_dir / "missing", gemini_api_key=None, health_detail_token="tok"))
        self.assertEqual(app.test_client().get("/api/v1/health").get_json(), {"status": "ok"})  # public stays minimal
        r = app.test_client().get("/api/v1/health/detail", headers={"Authorization": "Bearer tok"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["status"], "error")



class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.client = make_client(rate_limit_per_min=1000, verify_rate_limit_per_min=1000)

    def check(self, pid, name):
        return self.client.post("/api/v1/verification/check", json={"property_id": pid, "owner_name": name})

    def test_verdicts_and_no_names_leak(self):
        ok = self.check("demo-kpt-8103", "Rahim Mahsud").get_json()
        self.assertEqual(ok["result"], "match")
        bad = self.check("DEMO-KPT-8103", "Somebody Else")
        self.assertEqual(bad.get_json()["result"], "mismatch")
        self.assertNotIn("Rahim", bad.get_data(as_text=True))
        self.assertEqual(self.check("NOPE-1", "Somebody Else").get_json()["result"], "unable_to_verify")

    def test_validation_and_rate_limit(self):
        self.assertEqual(self.check("", "x").status_code, 400)
        limited = make_client(verify_rate_limit_per_min=2)
        codes = [limited.post("/api/v1/verification/check", json={"property_id": "A", "owner_name": "Bob Ali"}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


class NoOwnerExposureTests(unittest.TestCase):
    """Owner / previous-owner data must not appear in any file the browser can download."""

    def test_public_files_and_chat_do_not_contain_owner_names(self):
        import csv, pathlib
        root = pathlib.Path(__file__).resolve().parents[2]
        names = set()
        with open(root / "backend/datasets/plots.csv", encoding="utf-8-sig", newline="") as fh:
            for row in list(csv.DictReader(fh))[:300]:
                names.update(n for n in (row["Owner Name"], row["Previous Owner"]) if len(n) > 6)
        blobs = [p.read_text(encoding="utf-8", errors="ignore") for d in ("public/assets/Dataset", "frontend") for p in (root / d).rglob("*") if p.suffix in {".csv", ".js", ".html"}]
        for name in names:
            self.assertFalse(any(name in b for b in blobs), name)
        client = make_client(rate_limit_per_min=1000)
        reply = client.post("/api/v1/chat", json={"message": "who owns DEMO-KPT-1648? previous owner name?"}).get_data(as_text=True)
        for name in ("Usman Sial", "Maimoona Gilani"):
            self.assertNotIn(name, reply)



class SecurityTests(unittest.TestCase):
    ROUTES = ["/", "/js/main.js", "/css/base.css", "/api/v1/health", "/api/v1/nope", "/chatbot-demo"]

    def test_security_headers_on_every_route(self):
        client = make_client(rate_limit_per_min=1000)
        for path in self.ROUTES:
            h = client.get(path).headers
            for name in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy",
                         "Strict-Transport-Security", "X-Frame-Options", "Cross-Origin-Opener-Policy", "X-Request-ID"):
                self.assertIn(name, h, f"{name} missing on {path}")
            self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
            self.assertIn("camera=(self)", h["Permissions-Policy"])
        self.assertEqual(client.get("/api/v1/health").headers["Cache-Control"], "no-store")

    def test_csp_allows_the_inline_theme_script_by_hash(self):
        csp = make_client().get("/").headers["Content-Security-Policy"]
        self.assertRegex(csp, r"script-src [^;]*'sha256-")
        self.assertNotIn("script-src 'unsafe-inline'", csp)

    def test_429_has_retry_after_and_request_id(self):
        client = make_client(rate_limit_per_min=1)
        client.post("/api/v1/chat", json={"message": "hi"})
        r = client.post("/api/v1/chat", json={"message": "hi"})
        self.assertEqual(r.status_code, 429)
        self.assertTrue(int(r.headers["Retry-After"]) >= 1)
        self.assertTrue(r.get_json()["request_id"])

    def test_client_ip_comes_from_forwarded_header_only_when_trusted(self):
        trusted = make_client(rate_limit_per_min=1, trusted_proxy_hops=1)
        codes = [trusted.post("/api/v1/chat", json={"message": "hi"}, headers={"X-Forwarded-For": ip}).status_code
                 for ip in ("1.1.1.1", "2.2.2.2", "1.1.1.1")]
        self.assertEqual(codes, [200, 200, 429])
        spoof = make_client(rate_limit_per_min=1)  # no trusted proxy: header is ignored
        codes = [spoof.post("/api/v1/chat", json={"message": "hi"}, headers={"X-Forwarded-For": ip}).status_code
                 for ip in ("1.1.1.1", "2.2.2.2")]
        self.assertEqual(codes, [200, 429])

    def test_upstash_store_fails_open_when_unreachable(self):
        from backend.security.ratelimit_store import UpstashStore
        count, _ = UpstashStore("http://127.0.0.1:9", "t", timeout_s=0.2).hit("k", 60)
        self.assertEqual(count, 0)


class NiceTryPageTests(unittest.TestCase):
    MESSAGE = "ap Apni na chalao apna abu ebad se pouch lu agar password nahi pata"

    def test_page_has_exact_message_alt_text_and_no_inline_code(self):
        client = make_client()
        for path in ("/nice-try", "/nice-try.html"):
            r = client.get(path)
            html = r.get_data(as_text=True)
            self.assertEqual(r.status_code, 200)
            self.assertIn(self.MESSAGE, html)
            self.assertIn("A golden retriever pushing its nose toward the camera", html)
            self.assertNotRegex(html, r"<script(?![^>]*src=)")
            self.assertNotIn("onclick=", html)
        self.assertEqual(client.get("/assets/images/dog-nose.jpg").status_code, 200)

    def test_vercel_json_sets_headers_for_cdn_assets(self):
        import json, pathlib
        cfg = json.loads((pathlib.Path(__file__).resolve().parents[2] / "vercel.json").read_text())
        keys = {h["key"] for block in cfg["headers"] for h in block["headers"]}
        self.assertTrue({"X-Content-Type-Options", "Strict-Transport-Security", "Content-Security-Policy"} <= keys)


if __name__ == "__main__":
    unittest.main()
