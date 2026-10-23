"""Pure text/number helpers and lookup tables shared by the data layer and the chat engines."""
import re

import numpy as np
import pandas as pd

COLS = {"property_id": "property_id", "house_number": "house_number", "street_number": "street",
        "area": "area", "block": "block", "rooms": "rooms", "property_type": "type",
        "ownership_status": "ownership", "taxes_status": "taxes", "legal_check": "legal",
        "utilities_bill": "utilities", "price_pkr": "price"}
AREA_ALIASES = {"defence": "dha", "defense": "dha", "d h a": "dha", "bahria": "bahria town",
                "fb": "fb area", "federal b area": "fb area", "p e c h s": "pechs"}
TYPE_SYN = {"flat": "apartment", "apt": "apartment", "home": "house", "bungalow": "house",
            "villa": "house", "shop": "commercial", "office": "commercial", "land": "plot",
            "floor": "portion", "upper portion": "portion", "lower portion": "portion"}
GENERIC_TOKENS = {"area", "town", "north"}


def norm(s):
    """Lower-case, strip punctuation, collapse whitespace (used for fuzzy matching)."""
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def fmt(x):
    """PKR with lakh/crore shorthand, e.g. 'PKR 10,000,000 (1.00 crore)'."""
    if x is None or pd.isna(x):
        return "not listed"
    x = float(x)
    short = f"{x / 1e7:.2f} crore" if x >= 1e7 else f"{x / 1e5:.2f} lakh" if x >= 1e5 else f"{x:,.0f}"
    return f"PKR {x:,.0f} ({short})"



def clean(v):
    """Convert NaN/numpy scalars into JSON-safe Python values."""
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else (int(v) if isinstance(v, (np.integer,)) else v)
