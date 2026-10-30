"""Orchestrates one chat turn: intent routing -> specialist (data/advisor) or Gemini -> structured reply.

Response contract (``docs/API.md``): ``reply, source, from_data`` (legacy, the widget uses these)
plus ``intent, specialist, chips[], cards[], actions[], memory, message_id``.
Chips and cards are structured data; the UI never parses the reply text to build them.
"""
import logging
import re
import threading
import uuid
from collections import OrderedDict

from backend.records.store import Store
from backend.records.text import norm
from backend.services import advisor
from backend.services.ai.agents_engine import AgentsEngine
from backend.services.ai.errors import classify_error, redact
from backend.services.gemini_engine import GeminiEngine
from backend.services.greetings import greeting_reply, is_greeting
from backend.services.grounding import needs_search_grounding
from backend.services.memory import Memory, update as update_memory
from backend.services.offline_engine import OfflineEngine
from backend.services.router import SPECIALISTS, classify

log = logging.getLogger("chatbot")

MAX_SESSIONS = 500          # oldest sessions are evicted beyond this
MAX_HISTORY_MESSAGES = 20   # per-session context kept in memory
MAX_TURNS = 2000            # message ids remembered so feedback can be tied to a question
STARTERS = ["Prices in Gulshan", "Show 3 plots under 3 crore", "Compare DHA and Clifton", "How does verification work?"]
LAWYER_NOTE = "\n\n*General guidance only. For legal, tax or financial decisions please consult a qualified lawyer or adviser.*"
STATIC = {
    "document_verification": ("**Document Verifier.** You can check a sale deed, allotment letter, NOC and more with *Verify Your Document* (photo, upload or manual entry), "
                              "and test an owner name against the registry in *Owner Verification*. Results are indicative, not proof of ownership.", "dataset"),
    "buying_process": ("**General knowledge, not live data.** A typical purchase in Karachi: agree a price, verify the seller's title documents and the property's tax and utility status, "
                       "sign an agreement, pay the transfer taxes and fees, then register the transfer with the sub-registrar. Exact duties change, so confirm them first." + LAWYER_NOTE, "general"),
    "account": ("**Account Help.** You can log in or create an account from the login page. Forgotten passwords cannot be reset online yet; contact us and we will help.", "dataset"),
    "small_talk": ("Happy to help! Ask me about prices, areas or listings whenever you like.", "general"),
    "off_topic": ("That's outside what I know best, so I'll keep it brief and steer back: I'm at my best with Karachi property prices, areas and listings. What would you like to explore?", "general"),
}


def _a(word):
    """'a house' / 'an apartment'."""
    w = word.lower()
    return f"{'an' if w[0] in 'aeiou' else 'a'} {w}"


