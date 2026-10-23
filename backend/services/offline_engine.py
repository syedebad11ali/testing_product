"""Rule-based fallback engine: answers straight from the record store when Gemini is unavailable."""
import re

from backend.records.text import AREA_ALIASES, GENERIC_TOKENS, norm


class OfflineEngine:
    """Rule-based answers straight from the tools; used when Gemini is unavailable."""
    def __init__(self, store):
        self.s = store
        tok = {}
        for k in store.area_names:
            for t in k.split():
                if len(t) >= 5 and t not in GENERIC_TOKENS:
                    tok.setdefault(t, set()).add(k)
        self.tok = {t: next(iter(v)) for t, v in tok.items() if len(v) == 1}

    def _area(self, t):
        for k in sorted(self.s.area_names, key=len, reverse=True):
            if re.search(rf"\b{re.escape(k)}\b", t):
                return k
        for a, k in AREA_ALIASES.items():
            if re.search(rf"\b{re.escape(a)}\b", t):
                return k
        for w in t.split():
            if w in self.tok:
                return self.tok[w]

    def _type(self, t):
        for w in t.split():
            k = self.s.resolve_type(w) if len(w) > 2 else None
            if k:
                return k

    @staticmethod
    def _money(t, words):
        m = re.search(rf"(?:{words})\s*(?:pkr|rs\.?)?\s*(\d+(?:\.\d+)?)\s*(crore|cr|lakh|lac|million|m)?\b", t)
        if not m:
            return 0
        return float(m.group(1)) * {"crore": 1e7, "cr": 1e7, "lakh": 1e5, "lac": 1e5, "million": 1e6, "m": 1e6}.get(m.group(2), 1)

    def answer(self, text):
        t = norm(text)
        s = self.s
        if re.search(r"\b(owner|owns|owned|seller|previous owner)\b", t):
            return "Sorry, I can't share owner details. I can give the property's price, location, rooms and status instead."
        pid = re.search(r"\b(demo kpt \d+)\b", t)
        if pid or re.search(r"\b(property|id)\s+(\d{3,})\b", t):
            key = pid.group(1).replace(" ", "-") if pid else re.search(r"(\d{3,})", t).group(1)
            r = s.get_property(key)
            return r["error"] if "error" in r else "\n".join(self._fmt_row(x) for x in r["matches"])
        area, ptype = self._area(t), self._type(t)
        blk = re.search(r"\bblock\s*(\d+)\b", t)
        block = int(blk.group(1)) if blk else 0
        a_txt, t_txt = (s.area_names[area] if area else ""), (s.type_names[ptype] if ptype else "")
        if re.search(r"\b(price|cost|estimate|worth|how much|value|predict|rate)\b", t) and not re.search(r"\b(average|cheapest|lowest|highest|expensive)\b", t):
            if not (area and ptype):
                return "To estimate a price I need the area and property type, e.g. *House in Clifton, block 5*."
            yrs = re.search(r"(\d+)\s*(?:years?|yrs?)", t)
            r = s.predict(a_txt, t_txt, block, forecast_years=int(yrs.group(1)) if yrs else 0)
            if "error" in r:
                return f"{r['error']} I can't estimate this area from the local property data."
            out = [f"**{r['property_type']} in {r['area']}**" + (f", block {r['block']}" if r["block"] else ""),
                   f"- Estimated price: {r['estimated_price']}", f"- Confidence: {r['confidence_level']} ({r['based_on_records']} records)"]
            if "typical_range" in r:
                out.append(f"- Typical range: {r['typical_range']}")
            if "forecast" in r:
                out.append(f"- In {r['forecast']['years']} years at {r['forecast']['assumed_annual_appreciation_pct']}%/yr (scenario): {r['forecast']['forecast_price']}")
            out += [f"- Note: {w}" for w in r["warnings"]]
            return "\n".join(out)
        if re.search(r"\b(average|avg|median|cheapest|lowest|highest|expensive|compare|statistics|stats)\b", t):
            group = "property_type" if area and not ptype else "area" if not area else ""
            r = s.stats(group, a_txt, t_txt, block)
            rows = r.get("groups_sorted_by_median_price_ascending")
            if not rows:
                o = r["overall"]
                return f"Median: {o.get('median', 'n/a')}; average: {o.get('average', 'n/a')} across {o['priced_records']} priced records."
            if re.search(r"\b(highest|expensive)\b", t):
                rows = rows[::-1]
            return "Median prices" + (f" ({', '.join(map(str, r['filters'].values()))})" if r["filters"] else "") + ":\n" + \
                "\n".join(f"- {x[group]}: {x.get('median', 'no prices listed')}" for x in rows[:8])
        if re.search(r"\b(list|show|find|search|available|under|below|above|over|between|cheap)\b", t) or area or ptype:
            hi = self._money(t, "under|below|less than|max|upto|up to")
            lo = self._money(t, "above|over|more than|min|at least")
            r = s.search(a_txt, t_txt, block, min_price=lo, max_price=hi, sort="price_desc" if re.search(r"\b(highest|expensive)\b", t) else "price_asc")
            if not r["listings"]:
                return "No matching properties found."
            return f"{r['total_matches']} matches, showing {r['showing']}:\n" + "\n".join(self._fmt_row(x) for x in r["listings"])
        o = s.overview()
        return (f"I'm in offline mode (AI service unavailable), but I can still use the data. It covers {o['total_records']} records "
                f"in {len(o['areas'])} areas. Try: *price of a house in DHA*, *cheapest area for apartments*, or *plots under 3 crore in Malir*.")

    @staticmethod
    def _fmt_row(x):
        return f"- {x['property_id']}: {x['property_type']}, {x['area']} block {x['block']}, {x['rooms']} rooms, {x['price']}"

