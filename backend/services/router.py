"""Intent router: classify a message and name the specialist that handles it.

Rule-based on purpose (fast, free, testable). To add a specialist: add an ``Intent`` to
``SPECIALISTS``, a rule in ``classify`` and (optionally) a handler in ``advisor.py``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.records.text import norm


@dataclass(frozen=True)
class Intent:
    name: str
    specialist: str


SPECIALISTS = {i.name: i for i in (
    Intent("price_estimate", "Price Estimator"),
    Intent("market_compare", "Market Analyst"),
    Intent("find_plot", "Plot Finder"),
    Intent("find_property", "Property Finder"),
    Intent("compare_listings", "Market Analyst"),
    Intent("document_verification", "Document Verifier"),
    Intent("buying_process", "Buying Guide"),
    Intent("book_viewing", "Viewing Coordinator"),
    Intent("help", "Property Assistant"),
    Intent("dataset_overview", "Market Analyst"),
    Intent("account", "Account Help"),
    Intent("small_talk", "Property Assistant"),
    Intent("off_topic", "Property Assistant"),
)}

_ID = re.compile(r"\bdemo[\s-]*kpt[\s-]*\d+\b", re.I)
_REAL_ESTATE = r"(propert|plot|land|house|home|flat|apartment|portion|commercial|shop|office|price|rate|area|block|dha|clifton|gulshan|malir|karachi|crore|lakh|rent|buy|sell|invest|bahria|scheme|nazimabad|saddar|korangi|johar|jauhar|pechs|fb area)"
_RULES = (
    # Tight, deterministic rules (added from the reference project's offline help/stats answers): capability questions and
    # "how many / summary of the data" questions are answered from the data, never by the language model.
    ("help", r"^(help|help me|commands|menu|options)\W*$|\b(what can (you|i) (do|ask|help)|what do you do|how can you help|how do(es)? (this|you) work|what are your (features|capabilities))\b"),
    ("dataset_overview", r"\bhow many (properties|property|listings?|records|houses?|plots?|apartments?|flats?|portions?|commercials?|areas|types)\b"
                         r"|\b(summary|summari[sz]e|overview|statistics|stats) (of )?(the )?(data|dataset|records|listings|market)\b|\bwhat data do you have\b"
                         r"|\b(which|what) areas (do you|are you|are there|are covered|you cover)\b|\bwhat areas\b"),
    ("account", r"\b(log ?in|sign ?in|sign ?up|password|account|register|forgot)\b"),
    ("book_viewing", r"\b(view(ing)?|visit|appointment|book|talk to|speak to|human|agent|call me|whatsapp|contact)\b"),
    ("document_verification", r"\b(verify|verification|document|sale deed|registry|fake|genuine|authentic|ownership proof|noc)\b"),
    ("buying_process", r"\b(how (do|to|can) (i|we) (buy|purchase|sell|transfer)|buying process|stamp duty|tax(es)?|transfer|registration|legal|lawyer|mortgage|loan|installment|cvt|ftc|process)\b"),
    ("small_talk", r"^(thanks|thank you|shukriya|ok|okay|bye|goodbye|great|nice|cool)\W*$|\bhow are you\b"),
)


def classify(text: str) -> Intent:
    t = norm(text)
    if len(_ID.findall(text)) >= 2 or (re.search(r"\bcompare\b", t) and len(_ID.findall(text)) >= 1):
        return SPECIALISTS["compare_listings"]
    for name, pattern in _RULES:
        if re.search(pattern, t):
            return SPECIALISTS[name]
    if re.search(r"\b(plots?|land)\b", t) and re.search(r"\b(show|find|suggest|recommend|available|looking|want|need|buy|under|below|budget|best|good|options?)\b", t):
        return SPECIALISTS["find_plot"]
    if re.search(r"\b(compare|versus|vs|cheapest|costliest|most expensive|lowest|highest|median|average|trend|which area)\b", t):
        return SPECIALISTS["market_compare"]
    if re.search(r"\b(price|prices|cost|estimate|worth|how much|value|rate|rates|predict)\b", t):
        return SPECIALISTS["price_estimate"]
    if re.search(r"\b(show|find|list|search|available|under|below|budget|looking for|want|need|houses?|apartments?|flats?|portions?|plots?)\b", t):
        return SPECIALISTS["find_property"]
    return SPECIALISTS["find_property"] if re.search(_REAL_ESTATE, t) else SPECIALISTS["off_topic"]
