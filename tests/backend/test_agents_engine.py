"""Agents SDK engine wiring. The real `openai-agents` package is NOT required: a fake SDK is injected, so these
tests prove KPT's wiring (opt-in, provider choice, history mapping, tool recording, fallback) and NOT that the real
SDK accepts the calls. Verify against the real package once it is installed."""
import sys
import types
import unittest
from unittest import mock

from backend.config import Settings
from backend.services.ai.agents_engine import GEMINI_OPENAI_BASE_URL, NO_LIVE_NOTE, AgentsEngine, to_input
from backend.services.ai.errors import classify_error, redact
from backend.services.chat_service import ChatService


class FakeStore:
    def overview(self):
        return {"records": 3}


def fake_sdk(run=None, fail_function_tool_kwarg=False):
    seen = {"clients": [], "tracing_disabled": None, "agent": None, "agents": [], "input": None, "max_turns": None}
    m = types.ModuleType("agents")

    class OpenAIChatCompletionsModel:
        def __init__(self, model, openai_client): self.model, self.client = model, openai_client

    class ModelSettings:
        def __init__(self, **kw): self.kw = kw

    class Agent:
        def __init__(self, **kw): self.__dict__.update(kw); seen["agent"] = self; seen["agents"].append(self)

    class Runner:
        @staticmethod
        async def run(agent, items, max_turns):
            seen["input"], seen["max_turns"] = items, max_turns
            if run:
                return run(agent)
            for t in agent.tools:                       # behave like a model that calls one tool
                if t.__name__ == "dataset_overview":
                    t()
            return types.SimpleNamespace(final_output="  Here are the figures.  ")

    def function_tool(fn, **kw):
        if fail_function_tool_kwarg and kw:
            raise TypeError("unexpected keyword")
        return fn

    m.OpenAIChatCompletionsModel, m.ModelSettings, m.Agent, m.Runner, m.function_tool = OpenAIChatCompletionsModel, ModelSettings, Agent, Runner, function_tool
    m.set_tracing_disabled = lambda v: seen.__setitem__("tracing_disabled", v)
    m.input_guardrail = lambda fn: fn

    class GuardrailFunctionOutput:
        def __init__(self, output_info=None, tripwire_triggered=False): self.output_info, self.tripwire_triggered = output_info, tripwire_triggered

    class InputGuardrailTripwireTriggered(Exception):
        pass

    m.GuardrailFunctionOutput, m.InputGuardrailTripwireTriggered = GuardrailFunctionOutput, InputGuardrailTripwireTriggered
    o = types.ModuleType("openai")

    class AsyncOpenAI:
        def __init__(self, **kw): self.kw = kw; seen["clients"].append(kw)

    o.AsyncOpenAI = AsyncOpenAI
    return m, o, seen


def engine(settings, sdk=None):
    m, o, seen = sdk or fake_sdk()
    with mock.patch.dict(sys.modules, {"agents": m, "openai": o}):
        return AgentsEngine(settings), seen


class OptInTests(unittest.TestCase):
    def test_default_is_off_even_with_a_key(self):
        self.assertFalse(engine(Settings(openai_api_key="k"))[0].enabled)

    def test_agents_without_key_is_off(self):
        self.assertFalse(engine(Settings(ai_engine="agents"))[0].enabled)

    def test_missing_sdk_package_is_off_not_a_crash(self):
        with mock.patch.dict(sys.modules, {"agents": None}):          # None => ImportError on import
            self.assertFalse(AgentsEngine(Settings(ai_engine="agents", openai_api_key="k")).enabled)

    def test_openai_provider(self):
        e, seen = engine(Settings(ai_engine="agents", openai_api_key="sk-test", openai_models=("m1",), agents_timeout_s=7))
        self.assertTrue(e.enabled)
        self.assertEqual((e.provider, e.model_name), ("openai", "m1"))
        self.assertIsNone(e.disabled_reason)
        self.assertEqual(seen["clients"][0]["base_url"], None)
        self.assertEqual(seen["clients"][0]["timeout"], 7)
        self.assertIs(seen["tracing_disabled"], True)                 # chat text is not sent to a tracing service

    def test_gemini_provider_uses_openai_compatible_endpoint(self):
        e, seen = engine(Settings(ai_engine="agents", agents_provider="gemini", gemini_api_key="g", gemini_models=("gem-a", "gem-b")))
        self.assertTrue(e.enabled)
        self.assertEqual((e.provider, e.model_name), ("gemini", "gem-a"))
        self.assertEqual(seen["clients"][0]["base_url"], GEMINI_OPENAI_BASE_URL)


