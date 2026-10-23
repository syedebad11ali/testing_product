"""Gemini function-calling tools. Fresh closures per request so `calls` records what was used."""
import functools
import logging

log = logging.getLogger("chatbot")


def make_tools(store):
    """Fresh tool functions per request; `calls` records which ones Gemini used."""
    calls = []

    def guard(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            calls.append(fn.__name__)
            try:
                return fn(*a, **k)
            except Exception as e:  # tool errors go back to the model, not the user
                log.exception("tool %s failed", fn.__name__)
                return {"error": f"{type(e).__name__}: {e}"}
        return wrapper

    @guard
    def predict_price(area: str, property_type: str, block: int = 0, rooms: int = 0,
                      forecast_years: int = 0, annual_appreciation_pct: float = 5.0) -> dict:
        """Estimate a property's price with the trained model (falls back to historical averages).
        area and property_type are required. Use block=0 / rooms=0 when unknown.
        Set forecast_years > 0 only if the user asks for a future price."""
        return store.predict(area, property_type, block, rooms, forecast_years, annual_appreciation_pct)

    @guard
    def market_stats(group_by: str = "", area: str = "", property_type: str = "", block: int = 0) -> dict:
        """Price statistics (count, min, median, average, max). Optional filters: area, property_type, block.
        group_by can be 'area', 'property_type' or 'block' to compare groups (sorted cheapest first);
        use it for 'cheapest/most expensive area', 'compare types', etc."""
        return store.stats(group_by, area, property_type, block)

    @guard
    def search_properties(area: str = "", property_type: str = "", block: int = 0, min_price: float = 0,
                          max_price: float = 0, min_rooms: int = 0, max_rooms: int = 0,
                          sort: str = "price_asc", limit: int = 5) -> dict:
        """List matching properties from the records. Prices are in PKR (1 lakh = 100000, 1 crore = 10000000).
        Use 0 for any filter that is not needed. sort is 'price_asc' or 'price_desc'. limit is at most 10."""
        return store.search(area, property_type, block, min_price, max_price, min_rooms, max_rooms, sort, limit)

    @guard
    def get_property(property_id: str) -> dict:
        """Look up one property by ID, e.g. 'DEMO-KPT-8103' or just '8103'. Never returns owner names."""
        return store.get_property(property_id)

    @guard
    def dataset_overview() -> dict:
        """What the data covers: record counts, areas, property types, block range, unpriced types, model accuracy."""
        return store.overview()

    return [predict_price, market_stats, search_properties, get_property, dataset_overview], calls
