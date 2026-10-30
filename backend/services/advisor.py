"""Data-driven answers that make the bot more than a lookup: ranges with context, listing
suggestions, comparisons, hand-offs. Everything is read-only and built from the record store.

Cards are built here from dataset rows, never from model output, so a model cannot invent a
listing or a link. No owner field exists in the store, so none can leak into a card.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from backend.records.store import Store
from backend.records.text import clean, fmt

TYPE_SLUG = {"Plot": "plot", "House": "house", "Apartment": "apartment", "Portion": "portion", "Commercial": "commercial"}
_ID = re.compile(r"\bdemo[\s-]*kpt[\s-]*(\d+)\b", re.I)


def short_money(x: float) -> str:
    return f"{x / 1e7:.2f} crore" if x >= 1e7 else f"{x / 1e5:.0f} lakh"


def listing_url(row) -> str:
    return f"/#/{TYPE_SLUG.get(row.type, 'property')}/{row.property_id}"


def _why(store: Store, row, median: float | None) -> list[str]:
    why = []
    if median and row.price and row.price < median:
        why.append(f"{(1 - row.price / median) * 100:.0f}% below the {row.area} {row.type.lower()} median ({short_money(median)})")
    if row.legal == "Clear": why.append("Legal check: clear")
    if row.ownership == "Verified": why.append("Ownership status: verified")
    if row.taxes == "Paid": why.append("Taxes paid")
    if clean(row.block): why.append(f"Block {int(row.block)}")
    return why[:4]


def card(store: Store, row, median: float | None = None) -> dict:
    return {"id": row.property_id, "title": f"{row.type} in {row.area}" + (f", Block {int(row.block)}" if clean(row.block) else ""),
            "area": row.area, "block": clean(row.block), "type": row.type, "rooms": clean(row.rooms),
            "price": fmt(row.price), "why": _why(store, row, median), "url": listing_url(row),
            "badges": [f"Legal: {row.legal}", f"Taxes: {row.taxes}"]}


def suggest(store: Store, area: str = "", ptype: str = "", budget_max: float = 0, n: int = 3) -> tuple[list[dict], dict]:
    """Pick ``n`` good-value, clean-status listings. Returns (cards, info) with info['relaxed'] if the budget was stretched."""
    d, filt, err = store._filter(area, ptype)
    if err:
        return [], {"error": err}
    d = d.dropna(subset=["price"])
    info: dict = {"filters": filt, "relaxed": False}
    pool = d[d.price <= budget_max] if budget_max else d
    if pool.empty and budget_max:
        pool, info["relaxed"] = d[d.price <= budget_max * 1.3], True
    if pool.empty:
        return [], info
    med = {(a, t): v for (a, t), v in d.groupby(["area_key", "type_key"]).price.median().items()}
    scored = []
    for r in pool.itertuples():
        m = med.get((r.area_key, r.type_key))
        score = (2 if r.legal == "Clear" else 0) + (1 if r.ownership == "Verified" else 0) + (1 if r.taxes == "Paid" else 0) \
            + (1.5 * max(0.0, 1 - r.price / m) if m else 0)
        scored.append((score, -r.price, r, m))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    picked, seen_blocks = [], set()
    for _, _, r, m in scored:
        key = (r.area_key, clean(r.block))
        if key in seen_blocks and len(scored) > n * 4:
            continue
        seen_blocks.add(key); picked.append(card(store, r, m))
        if len(picked) == n: break
    return picked, info


def area_overview(store: Store, area: str) -> dict | None:
    """Min/median/max per type for one area plus how it ranks against the other areas."""
    k, _ = store.resolve_area(area)
    if not k: return None
    d = store.df.dropna(subset=["price"])
    a = d[d.area_key == k]
    if a.empty: return None
    city_med = d.price.median()
    ranks = d.groupby("area_key").price.median().sort_values()
    pos = list(ranks.index).index(k) + 1 if k in ranks.index else None
    per_type = [{"type": store.type_names[t], "count": int(len(g)), "min": g.price.min(), "median": g.price.median(), "max": g.price.max()}
                for t, g in a.groupby("type_key")]
    spread = None
    if len(per_type) > 1:
        lo, hi = min(per_type, key=lambda x: x["median"]), max(per_type, key=lambda x: x["median"])
        spread = (lo["type"], lo["median"], hi["type"], hi["median"])
    return {"area": store.area_names[k], "count": int(len(a)), "median": a.price.median(), "city_median": city_med,
            "rank": pos, "areas": int(len(ranks)), "per_type": per_type, "spread": spread}


def price_overview_text(o: dict) -> str:
    lines = [f"**{o['area']} at a glance.** *From the dataset:* {o['count']:,} priced listings"]
    for t in o["per_type"]:
        small = " (small sample)" if t["count"] < 10 else ""
        lines.append(f"- {t['type']}: {short_money(t['min'])} to {short_money(t['max'])}, median {short_money(t['median'])}, {t['count']} listings{small}")
    rel = "above" if o["median"] > o["city_median"] else "below"
    lines.append(f"- City context: its overall median ({short_money(o['median'])}) is {rel} the Karachi median ({short_money(o['city_median'])}); "
                 f"cheapest-to-priciest rank {o['rank']} of {o['areas']} areas.")
    if o["spread"]:
        lo_t, lo_m, hi_t, hi_m = o["spread"]
        lines.append(f"- What moves price here: property type (a typical {lo_t.lower()} is {short_money(lo_m)}, a typical {hi_t.lower()} {short_money(hi_m)}); size and block matter too.")
    return "\n".join(lines)


def compare_ids(store: Store, text: str) -> tuple[str, list[dict]]:
    ids = list(dict.fromkeys(f"DEMO-KPT-{m}" for m in _ID.findall(text)))[:4]
    rows = [store.df[store.df.property_id.str.upper() == i] for i in ids]
    found = [r.iloc[0] for r in rows if not r.empty]
    if len(found) < 2:
        return "I need at least two valid property IDs to compare, for example *Compare DEMO-KPT-1648 and DEMO-KPT-1517*.", []
    cards, lines = [], ["**Side by side** (from the property records)"]
    for r in found:
        tup = type("R", (), r.to_dict())()
        lines.append(f"- {tup.property_id}: {tup.type} in {tup.area}, block {clean(tup.block)}, {fmt(tup.price)}, legal check {tup.legal}, taxes {tup.taxes}")
        cards.append(card(store, tup))
    priced = [c for c in found if c["price"] == c["price"]]
    if len(priced) >= 2:
        cheap = min(priced, key=lambda c: c["price"])
        lines.append(f"- Lowest price: {cheap['property_id']} ({fmt(cheap['price'])}).")
    return "\n".join(lines), cards


def handoff_actions(settings, summary: str) -> list[dict]:
    """Contact links prefilled with a chat summary. Only built for channels the owner configured."""
    text = quote(f"Hello, I was chatting with the Property Assistant. {summary}".strip())
    out = []
    if settings.contact_whatsapp:
        out.append({"type": "link", "label": "Message us on WhatsApp", "url": f"https://wa.me/{re.sub(r'[^0-9]', '', settings.contact_whatsapp)}?text={text}"})
    if settings.contact_email:
        out.append({"type": "link", "label": "Email an agent", "url": f"mailto:{settings.contact_email}?subject={quote('Property enquiry')}&body={text}"})
    return out