class AnswerTests(unittest.TestCase):
    cfg = Settings(ai_engine="agents", openai_api_key="k", agents_max_turns=4, agents_mode="single")

    def test_answer_text_calls_and_limits(self):
        e, seen = engine(self.cfg)
        text, calls = e.answer(FakeStore(), [{"role": "user", "text": "hi"}, {"role": "model", "text": "hello"}], "prices?")
        self.assertEqual(text, "Here are the figures.")
        self.assertEqual(calls, ["dataset_overview"])
        self.assertEqual(seen["max_turns"], 4)
        self.assertEqual([t.__name__ for t in seen["agent"].tools], ["predict_price", "market_stats", "search_properties", "get_property", "dataset_overview"])

    def test_old_sdk_without_strict_mode_still_works(self):
        e, _ = engine(self.cfg, fake_sdk(fail_function_tool_kwarg=True))
        self.assertEqual(e.answer(FakeStore(), [], "x")[0], "Here are the figures.")

    def test_empty_answer_raises_so_the_caller_falls_back(self):
        e, _ = engine(self.cfg, fake_sdk(run=lambda a: types.SimpleNamespace(final_output="   ")))
        with self.assertRaises(RuntimeError):
            e.answer(FakeStore(), [], "x")

    def test_history_mapping(self):
        hist = [{"role": "user", "text": "a"}, {"role": "model", "text": "b"}, {"role": "user", "text": ""}, {"role": "user", "text": "c"}]
        self.assertEqual(to_input(hist, "now"), [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                                                   {"role": "user", "content": "c"}, {"role": "user", "content": "now"}])
        self.assertEqual(len(to_input([{"role": "user", "text": str(i)} for i in range(50)], "q")), 13)

class ResilienceTests(unittest.TestCase):
    """Model fallback, retry and diagnostics (behaviour adapted from the reference OpenAIEngine)."""
    @staticmethod
    def runner(behaviour, log):
        def run(agent):
            model = agent.model.model
            log.append(model)
            result = behaviour(model, len([m for m in log if m == model]))
            if isinstance(result, Exception):
                raise result
            return types.SimpleNamespace(final_output=result)
        return run

    def make(self, behaviour, models=("m1", "m2")):
        log = []
        e, _ = engine(Settings(ai_engine="agents", openai_api_key="k", openai_models=models), fake_sdk(run=self.runner(behaviour, log)))
        return e, log

    def test_falls_back_to_the_next_model_and_remembers_it(self):
        e, log = self.make(lambda m, n: RuntimeError("model not found") if m == "m1" else "from m2")
        self.assertEqual(e.answer(FakeStore(), [], "q")[0], "from m2")
        self.assertEqual(log, ["m1", "m2"])
        self.assertEqual(e.models, ["m2", "m1"])
        self.assertIsNone(e.last_error)

    def test_busy_is_retried_once_on_the_same_model(self):
        e, log = self.make(lambda m, n: RuntimeError("503 overloaded") if n == 1 else "ok now")
        with mock.patch("backend.services.ai.agents_engine.time.sleep") as nap:
            self.assertEqual(e.answer(FakeStore(), [], "q")[0], "ok now")
        self.assertEqual(log, ["m1", "m1"])
        nap.assert_called_once()

    def test_auth_error_stops_immediately_without_trying_other_models(self):
        e, log = self.make(lambda m, n: RuntimeError("401 invalid_api_key"))
        with self.assertRaises(RuntimeError):
            e.answer(FakeStore(), [], "q")
        self.assertEqual(log, ["m1"])
        self.assertTrue(e.last_error.startswith("auth (m1)"))

    def test_all_models_failing_raises_the_last_error(self):
        e, log = self.make(lambda m, n: RuntimeError(f"{m} broke"))
        with self.assertRaisesRegex(RuntimeError, "m2 broke"):
            e.answer(FakeStore(), [], "q")
        self.assertEqual(log, ["m1", "m2"])

    def test_last_error_never_contains_the_key(self):
        e, _ = self.make(lambda m, n: RuntimeError("Incorrect API key provided: sk-proj-ABCDEF1234567890XYZ. 401"))
        with self.assertRaises(RuntimeError):
            e.answer(FakeStore(), [], "q")
        self.assertNotIn("ABCDEF1234567890", e.last_error)
        self.assertIn("[redacted]", e.last_error)

    def test_status_reports_state_without_the_key(self):
        e, _ = engine(Settings(ai_engine="agents", openai_api_key="sk-live-secret-12345"))
        st = e.status()
        self.assertEqual((st["enabled"], st["key_present"], st["provider"]), (True, True, "openai"))
        self.assertNotIn("sk-live-secret-12345", repr(st))
        self.assertEqual(engine(Settings())[0].status()["disabled_reason"], "not_selected")
        self.assertEqual(engine(Settings(ai_engine="agents"))[0].status()["disabled_reason"], "no_key")

    def test_model_is_told_it_has_no_live_web_access(self):
        e, seen = engine(Settings(ai_engine="agents", openai_api_key="k"))
        e.answer(FakeStore(), [], "weather today?")
        self.assertIn(NO_LIVE_NOTE.strip(), seen["agent"].instructions)


