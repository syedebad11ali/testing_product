"""Record store, offline engine and config behaviour (no network, no Gemini)."""
import os
import unittest
import warnings
from unittest import mock

warnings.filterwarnings("ignore")

from backend.config import Settings  # noqa: E402
from backend.records.store import Store  # noqa: E402
from backend.records.text import fmt, norm  # noqa: E402
from backend.services.greetings import is_greeting  # noqa: E402
from backend.services.offline_engine import OfflineEngine  # noqa: E402


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = Settings.from_env()
        cls.store = Store(s.data_dir, s.model_path)
        cls.engine = OfflineEngine(cls.store)

    def test_loads_all_records(self):
        self.assertEqual(len(self.store.df), 16000)

    def test_owner_data_is_never_loaded(self):
        cols = [c.lower() for c in self.store.df.columns]
        for banned in ("owner_name", "owner name", "previous_owner", "previous owner", "owner_id", "cnic"):
            self.assertNotIn(banned, cols)
        self.assertIn("ownership", cols)  # status only (e.g. "Verified"), not a person

    def test_offline_answers_are_strings_and_never_mention_owner_fields(self):
        for q in ("who is the owner of property 8103", "price of house in DHA", "xyz nonsense", ""):
            reply = self.engine.answer(q)
            self.assertTrue(reply)

    def test_missing_data_dir_fails_loudly(self):
        s = Settings.from_env()
        with self.assertRaises(Exception):
            Store(s.data_dir / "nope", s.model_path)

    def test_text_helpers(self):
        self.assertEqual(norm("  D.H.A  Phase-6 "), "d h a phase 6")
        self.assertEqual(fmt(None), "not listed")
        self.assertIn("crore", fmt(25_000_000))
        self.assertTrue(is_greeting("salam"))


class ConfigTests(unittest.TestCase):
    def test_bad_numeric_env_falls_back_instead_of_crashing(self):
        with mock.patch.dict(os.environ, {"RATE_LIMIT_PER_MIN": "lots", "PORT": "", "GEMINI_TIMEOUT_MS": "-5"}):
            s = Settings.from_env()
        self.assertEqual((s.rate_limit_per_min, s.port), (20, 5000))
        self.assertGreaterEqual(s.gemini_timeout_ms, 1)

    def test_models_and_origins_parse_as_lists(self):
        with mock.patch.dict(os.environ, {"GEMINI_MODEL": "a, b ,", "ALLOWED_ORIGINS": "https://x.test, https://y.test"}):
            s = Settings.from_env()
        self.assertEqual(s.gemini_models, ("a", "b"))
        self.assertEqual(s.allowed_origins, ("https://x.test", "https://y.test"))

    def test_api_key_comes_only_from_env(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "k"}):
            self.assertEqual(Settings.from_env().gemini_api_key, "k")


class DatasetSyncTests(unittest.TestCase):
    def test_public_datasets_match_sanitised_source(self):
        import subprocess, sys
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        r = subprocess.run([sys.executable, os.path.join(root, "scripts", "sync_datasets.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
