"""Behaviour taken from the reference chatbot (block follow-ups, clarifying questions, engine order, failure reasons).
Runs against the real ChatService, record store and price model; no AI engine is configured, so answers come from the data."""
import dataclasses
import types
import unittest
from unittest import mock

from backend.config import Settings
from backend.services.chat_service import ChatService
from backend.services.memory import Memory


def settings(**kw):
    return dataclasses.replace(Settings.from_env(), gemini_api_key=None, ai_engine="gemini", **kw)


class DataAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = ChatService(settings())

    def say(self, sid, text):
        return self.svc.reply(sid, text)

    def test_block_follow_up_continues_the_price_question(self):
        a = self.say("t-block", "price of a house in DHA")
        self.assertNotIn("block", a["memory"])
        b = self.say("t-block", "block 10")
        self.assertEqual((b["intent"], b["memory"]["block"]), ("price_estimate", 10))
        self.assertIn("block 10", b["reply"])
        self.assertIn("Estimated price", b["reply"])
        c = self.say("t-block", "11")                                  # a bare number works too, and replaces the block
        self.assertEqual(c["memory"]["block"], 11)
        self.assertNotEqual(b["reply"], c["reply"])

    def test_block_is_forgotten_when_the_area_changes(self):
        self.say("t-area", "price of a house in DHA")
        self.say("t-area", "block 10")
        r = self.say("t-area", "price of a house in Clifton")
        self.assertEqual(r["memory"].get("area"), "Clifton")
        self.assertNotIn("block", r["memory"])

    def test_a_bare_number_without_an_area_is_not_treated_as_a_block(self):
        r = self.say("t-bare", "10")
        self.assertNotIn("block", r["memory"])
        self.assertEqual(r["intent"], "off_topic")

    def test_history_keeps_what_the_user_typed_not_the_rewrite(self):
        self.say("t-hist", "price of a house in DHA")
        self.say("t-hist", "block 10")
        typed = [m["text"] for m in self.svc.snapshot("t-hist", persisted=False)["history"] if m["role"] == "user"]
        self.assertEqual(typed, ["price of a house in DHA", "block 10"])

    def test_missing_price_details_get_a_targeted_question(self):
        self.assertIn("Which area is the plot in?", self.say("t-q1", "price of a plot")["reply"])
        self.assertIn("Which area and property type?", self.svc.offline.answer("what is the price"))

    def test_rows_never_print_none_or_zero_rooms(self):
        text = self.svc.offline.answer("list plots in Malir")
        self.assertIn("Plot, Malir block", text)
        self.assertNotIn("None", text)
        self.assertNotIn("0 rooms", text)
        row = {"property_id": "X-1", "property_type": "Apartment", "area": "DHA", "block": None, "rooms": 1, "price": "PKR 1"}
        self.assertEqual(self.svc.offline._fmt_row(row), "- X-1: Apartment, DHA, 1 room, PKR 1")

    def test_stats_answers_say_which_way_they_are_sorted(self):
        self.assertTrue(self.svc.offline.answer("cheapest area for apartments").startswith("Cheapest areas"))
        self.assertTrue(self.svc.offline.answer("most expensive area for houses").startswith("Most expensive areas"))
        self.assertTrue(self.svc.offline.answer("compare areas for plots").startswith("Median prices, lowest first"))

    def test_block_memory_is_saved_and_restored_but_never_arbitrary_keys(self):
        m = Memory(area="DHA", property_type="House", block=10)
        self.assertEqual(m.as_dict()["block"], 10)
        self.assertIn("block=10", m.summary())
        self.assertNotIn("block", Memory().as_dict())


class EngineOrderTests(unittest.TestCase):
    """AI_ORDER and the reason reported when the AI could not answer."""
    def service(self, order, agents, gemini):
        svc = ChatService.__new__(ChatService)
        svc.settings, svc.store, svc.agents, svc.gemini = settings(ai_order=order), object(), agents, gemini
        return svc

    @staticmethod
    def engine(name, answer=None, fail=None, enabled=True):
        def run(*a):
            if fail:
                raise fail
            return answer, ["tool"]
        return types.SimpleNamespace(enabled=enabled, provider=name, answer=run, answer_with_search=lambda *a: "live", last_error=None)

    session = lambda self: {"history": [], "memory": Memory(), "reason": None}

    def ask(self, svc, session=None, live=False):
        session = session or self.session()
        with mock.patch("backend.services.chat_service.needs_search_grounding", return_value=live):
            return svc._llm_or_offline(session, "hello", None), session

    def test_default_order_tries_agents_first_and_gemini_first_when_configured(self):
        a, g = self.engine("openai", "from agents"), self.engine("gemini", "from gemini")
        self.assertEqual(self.ask(self.service(("agents", "gemini"), a, g))[0], ("from agents", "openai", True))
        self.assertEqual(self.ask(self.service(("gemini", "agents"), a, g))[0], ("from gemini", "gemini", True))

    def test_a_failing_engine_falls_through_to_the_next_and_the_failure_is_recorded(self):
        a, g = self.engine("openai", fail=RuntimeError("429 quota exceeded")), self.engine("gemini", "from gemini")
        out, session = self.ask(self.service(("agents", "gemini"), a, g))
        self.assertEqual(out[1], "gemini")
        self.assertEqual(session["reason"], "quota")
        self.assertTrue(a.last_error.startswith("quota:"))

    def test_all_engines_failing_returns_none_with_the_reason(self):
        a, g = self.engine("openai", fail=RuntimeError("503 overloaded")), self.engine("gemini", fail=RuntimeError("request timed out"))
        out, session = self.ask(self.service(("agents", "gemini"), a, g))
        self.assertIsNone(out)
        self.assertEqual(session["reason"], "timeout")          # the last failure wins

    def test_no_engine_configured_reports_no_key(self):
        out, session = self.ask(self.service(("agents", "gemini"), self.engine("openai", enabled=False), self.engine("gemini", enabled=False)))
        self.assertIsNone(out)
        self.assertEqual(session["reason"], "no_key")

    def test_live_questions_skip_agents_and_use_gemini_search(self):
        a, g = self.engine("openai", "from agents"), self.engine("gemini", "from gemini")
        self.assertEqual(self.ask(self.service(("agents", "gemini"), a, g), live=True)[0], ("live", "gemini", False))

    def test_unknown_names_in_ai_order_are_ignored(self):
        import os
        with mock.patch.dict(os.environ, {"AI_ORDER": "bogus, gemini"}):
            self.assertEqual(Settings.from_env().ai_order, ("gemini",))
        with mock.patch.dict(os.environ, {"AI_ORDER": "nonsense"}):
            self.assertEqual(Settings.from_env().ai_order, ("agents", "gemini"))


class GeminiStatusTests(unittest.TestCase):
    def test_status_explains_why_it_is_off_and_never_includes_the_key(self):
        from backend.services.gemini_engine import GeminiEngine
        off = GeminiEngine(settings()).status()
        self.assertEqual((off["enabled"], off["key_present"], off["disabled_reason"]), (False, False, "no_key"))
        on = GeminiEngine(dataclasses.replace(settings(), gemini_api_key="AIza-secret-key-1234567890123456"))
        self.assertNotIn("secret", repr(on.status()))
        self.assertTrue(on.status()["key_present"])


if __name__ == "__main__":
    unittest.main()
