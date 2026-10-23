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
            body = self.client.get(path).get_json()
            self.assertEqual(body["status"], "ok", path)
            self.assertEqual(body["records"], 16000)
            self.assertFalse(body["gemini"])

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
        app = create_app(dataclasses.replace(Settings.from_env(), data_dir=Settings.from_env().data_dir / "missing", gemini_api_key=None))
        r = app.test_client().get("/api/v1/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["status"], "error")


if __name__ == "__main__":
    unittest.main()