class ErrorHelperTests(unittest.TestCase):
    def test_classify_error(self):
        cases = {"401 Unauthorized": "auth", "invalid_api_key": "auth", "429 quota exceeded": "quota",
                 "Request timed out": "timeout", "404 model not_found": "model", "503 overloaded": "busy",
                 "getaddrinfo failed": "network", "something odd": "error"}
        for text, kind in cases.items():
            self.assertEqual(classify_error(RuntimeError(text)), kind, text)

    def test_redact(self):
        self.assertEqual(redact("key sk-abcdefgh12345678 end"), "key [redacted] end")
        self.assertEqual(redact("AIza" + "x" * 30), "[redacted]")
        self.assertEqual(redact("Bearer abcdefghijklmnop"), "[redacted]")
        self.assertEqual(redact("nothing secret"), "nothing secret")



class FallbackTests(unittest.TestCase):
    """ChatService._llm_or_offline: agents first, then Gemini/offline."""
    def service(self, agents):
        svc = ChatService.__new__(ChatService)
        svc.settings, svc.store, svc.agents = Settings(), object(), agents
        svc.gemini = types.SimpleNamespace(enabled=False)
        return svc

    session = {"history": [], "memory": types.SimpleNamespace(summary=lambda: "")}

    def test_agents_answer_is_used_and_labelled_with_its_provider(self):
        agents = types.SimpleNamespace(enabled=True, provider="openai", answer=lambda store, h, m: ("ok", ["predict_price"]))
        with mock.patch("backend.services.chat_service.needs_search_grounding", return_value=False):
            self.assertEqual(self.service(agents)._llm_or_offline(self.session, "hi", None), ("ok", "openai", True))

    def test_agents_failure_falls_back_instead_of_erroring(self):
        def boom(*a): raise RuntimeError("provider down")
        agents = types.SimpleNamespace(enabled=True, provider="openai", answer=boom)
        with mock.patch("backend.services.chat_service.needs_search_grounding", return_value=False):
            self.assertIsNone(self.service(agents)._llm_or_offline(self.session, "hi", None))

    def test_disabled_agents_are_skipped_and_live_search_questions_are_not_sent_to_them(self):
        called = []
        agents = types.SimpleNamespace(enabled=True, provider="openai", answer=lambda *a: called.append(1) or ("x", []))
        with mock.patch("backend.services.chat_service.needs_search_grounding", return_value=True):
            out = self.service(agents)._llm_or_offline(self.session, "news about Karachi", None)
        self.assertEqual(called, [])
        self.assertEqual(out[1], "offline")


