"""Owner-privacy guardrail shared by the Agents SDK engine.

The record store never loads owner names, previous owners or owner IDs, so no tool can return them; this guardrail
makes the assistant *say so* instead of improvising, and stops the request before any model call. It is a plain
function so it can be unit-tested without the SDK, and so the engine can apply it even if the SDK's guardrail
API changes.
"""
import re

OWNER_REFUSAL = "Sorry, I can't share owner details. I can give the property's price, location, rooms and status instead."

_OWNER = re.compile(
    r"\bwho\s+(?:owns|owned|is\s+the\s+owner|was\s+the\s+owner)\b"
    r"|\b(?:previous|current|registered|original)\s+owner\b"
    r"|\bowner['’]?s?\s+(?:name|details?|info(?:rmation)?|cnic|id|phone|number|address|contact)\b"
    r"|\b(?:name|details?|cnic|phone(?:\s+number)?|contact|address)\s+(?:of|for)\s+(?:the\s+|its\s+|this\s+|that\s+)?(?:owner|seller)\b",
    re.I)


def asks_for_owner_details(text) -> bool:
    return bool(_OWNER.search(str(text or "")))
