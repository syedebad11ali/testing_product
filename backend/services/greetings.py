"""Instant replies for greetings (no model call needed)."""
from backend.records.text import norm


GREETINGS = ("hi", "hii", "hello", "helo", "hey", "salam", "salaam", "assalam", "assalamualaikum", "assalamu",
             "aoa", "as salam", "good morning", "good afternoon", "good evening", "hola", "namaste")


def is_greeting(text):
    n = norm(text)
    return bool(n) and len(n.split()) <= 5 and any(n == g or n.startswith(g + " ") for g in GREETINGS)


def greeting_reply(text):
    n = norm(text)
    salam = any(n.startswith(g) for g in ("salam", "salaam", "assalam", "as salam", "aoa"))
    return (("Wa alaikum assalam! " if salam else "Hello! ") + "👋 I'm the Property Assistant. I can estimate prices, "
            "compare areas and search our property records. What would you like to know?")