class ChatService:
    def __init__(self, settings):
        self.settings = settings
        self.store = Store(settings.data_dir, settings.model_path)
        self.gemini = GeminiEngine(settings)
        self.agents = AgentsEngine(settings)   # opt-in (AI_ENGINE=agents); never enabled by default
        self.offline = OfflineEngine(self.store)
        self.sessions = OrderedDict()     # sid -> {"history": [...], "memory": Memory}
        self.turns = OrderedDict()        # message_id -> {"intent", "question", "answered"}
        self.lock = threading.Lock()

    def _session(self, sid):
        with self.lock:
            s = self.sessions.setdefault(sid, {"history": [], "memory": Memory()})
            self.sessions.move_to_end(sid)
            while len(self.sessions) > MAX_SESSIONS:
                self.sessions.popitem(last=False)
            return s

    # ---- helpers -----------------------------------------------------------
    def _chip(self, label, message=None, url=None):
        return {"label": label, **({"message": message} if message else {}), **({"url": url} if url else {})}

    def _starter_chips(self):
        return [self._chip(s, s) for s in STARTERS]

    def _top_areas(self, ptype="", k=4):
        d = self.store.df[self.store.df.type == ptype] if ptype else self.store.df
        return [self.store.area_names[a] for a in d.area_key.value_counts().index[:k]]

    def _help_text(self):
        """What the assistant can do, with the real size of the data (no model call, nothing invented)."""
        o = self.store.overview()
        return (f"**Property Assistant.** I answer from the property data on this site ({o['total_records']} records across {len(o['areas'])} Karachi areas) and can:\n"
                "- estimate a price (*price of a house in DHA, block 5*)\n- compare areas (*cheapest area for apartments*, *compare DHA and Clifton*)\n"
                "- find listings (*plots under 3 crore in Malir*)\n- explain document and owner verification\n- hand you to our team to book a viewing\n"
                "I can't share owner details, and estimates are indicative, not valuations.")

    def _overview_text(self, message):
        """Counts straight from the store: the whole dataset, or one area / type / block when the question names it."""
        t = norm(message)
        area, ptype = self.offline._area(t), self.offline._type(t)
        blk = re.search(r"\bblock\s*(\d+)\b", t)
        a_txt, t_txt = (self.store.area_names[area] if area else ""), (self.store.type_names[ptype] if ptype else "")
        if not (a_txt or t_txt or blk):
            o = self.store.overview()
            by_type = ", ".join(f"{n}: {c}" for n, c in sorted(o["records_by_type"].items(), key=lambda kv: -kv[1]))
            note = f" No prices are listed for: {', '.join(o['types_without_prices'])}." if o["types_without_prices"] else ""
            return (f"**From the dataset.** I have {o['total_records']} records ({o['priced_records']} with a listed price) across {len(o['areas'])} areas.\n"
                    f"By type: {by_type}.{note}\nAreas: {', '.join(o['areas'])}.\nAsk about an area, e.g. *how many houses in DHA*, or *prices in Gulshan*.")
        r = self.store.stats("", a_txt, t_txt, int(blk.group(1)) if blk else 0)
        if "error" in r:
            return f"{r['error']} Try an area from the dataset, e.g. *how many houses in DHA*."
        o = r["overall"]
        what = " ".join(x for x in (t_txt.lower() + "s" if t_txt else "properties", f"in {a_txt}" if a_txt else "", f"(block {blk.group(1)})" if blk else "") if x)
        if not o["records"]:
            return f"**From the dataset.** I have no {what}."
        if not o["priced_records"]:
            return f"**From the dataset.** I have {o['records']} {what}, but none has a listed price."
        return (f"**From the dataset.** I have {o['records']} {what} ({o['priced_records']} priced). Median {o['median']}, average {o['average']}, "
                f"ranging from {o['min']} to {o['max']}. Ask me to estimate a price or list a few examples.")

    def _llm_or_offline(self, session, message, intent):
        mem = session["memory"]
        model_message = f"[Remembered from this chat: {mem.summary()}]\n{message}" if mem.summary() else message
        live = needs_search_grounding(self.store, message)
        engines = {"agents": self.agents, "gemini": self.gemini}
        for name in self.settings.ai_order:          # AI_ORDER: first enabled engine that answers wins
            eng = engines.get(name)
            if eng is None or not eng.enabled or (name == "agents" and live):   # live questions need Gemini's Google Search
                continue
            try:
                if name == "agents":
                    text, calls = self.agents.answer(self.store, session["history"], model_message)
                    return text, self.agents.provider, bool(calls)
                if live:
                    return self.gemini.answer_with_search(session["history"], model_message), "gemini", False
                text, calls = self.gemini.answer(self.store, session["history"], model_message)
                return text, "gemini", bool(calls)
            except Exception as e:  # noqa: BLE001 - try the next engine, then the offline engine
                kind = getattr(e, "reason", None) or classify_error(e)
                session["reason"] = kind
                eng.last_error = f"{kind}: {type(e).__name__}: {redact(e)[:200]}"
                log.warning("%s engine failed [%s], trying the next: %s", name, kind, redact(e))
        if not self.gemini.enabled and not self.agents.enabled:
            session["reason"] = session.get("reason") or "no_key"
        if live and not self.gemini.enabled:
            return ("Live answers and estimates for areas outside the property records require Gemini. Configure GEMINI_API_KEY in your hosting environment; "
                    "I can still answer questions using the listed areas."), "offline", False
        return None

    # ---- specialists ---------------------------------------------------------
    def _find(self, intent, message, mem):
        ptype = "Plot" if intent.name == "find_plot" else mem.property_type
        if not (mem.area or mem.budget_max):
            noun = "plots" if ptype == "Plot" else "properties"
            chips = [self._chip(a, f"Show {noun} in {a}" + (f" under {mem.budget_max / 1e7:g} crore" if mem.budget_max else "")) for a in self._top_areas(ptype)]
            return {"text": f"Happy to suggest {noun}. Which area are you considering, and roughly what budget? (Pick an area below or just tell me both.)",
                    "cards": [], "chips": chips, "from_data": False}
        cards, info = advisor.suggest(self.store, mem.area, ptype, mem.budget_max)
        label = f"{ptype.lower()}s" if ptype else "properties"
        where = f" in {mem.area}" if mem.area else ""
        under = f" under {advisor.short_money(mem.budget_max)}" if mem.budget_max else ""
        if not cards:
            alt = [a for a in self._top_areas(ptype, 5) if a != mem.area][:3]
            chips = [self._chip(f"Try {a}", f"Show {label}{' in ' + a}{under}") for a in alt]
            if mem.budget_max:
                chips.insert(0, self._chip("Raise budget 30%", f"Show {label}{where} under {advisor.short_money(mem.budget_max * 1.3)}"))
            return {"text": f"I couldn't find {label}{where}{under} in the property records. Here is what I can do next: stretch the budget a little or look at nearby options.",
                    "cards": [], "chips": chips, "from_data": True}
        stretch = " Nothing fit the budget exactly, so these are up to 30% above it." if info.get("relaxed") else ""
        text = (f"**From the property records:** here are {len(cards)} {label}{where}{under} picked for value and clean status.{stretch} "
                "Tap a card to open the full listing. These are dataset entries (demo data), not offers.")
        ids = " and ".join(c["id"] for c in cards)
        cheaper = min(self.store.df[self.store.df.property_id.isin([c["id"] for c in cards])].price)
        chips = [self._chip(f"Compare these {label}", f"Compare {ids}"),
                 self._chip("Show cheaper ones", f"Show {label}{where} under {int(cheaper * 0.8 / 1e5)} lakh"),
                 self._chip("Estimate a price", f"Estimate price of a {(ptype or 'house').lower()}{where}"),
                 self._chip("Talk to an agent", "I want to talk to an agent")]
        return {"text": text, "cards": cards, "chips": chips, "from_data": True}

    @staticmethod
    def _block_followup(message, mem):
        """A bare "block 10" / "10" right after the chat has settled on an area continues that question (from the reference
        bot's per-session slots). Returns a self-contained rewrite of the message, or None when it is not such a follow-up."""
        m = re.fullmatch(r"(?:block\s*)?(\d{1,3})", norm(message))
        if not m or not mem.area:
            return None
        n = int(m.group(1))
        if mem.property_type:
            return f"price of {_a(mem.property_type)} in {mem.area} block {n}"
        return f"how many properties in {mem.area} block {n}"

    def _price(self, message, mem):
        area_known = bool(mem.area)
        if area_known and not mem.property_type:
            o = advisor.area_overview(self.store, mem.area)
            if o:
                types = [t["type"] for t in o["per_type"]][:3]
                other = "Clifton" if o["area"] != "Clifton" else "DHA"
                follow = "\n\nTo narrow this down: which property type are you after, and are you buying or renting?"
                chips = [self._chip(f"Estimate {_a(t)}", f"Estimate price of {_a(t)} in {o['area']}") for t in types] + [self._chip(f"Compare with {other}", f"Compare {o['area']} and {other}")]
                return {"text": advisor.price_overview_text(o) + follow, "cards": [], "chips": chips, "from_data": True}
        if area_known and mem.property_type:
            query = f"{message} {mem.property_type} in {mem.area}" if mem.property_type.lower() not in message.lower() or mem.area.lower() not in message.lower() else message
            if mem.block and "block" not in query.lower():
                query += f" block {mem.block}"
            stats = self.store.stats("", mem.area, mem.property_type, mem.block or 0)["overall"]
            head = ""
            if stats.get("priced_records"):
                head = (f"**From the dataset:** {mem.property_type} in {mem.area}{f', block {mem.block}' if mem.block else ''}: {stats['min']} to {stats['max']}, median {stats['median']}, "
                        f"{stats['priced_records']} priced listings" + (" (small sample)" if stats["priced_records"] < 10 else "") + ".\n\n")
            return {"text": head + "**Model estimate** (not a valuation)\n" + self.offline.answer(query), "cards": [], "from_data": True,
                    "chips": [self._chip("Compare with DHA", f"Compare {mem.area} and DHA"), self._chip(f"Show {mem.property_type.lower()}s here", f"Show {mem.property_type.lower()}s in {mem.area}"),
                              self._chip("Estimate my property", "Estimate my property"), self._chip("Talk to an agent", "I want to talk to an agent")]}
        return None

    # ---- main entry ------------------------------------------------------------
    def attach_store(self, store):
        """Optional persistence (``DbChatStore``) for cookie-identified conversations."""
        self.chat_store = store

    def _hydrate(self, sid, session):
        """Fill an empty in-process session from the persistent store (after a refresh / cold start)."""
        store = getattr(self, "chat_store", None)
        if store is None or session["history"] or session["memory"].as_dict():
            return
        saved = store.load(sid)
        if saved:
            session["history"][:] = [m for m in saved["history"] if isinstance(m, dict) and m.get("role") in ("user", "model") and isinstance(m.get("text"), str)][-MAX_HISTORY_MESSAGES:]
            allowed = {k: v for k, v in saved["memory"].items() if k in ("area", "property_type", "budget_max", "purpose", "block")}
            session["memory"] = Memory(**allowed)

    def snapshot(self, sid, persisted=True):
        """``{history, memory}`` for restoring the chat window after a refresh."""
        session = self._session(sid)
        if persisted:
            self._hydrate(sid, session)
        return {"history": list(session["history"]), "memory": session["memory"].as_dict()}

    def reply(self, sid, message, reset=False, persist=False):
        session = self._session(sid)
        if reset:
            session["history"].clear(); session["memory"] = Memory()
            if persist and getattr(self, "chat_store", None):
                self.chat_store.delete(sid)
        elif persist:
            self._hydrate(sid, session)
        mem = session["memory"]
        session["reason"] = None
        typed = message                                   # what the user actually wrote (history, analytics)
        message = self._block_followup(message, mem) or message
        greeting = is_greeting(message)
        intent = SPECIALISTS["small_talk"] if greeting else classify(message)
        if intent.name not in ("small_talk", "off_topic", "account", "help"):
            update_memory(mem, self.offline, message)
        out = {"cards": [], "chips": [], "actions": [], "from_data": False}
        source = "offline"
        if greeting:
            out.update(text=greeting_reply(message), chips=self._starter_chips()); source = "greeting"
        elif intent.name == "compare_listings":
            out["text"], out["cards"] = advisor.compare_ids(self.store, message); out["from_data"] = True
        elif intent.name == "help":
            out["text"], out["from_data"] = self._help_text(), True
        elif intent.name == "dataset_overview":
            out["text"], out["from_data"] = self._overview_text(message), True
        elif intent.name in ("find_plot", "find_property"):
            out.update(self._find(intent, message, mem))
        elif intent.name == "price_estimate" and (spec := self._price(message, mem)):
            out.update(spec)
        elif intent.name in ("document_verification", "buying_process", "account", "small_talk", "off_topic", "book_viewing"):
            llm = self._llm_or_offline(session, message, intent) if intent.name in ("buying_process", "off_topic") else None
            if llm:
                out["text"], source, out["from_data"] = llm
                if intent.name == "buying_process": out["text"] += LAWYER_NOTE
            elif intent.name == "book_viewing":
                summary = f"I'm interested in {mem.summary() or 'Karachi properties'}."
                out["actions"] = advisor.handoff_actions(self.settings, summary)
                out["text"] = ("**Viewing Coordinator.** I can hand you to our team with a summary of this chat." if out["actions"] else
                               "**Viewing Coordinator.** Direct contact channels are not configured on this site yet, so please use the contact details published on the website. I can keep helping with prices and listings meanwhile.")
            else:
                out["text"], kind = STATIC[intent.name]; out["from_data"] = kind == "dataset"
            if intent.name == "document_verification":
                out["actions"] = [{"type": "link", "label": "Verify a document", "url": "/#verify-document"}, {"type": "link", "label": "Owner Verification", "url": "/#owner-verification"}]
            elif intent.name == "account":
                out["actions"] = [{"type": "link", "label": "Go to login", "url": "/login"}]
        else:
            llm = self._llm_or_offline(session, message, intent)
            if llm:
                out["text"], source, out["from_data"] = llm
            else:
                augmented = message
                if mem.area and not self.offline._area(message.lower()): augmented += f" {mem.area}"
                if mem.property_type and not self.offline._type(message.lower()): augmented += f" {mem.property_type}"
                out["text"], out["from_data"] = self.offline.answer(augmented), True
                if intent.name == "market_compare": out["text"] = "**From the dataset**\n" + out["text"]
        if not out["chips"]:
            out["chips"] = self._starter_chips()
        history = session["history"]
        history += [{"role": "user", "text": typed}, {"role": "model", "text": out["text"]}]
        del history[:-MAX_HISTORY_MESSAGES]
        if persist and getattr(self, "chat_store", None):
            self.chat_store.save(sid, history, mem.as_dict())
        message_id = uuid.uuid4().hex
        answered = not re.search(r"couldn't find|No matching|not in the property data|can't estimate|outside what I know", out["text"])
        with self.lock:
            self.turns[message_id] = {"intent": intent.name, "question": typed[:300], "answered": answered}
            while len(self.turns) > MAX_TURNS: self.turns.popitem(last=False)
        return {"reply": out["text"], "source": source, "from_data": out["from_data"], "intent": intent.name,
                "specialist": intent.specialist, "chips": out["chips"][:5], "cards": out["cards"], "actions": out["actions"],
                "memory": mem.as_dict(), "message_id": message_id, "reason": session["reason"]}

    def welcome(self, first_name="", last_property_id="", has_history=False):
        """Returning-visitor greeting. A first name only for signed-in users; anonymous visitors get a
        generic "Welcome back" with a one-tap chip for their last viewed property (built from the dataset)."""
        text = f"Welcome back, {first_name}! 👋" if first_name else "Welcome back! 👋"
        chips = []
        if last_property_id:
            found = self.store.get_property(last_property_id).get("matches")
            if found:
                row = found[0]
                chips.append(self._chip(f"Continue with {row['property_type'].lower()} in {row['area']}", message=f"Tell me more about {row['property_id']}"))
        if has_history:
            text += " Your conversation is still here."
        return {"text": text, "chips": chips or self._starter_chips()[:2]}

    def turn_info(self, message_id):
        with self.lock:
            return dict(self.turns.get(message_id) or {})