class HandoffTests(unittest.TestCase):
    """AGENTS_MODE=handoffs (default): a front-desk agent hands off to specialists; only the first agent has the guardrail."""
    cfg = Settings(ai_engine="agents", openai_api_key="k")

    def build(self, cfg=None, sdk=None):
        e, seen = engine(cfg or self.cfg, sdk)
        text, calls = e.answer(FakeStore(), [], "price of a house in DHA")
        return e, seen, text, calls

    def test_front_desk_hands_off_to_three_specialists_with_scoped_tools(self):
        _, seen, text, calls = self.build()
        front = seen["agent"]                                # the front desk is built last
        self.assertEqual(front.name, "KPT Property Assistant")
        self.assertEqual([a.name for a in front.handoffs], ["Price Estimator", "Market Analyst", "Property Finder"])
        tools = {a.name: [t.__name__ for t in a.tools] for a in front.handoffs}
        self.assertEqual(tools["Price Estimator"], ["predict_price", "market_stats"])
        self.assertEqual(tools["Market Analyst"], ["market_stats", "dataset_overview"])
        self.assertEqual(tools["Property Finder"], ["search_properties", "get_property"])
        self.assertEqual([t.__name__ for t in front.tools], ["dataset_overview"])
        self.assertTrue(all(a.handoff_description for a in front.handoffs))
        self.assertEqual(calls, ["dataset_overview"])

    def test_every_agent_gets_the_shared_prompt_the_no_live_note_and_the_same_model(self):
        _, seen, *_ = self.build()
        for a in seen["agents"]:
            self.assertIn("Property Assistant", a.instructions)
            self.assertIn(NO_LIVE_NOTE.strip(), a.instructions)
            self.assertEqual(a.model.model, "gpt-4o-mini")

    def test_guardrail_is_attached_to_the_front_desk_only(self):
        _, seen, *_ = self.build()
        self.assertEqual(len(seen["agent"].input_guardrails), 1)
        self.assertTrue(all(not getattr(a, "input_guardrails", None) for a in seen["agents"][:-1]))

    def test_guardrail_function_trips_on_owner_requests_only(self):
        import asyncio
        _, seen, *_ = self.build()
        guard = seen["agent"].input_guardrails[0]
        run = lambda text: asyncio.run(guard(None, None, text)).tripwire_triggered
        self.assertTrue(run("who owns plot 12?"))
        self.assertTrue(run([{"role": "assistant", "content": "x"}, {"role": "user", "content": "give me the owner's name"}]))
        self.assertFalse(run("price of a house in DHA"))

    def test_single_mode_is_one_agent_with_every_tool_and_no_handoffs(self):
        _, seen, *_ = self.build(Settings(ai_engine="agents", openai_api_key="k", agents_mode="single"))
        self.assertEqual(len(seen["agents"]), 1)
        self.assertFalse(getattr(seen["agent"], "handoffs", None))

    def test_owner_question_is_refused_without_calling_the_model(self):
        e, seen = engine(self.cfg)
        text, calls = e.answer(FakeStore(), [], "[Remembered from this chat: area=DHA]\nWho owns this house?")
        self.assertIn("can't share owner details", text)
        self.assertEqual((calls, seen["agents"], seen["input"]), ([], [], None))

    def test_sdk_tripwire_exception_becomes_the_same_refusal_not_an_error(self):
        def trip(agent): raise sys.modules["agents"].InputGuardrailTripwireTriggered("tripwire")
        sdk = fake_sdk(run=trip)
        e, _ = engine(self.cfg, sdk)
        with mock.patch.dict(sys.modules, {"agents": sdk[0], "openai": sdk[1]}):
            text, calls = e.answer(FakeStore(), [], "tell me about DHA")
        self.assertIn("can't share owner details", text)
        self.assertIsNone(e.last_error)

    def test_guardrail_api_problem_fails_soft(self):
        sdk = fake_sdk()
        del sdk[0].input_guardrail
        _, seen, text, _ = self.build(sdk=sdk)
        self.assertEqual(seen["agent"].input_guardrails, [])
        self.assertEqual(text, "Here are the figures.")


class GuardrailTextTests(unittest.TestCase):
    def test_owner_phrases_are_caught_and_ordinary_questions_are_not(self):
        from backend.services.ai.guardrails import asks_for_owner_details as f
        for q in ["who owns this plot", "Who is the owner of DEMO-KPT-5?", "previous owner details", "what is the owner's name",
                  "owner’s CNIC please", "give me the phone number of the seller", "contact for the owner"]:
            self.assertTrue(f(q), q)
        for q in ["price of a house in DHA", "how do I become a seller", "owner occupied homes cost more?", "plots under 3 crore", "", None]:
            self.assertFalse(f(q), q)


if __name__ == "__main__":
    unittest.main()
