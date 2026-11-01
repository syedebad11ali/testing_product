"""Error helpers for AI engines (classification adapted from the reference project's chatbot_core.classify_error)."""
import re

_SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,}|Bearer\s+[A-Za-z0-9._\-]{12,})")


def redact(text) -> str:
    """Remove anything that looks like an API key / bearer token before it is logged or shown to an admin."""
    return _SECRET.sub("[redacted]", str(text))


def classify_error(e) -> str:
    """Short machine-readable reason for a failed AI call: auth, quota, timeout, model, busy, network or error."""
    s = f"{type(e).__name__} {e}".lower()
    if any(x in s for x in ("api key", "api_key", "401", "403", "permission", "unauthenticated", "forbidden", "invalid_api_key")):
        return "auth"
    if any(x in s for x in ("429", "quota", "resource_exhausted", "rate limit", "rate_limit")):
        return "quota"
    if any(x in s for x in ("timeout", "timed out", "deadline")):
        return "timeout"
    if "404" in s or "not_found" in s or "not found" in s:
        return "model"
    if any(x in s for x in ("503", "500", "unavailable", "overloaded")):
        return "busy"
    if any(x in s for x in ("connect", "network", "name resolution", "getaddrinfo", "ssl")):
        return "network"
    return "error"
