"""Read-only property record store + the pre-trained price model (never retrains at runtime).

Owner names / previous owners / owner IDs are deliberately never loaded, so nothing
downstream (Gemini tools, offline engine, API) can disclose them.
"""
import difflib
import logging
from pathlib import Path

import pandas as pd

from backend.ml import price_prediction_pipeline as ppp
from backend.records.text import AREA_ALIASES, COLS, TYPE_SYN, clean, fmt, norm

log = logging.getLogger("chatbot")


class Store:
    def __init__(self, data_dir: Path, model_path: Path):
        self.data_dir = Path(data_dir)
        self.model_path = Path(model_path)
        frames = []
        for p in sorted(self.data_dir.glob("*.csv")):
            raw = pd.read_csv(p, encoding="utf-8-sig")
            raw.columns = [ppp._norm_col(c) for c in raw.columns]
            f = raw[[c for c in COLS if c in raw.columns]].rename(columns=COLS)
            f["source_file"] = p.name
            frames.append(f)
        if not frames:
            raise FileNotFoundError(f"No CSV files found in {self.data_dir}")
        df = pd.concat(frames, ignore_index=True)
        for c in ("price", "block", "rooms"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["area_key"], df["type_key"] = df["area"].map(norm), df["type"].map(norm)
        df = df.drop_duplicates(subset=["property_id", "type_key"]).dropna(subset=["area", "type"])
        self.df = df.reset_index(drop=True)
        self.area_names = df.groupby("area_key")["area"].agg(lambda s: s.mode().iat[0]).to_dict()
        self.type_names = df.groupby("type_key")["type"].agg(lambda s: s.mode().iat[0].title()).to_dict()
        self.files = df["source_file"].value_counts().to_dict()
        self.bundle = self._load_model()

    def _load_model(self):
        """Load the pre-trained model bundle. Never retrains and never writes to disk.

        Retraining is an explicit development step (python backend/ml/price_prediction_pipeline.py
        backend/datasets --save backend/ml/price_model.joblib). If loading fails, the real error is raised so it
        shows up in the deployment logs / the /api/health response instead of being masked.
        """
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Price model not found at {self.model_path}")
        try:
            bundle = ppp.ModelBundle.load(str(self.model_path))
        except Exception as e:
            raise RuntimeError(f"Could not load price model {self.model_path.name}: {type(e).__name__}: {e}") from e
        log.info("Loaded price model %s (%s)", self.model_path.name, getattr(bundle, "model_name", "?"))
        return bundle

    # ---- resolvers -------------------------------------------------------
    def resolve_area(self, text):
        q = norm(text)
        q = AREA_ALIASES.get(q, q)
        keys = list(self.area_names)
        if q in keys:
            return q, []
        toks = set(q.split())
        hits = [k for k in keys if toks and toks <= set(k.split())]
        if len(hits) == 1:
            return hits[0], []
        if len(hits) > 1:
            return None, [self.area_names[k] for k in hits]
        m = difflib.get_close_matches(q, keys, n=1, cutoff=0.75)
        return (m[0], []) if m else (None, [])

    def resolve_type(self, text):
        q = norm(text)
        q = TYPE_SYN.get(q, q)
        if q not in self.type_names and q.endswith("s"):
            q = q[:-1]
        q = TYPE_SYN.get(q, q)
        if q in self.type_names:
            return q
        m = difflib.get_close_matches(q, list(self.type_names), n=1, cutoff=0.8)
        return m[0] if m else None

    def _filter(self, area="", ptype="", block=0):
        d, filt = self.df, {}
        if area:
            k, cands = self.resolve_area(area)
            if not k:
                if cands:
                    return None, None, {"error": f"'{area}' matches several areas; ask the user which one.", "candidates": cands}
                return None, None, {"error": f"Area '{area}' is not in the property data.",
                                    "known_areas": sorted(self.area_names.values())}
            d, filt["area"] = d[d.area_key == k], self.area_names[k]
        if ptype:
            t = self.resolve_type(ptype)
            if not t:
                return None, None, {"error": f"Property type '{ptype}' is not in the data.",
                                    "known_types": sorted(self.type_names.values())}
            d, filt["property_type"] = d[d.type_key == t], self.type_names[t]
        if block:
            d, filt["block"] = d[d.block == block], int(block)
        return d, filt, None

    # ---- tool implementations -------------------------------------------
    def predict(self, area, property_type, block=0, rooms=0, forecast_years=0, rate_pct=5.0):
        _, _, err = self._filter(area, property_type)
        if err:
            return err
        if not area or not property_type:
            return {"error": "Both area and property_type are required for an estimate."}
        if not -50 <= rate_pct <= 100:
            return {"error": "annual_appreciation_pct must be between -50 and 100."}
        fy = int(forecast_years) if forecast_years and forecast_years > 0 else None
        if fy and fy > 50:
            return {"error": "forecast_years must be 50 or less."}
        a = self.area_names[self.resolve_area(area)[0]]
        t = self.type_names[self.resolve_type(property_type)]
        r = ppp.predict_property_price(self.bundle, a, t, block_number=int(block) or None,
                                       rooms=int(rooms) or None, forecast_years=fy,
                                       annual_appreciation_rate=rate_pct / 100)
        out = {"area": a, "property_type": t, "block": int(block) or None,
               "estimated_price": fmt(r["predicted_price"]), "confidence_level": r["confidence_level"],
               "prediction_source": r["prediction_source"], "based_on_records": r["support_count"],
               "method": r["method_detail"], "warnings": r["warnings"]}
        if r["price_range"]:
            out["typical_range"] = f"{fmt(r['price_range']['low'])} to {fmt(r['price_range']['high'])}"
        if fy:
            out["forecast"] = {"years": fy, "assumed_annual_appreciation_pct": rate_pct,
                               "forecast_price": fmt(r["forecast_price"]),
                               "note": "Scenario using the assumed rate, not a trained forecast."}
        return out

    def _summ(self, g, total):
        p = g["price"].dropna()
        if p.empty:
            return {"records": int(total), "priced_records": 0}
        return {"records": int(total), "priced_records": int(len(p)), "min": fmt(p.min()),
                "median": fmt(p.median()), "average": fmt(p.mean()), "max": fmt(p.max()),
                "median_value": float(p.median())}

    def stats(self, group_by="", area="", property_type="", block=0):
        d, filt, err = self._filter(area, property_type, block)
        if err:
            return err
        out = {"filters": filt, "overall": self._summ(d, len(d))}
        out["overall"].pop("median_value", None)
        col = {"area": "area_key", "property_type": "type_key", "block": "block"}.get(group_by)
        if col:
            rows = []
            for key, g in d.groupby(col):
                s = self._summ(g, len(g))
                label = self.area_names.get(key) if group_by == "area" else \
                    self.type_names.get(key) if group_by == "property_type" else int(key)
                rows.append({group_by: label, **s})
            rows.sort(key=lambda r: r.get("median_value", float("inf")))
            for r in rows:
                r.pop("median_value", None)
            out["groups_sorted_by_median_price_ascending"] = rows[:25]
        return out

    def _row(self, r):
        return {"property_id": r.property_id, "address": f"{r.house_number}, {r.street}",
                "area": r.area, "block": clean(r.block), "property_type": r.type,
                "rooms": clean(r.rooms), "price": fmt(r.price), "ownership_status": r.ownership,
                "taxes_status": r.taxes, "legal_check": r.legal, "utilities_bill": r.utilities}

    def search(self, area="", property_type="", block=0, min_price=0, max_price=0,
               min_rooms=0, max_rooms=0, sort="price_asc", limit=5):
        d, filt, err = self._filter(area, property_type, block)
        if err:
            return err
        if min_price > 0:
            d = d[d.price >= min_price]
        if max_price > 0:
            d = d[d.price <= max_price]
        if min_rooms > 0:
            d = d[d.rooms >= min_rooms]
        if max_rooms > 0:
            d = d[d.rooms <= max_rooms]
        top = d.sort_values("price", ascending=sort != "price_desc", na_position="last").head(min(max(int(limit), 1), 10))
        return {"filters": filt, "total_matches": len(d), "showing": len(top),
                "listings": [self._row(r) for r in top.itertuples()]}

    def get_property(self, property_id):
        q = str(property_id).strip().upper()
        ids = self.df.property_id.str.upper()
        d = self.df[(ids == q) | ids.str.endswith("-" + q)] if q.isdigit() else self.df[ids == q]
        if d.empty:
            return {"error": f"No property found with ID '{property_id}'."}
        return {"matches": [self._row(r) for r in d.head(5).itertuples()]}

    def overview(self):
        priced = self.df.dropna(subset=["price"])
        m = self.bundle.metrics
        return {"total_records": len(self.df), "priced_records": len(priced),
                "records_by_type": {self.type_names[k]: int(v) for k, v in self.df.type_key.value_counts().items()},
                "types_without_prices": [self.type_names[k] for k in self.type_names
                                         if priced[priced.type_key == k].empty],
                "areas": sorted(self.area_names.values()),
                "blocks": f"{int(self.df.block.min())} to {int(self.df.block.max())}",
                "price_model": {"name": self.bundle.model_name, "holdout_r2": round(m["r2"], 3),
                                "holdout_mape_pct": round(m["mape_pct"], 1)}}

