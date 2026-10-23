"""Decides when a question needs live Google Search grounding instead of local records."""
import re

from backend.records.text import norm


def needs_search_grounding(store, message):
    text = norm(message)
    if re.search(r"\b(weather|forecast|temperature|rain|sunny|latest news|current news|right now|today)\b", text):
        return True
    if not re.search(r"\b(price|cost|estimate|worth|how much|value|predict|valuation)\b", text):
        return False
    location = re.search(r"\b(?:in|around|near|outside|within|at)\s+(.+)", text)
    if not location:
        return False
    area_query = re.split(
        r"\b(?:for|with|under|below|above|over|between|house|home|apartment|flat|plot|portion|commercial|"
        r"property|bed|bedroom|bedrooms|room|rooms|bath|bathroom|bathrooms|block)\b",
        location.group(1), maxsplit=1,
    )[0].strip()
    if not area_query:
        return False
    area, candidates = store.resolve_area(area_query)
    return not area and not candidates

