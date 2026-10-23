from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("real_estate")

# Saved models (backend/ml/price_model.joblib) were pickled while this file was imported as the
# top-level module `price_prediction_pipeline`, so they reference e.g.
# `price_prediction_pipeline.ModelBundle`. The app imports this file as
# `backend.ml.price_prediction_pipeline`. Register the original name as an alias of this very
# module so joblib can resolve the pickled classes in any import layout (Vercel included).
# The classes stay single-definition: the alias points at this module object, nothing is copied.
# (Skipped when run as a script: the CLI at the bottom re-imports the module by its real name
# so that newly trained models are pickled as `price_prediction_pipeline.ModelBundle`.)
if __name__ != "__main__":
    sys.modules.setdefault("price_prediction_pipeline", sys.modules[__name__])

# --------------------------------------------------------------------------- #
# Step 1 - Ingestion & preparation
# --------------------------------------------------------------------------- #

# Canonical column name -> accepted raw spellings (compared after normalisation).
COLUMN_ALIASES: dict[str, list[str]] = {
    "property_id": ["property_id", "id", "listing_id"],
    "area_name": ["area_name", "area", "locality", "neighborhood", "neighbourhood", "society"],
    "block_number": ["block_number", "block", "block_no", "sector", "phase"],
    "property_type": ["property_type", "type", "category"],
    "rooms": ["rooms", "room_count", "no_of_rooms"],
    "bedrooms": ["bedrooms", "beds", "bedroom", "bed"],
    "bathrooms": ["bathrooms", "baths", "bathroom", "bath"],
    "size_sqft": ["size_sqft", "size", "area_sqft", "sqft", "covered_area", "size_sq_ft"],
    "price": ["price", "price_pkr", "sale_price", "amount", "total_price"],
}

# Optional numeric features: used only if at least one loaded CSV provides them.
OPTIONAL_NUMERIC = ["size_sqft", "bedrooms", "bathrooms"]


def _norm_col(name: str) -> str:
    """'Price (PKR)' -> 'price_pkr'; 'Block' -> 'block'."""
    return re.sub(r"[^0-9a-z]+", "_", str(name).strip().lower()).strip("_")


def _norm_text(value: Any) -> Any:
    """Normalise category strings so 'DHA ', 'dha' and 'Dha' match."""
    if pd.isna(value):
        return np.nan
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def resolve_csv_paths(source: Union[str, os.PathLike, Iterable[Union[str, os.PathLike]]]) -> list[str]:
    """Accept a folder, a glob pattern, a single file, or a list of any of those."""
    items = [source] if isinstance(source, (str, os.PathLike)) else list(source)
    paths: list[str] = []
    for item in items:
        item = os.fspath(item)
        if os.path.isdir(item):
            paths += glob.glob(os.path.join(item, "*.csv"))
        elif any(ch in item for ch in "*?["):
            paths += glob.glob(item)
        elif os.path.isfile(item):
            paths.append(item)
        else:
            log.warning("Skipping %s (not found)", item)
    paths = sorted(set(paths))
    if not paths:
        raise FileNotFoundError("No CSV files found for the given input.")
    return paths


def _standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw columns to canonical names; keep only canonical ones."""
    normalised = {_norm_col(c): c for c in df.columns}
    rename = {}
    for canon, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                rename[normalised[alias]] = canon
                break
    out = df.rename(columns=rename)
    return out[[c for c in COLUMN_ALIASES if c in out.columns]].copy()


def load_and_consolidate(source) -> pd.DataFrame:
    """
    Load every CSV, harmonise schemas, clean and stack into one master frame.

    Handles: differing column spellings, missing optional columns (filled NaN),
    stray whitespace/case in categories, non-numeric prices, exact duplicates
    and duplicate property IDs. Rows without a price are kept in the master
    frame (flagged by NaN) but excluded from training / mean tables later.
    """
    paths = resolve_csv_paths(source)
    frames = []
    for p in paths:
        raw = pd.read_csv(p)
        std = _standardise_columns(raw)
        missing_core = {"area_name", "property_type", "price"} - set(std.columns)
        if missing_core:
            log.warning("%s lacks core columns %s - skipped", os.path.basename(p), missing_core)
            continue
        std["source_file"] = os.path.basename(p)
        log.info("Loaded %-18s rows=%5d priced=%5d", os.path.basename(p), len(std), std["price"].notna().sum())
        frames.append(std)
    if not frames:
        raise ValueError("None of the CSVs contained the required columns.")

    df = pd.concat(frames, ignore_index=True, sort=False)

    # Categories
    for col in ("area_name", "property_type"):
        df[col] = df[col].map(_norm_text)
    # Numerics (robust to '1,200' or 'PKR 5000000')
    for col in ["block_number", "rooms", "price", *OPTIONAL_NUMERIC]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")

    before = len(df)
    df = df.drop_duplicates(subset=[c for c in df.columns if c != "source_file"])
    if "property_id" in df.columns:
        df = df.drop_duplicates(subset=["property_id", "property_type"], keep="first")
    log.info("Dropped %d duplicate rows", before - len(df))

    df = df.dropna(subset=["area_name", "property_type"])
    df = df[(df["price"].isna()) | (df["price"] > 0)]

    if "size_sqft" in df.columns and df["size_sqft"].notna().any():
        df["price_per_sqft"] = df["price"] / df["size_sqft"].where(df["size_sqft"] > 0)

    n_unpriced = int(df["price"].isna().sum())
    if n_unpriced:
        by_type = df[df["price"].isna()]["property_type"].value_counts().to_dict()
        log.warning("%d rows have no price and are excluded from training/means: %s", n_unpriced, by_type)
    log.info("Master dataset: %d rows (%d priced)", len(df), df["price"].notna().sum())
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Step 2 - Model training & evaluation
# --------------------------------------------------------------------------- #

CATEGORICAL = ["area_name", "property_type"]


def _make_regressor():
    """Best available gradient-boosting regressor (LightGBM > XGBoost > sklearn)."""
    try:
        from lightgbm import LGBMRegressor
        return "lightgbm", LGBMRegressor(n_estimators=600, learning_rate=0.05, num_leaves=31, verbose=-1, random_state=42)
    except ImportError:
        pass
    try:
        from xgboost import XGBRegressor
        return "xgboost", XGBRegressor(n_estimators=600, learning_rate=0.05, max_depth=6,
                                       enable_categorical=True, tree_method="hist", random_state=42)
    except ImportError:
        pass
    from sklearn.ensemble import HistGradientBoostingRegressor
    return "sklearn_hist_gbm", HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.06, categorical_features="from_dtype", random_state=42)


@dataclass
class ModelBundle:
    """Everything needed at inference time; saved/loaded as one joblib file."""
    model: Any
    model_name: str
    feature_cols: list[str]
    categories: dict[str, list[str]]        # known levels for each categorical feature
    known_blocks: set                        # blocks seen in training
    metrics: dict[str, float]
    fallback: "HierarchicalEstimator"
    optional_features: list[str] = field(default_factory=list)

    def save(self, path: str) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path: str) -> "ModelBundle":
        return joblib.load(path)


def _build_X(df: pd.DataFrame, feature_cols: list[str], categories: dict[str, list[str]]) -> pd.DataFrame:
    X = df.reindex(columns=feature_cols).copy()
    for col, levels in categories.items():
        X[col] = pd.Categorical(X[col], categories=levels)
    return X


def train_model(df: pd.DataFrame, test_size: float = 0.2, seed: int = 42) -> ModelBundle:
    """
    Train the price model on the priced rows and evaluate on a hold-out set.

    Encoding: categorical columns use pandas 'category' dtype (native handling by
    LightGBM / XGBoost / sklearn HistGBM - no one-hot blow-up). Block is numeric
    (it is an ordinal id) and is *also* fed to the hierarchical means.
    The target is log-transformed because prices span ~1 order of magnitude
    across property types; metrics are reported back in PKR.
    """
    data = df.dropna(subset=["price"]).copy()
    optional = [c for c in OPTIONAL_NUMERIC + ["rooms"] if c in data.columns and data[c].notna().any()]
    feature_cols = CATEGORICAL + ["block_number"] + optional
    categories = {c: sorted(data[c].dropna().unique().tolist()) for c in CATEGORICAL}

    train_df, test_df = train_test_split(
        data, test_size=test_size, random_state=seed, stratify=data["property_type"])

    name, model = _make_regressor()
    model.fit(_build_X(train_df, feature_cols, categories), np.log1p(train_df["price"]))

    pred = np.expm1(model.predict(_build_X(test_df, feature_cols, categories)))
    y = test_df["price"].to_numpy()
    metrics = {
        "rmse": float(np.sqrt(mean_squared_error(y, pred))),
        "mae": float(mean_absolute_error(y, pred)),
        "r2": float(r2_score(y, pred)),
        "mape_pct": float(np.mean(np.abs(y - pred) / y) * 100),
    }

    # Reference: how good is the pure hierarchical-mean fallback on the same split?
    ref = HierarchicalEstimator().fit(train_df)
    ref_pred = np.array([
        ref.estimate(r.area_name, r.property_type, r.block_number, getattr(r, "size_sqft", None))["price"]
        for r in test_df.itertuples()])
    metrics.update({
        "fallback_rmse": float(np.sqrt(mean_squared_error(y, ref_pred))),
        "fallback_mae": float(mean_absolute_error(y, ref_pred)),
        "fallback_r2": float(r2_score(y, ref_pred)),
    })
    log.info("Model=%s | RMSE=%.0f MAE=%.0f R2=%.4f | fallback-only R2=%.4f",
             name, metrics["rmse"], metrics["mae"], metrics["r2"], metrics["fallback_r2"])

    # Refit on ALL priced rows for deployment (metrics above stay the honest hold-out numbers).
    _, final_model = _make_regressor()
    final_model.fit(_build_X(data, feature_cols, categories), np.log1p(data["price"]))

    return ModelBundle(
        model=final_model, model_name=name, feature_cols=feature_cols, categories=categories,
        known_blocks=set(data["block_number"].dropna().astype(int)), metrics=metrics,
        fallback=HierarchicalEstimator().fit(data), optional_features=optional)


# --------------------------------------------------------------------------- #
# Step 3 - Hierarchical fallback + inference API
# --------------------------------------------------------------------------- #

class HierarchicalEstimator:
    """
    Mean-based price lookup with four levels, built from the combined dataset.

    The metric is price/sqft when the data has a size column, otherwise plain
    price (the sample CSVs contain no size column, so plain price is used and
    `size_sqft` is ignored). Levels:

      L1  (area, block, type)   needs >= `min_support` rows
      L2  (area, type)          used if block missing / unseen / thin
      L3  area-level            used if the type is not present in that area:
                                area factor (mix-neutral) x global type mean;
                                if the type is unknown everywhere, the plain
                                area mean (x size when price/sqft is available)
      L4  global baseline       area unknown: global type mean, else global mean
    """

    def __init__(self, min_support: int = 3):
        self.min_support = min_support
        self.per_sqft = False

    def fit(self, df: pd.DataFrame) -> "HierarchicalEstimator":
        d = df.dropna(subset=["price"]).copy()
        self.per_sqft = "price_per_sqft" in d.columns and d["price_per_sqft"].notna().any()
        self.metric = "price_per_sqft" if self.per_sqft else "price"
        if self.per_sqft:
            d = d.dropna(subset=["price_per_sqft"])
        m = self.metric

        def agg(keys):
            g = d.groupby(keys)[m].agg(["mean", "std", "count"])
            return g.to_dict("index")

        self.l1 = agg(["area_name", "block_number", "property_type"])
        self.l2 = agg(["area_name", "property_type"])
        self.area_mean = d.groupby("area_name")[m].mean().to_dict()
        self.type_mean = d.groupby("property_type")[m].mean().to_dict()
        self.type_std = d.groupby("property_type")[m].std().to_dict()
        self.global_mean = float(d[m].mean())
        self.global_std = float(d[m].std())
        self.n_rows = len(d)

        # Mix-neutral area factor: average of (area-type mean / global type mean).
        ratios = {}
        for (area, ptype), s in self.l2.items():
            ratios.setdefault(area, []).append(s["mean"] / self.type_mean[ptype])
        self.area_factor = {a: float(np.mean(r)) for a, r in ratios.items()}
        return self

    def _scale(self, value: float, size_sqft: Optional[float]) -> float:
        if self.per_sqft and size_sqft:
            return value * size_sqft
        return value

    def estimate(self, area: Optional[str], ptype: Optional[str],
                 block: Optional[float] = None, size_sqft: Optional[float] = None) -> dict:
        """Return {'price', 'level', 'label', 'n', 'std'} for the deepest usable level."""
        area = _norm_text(area) if area else None
        ptype = _norm_text(ptype) if ptype else None
        blk = int(block) if block is not None and not pd.isna(block) else None

        if area and ptype and blk is not None:
            s = self.l1.get((area, blk, ptype))
            if s and s["count"] >= self.min_support:
                return dict(price=self._scale(s["mean"], size_sqft), level=1,
                            label="area+block+type mean", n=int(s["count"]),
                            std=self._scale(s["std"], size_sqft) if s["count"] > 1 else None)
        if area and ptype:
            s = self.l2.get((area, ptype))
            if s:
                return dict(price=self._scale(s["mean"], size_sqft), level=2,
                            label="area+type mean", n=int(s["count"]),
                            std=self._scale(s["std"], size_sqft) if s["count"] > 1 else None)
        if area in self.area_factor:
            if ptype in self.type_mean:
                v = self.area_factor[area] * self.type_mean[ptype]
                label = "area factor x global type mean"
            else:
                v, label = self.area_mean[area], "area mean (type unknown)"
            return dict(price=self._scale(v, size_sqft), level=3, label=label,
                        n=int(sum(s["count"] for (a, _), s in self.l2.items() if a == area)), std=None)
        v = self.type_mean.get(ptype, self.global_mean)
        return dict(price=self._scale(v, size_sqft), level=4,
                    label="global type mean" if ptype in self.type_mean else "global mean",
                    n=self.n_rows, std=self._scale(self.type_std.get(ptype, self.global_std), size_sqft))


_CONFIDENCE_BY_LEVEL = {1: "high", 2: "medium", 3: "low", 4: "very_low"}


def predict_property_price(
    bundle: ModelBundle,
    area_name: Optional[str],
    property_type: Optional[str],
    block_number: Optional[int] = None,
    size_sqft: Optional[float] = None,
    rooms: Optional[int] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    forecast_years: Optional[int] = None,
    annual_appreciation_rate: float = 0.05,
) -> dict:
    """Predict a current price and, optionally, an assumption-based future price.

    Path selection
    --------------
    * ML model: area, property type AND block were all seen in training.
    * Otherwise the hierarchical estimator picks the deepest level with data
      (L1 -> L2 -> L3 -> L4, see `HierarchicalEstimator`).

    Returns a JSON-serialisable dict:
        predicted_price   float, PKR (rounded)
        currency          "PKR"
        prediction_source "ml_model" | "fallback_level_1..4"
        confidence_level  "high" | "medium" | "low" | "very_low"
        price_range       {"low", "high"} rough +/-1 std band (or None)
        support_count     number of historical rows behind the estimate
        method_detail     human-readable explanation
        warnings          list of caveats (ignored inputs, unseen values ...)

    When forecast_years is provided, also returns forecast_price,
    forecast_years, annual_appreciation_rate and forecast_price_range. The
    forecast compounds the current estimate at the supplied annual rate; it is
    a scenario assumption, not a time-series model prediction.
    """
    if forecast_years is not None:
        if isinstance(forecast_years, bool) or not isinstance(forecast_years, int) or forecast_years < 0:
            raise ValueError("forecast_years must be a non-negative integer.")
        if not np.isfinite(annual_appreciation_rate) or annual_appreciation_rate <= -1:
            raise ValueError("annual_appreciation_rate must be finite and greater than -1.")

    def add_forecast(result: dict) -> dict:
        if forecast_years is None:
            return result
        growth_factor = (1 + annual_appreciation_rate) ** forecast_years
        result["forecast_years"] = forecast_years
        result["annual_appreciation_rate"] = annual_appreciation_rate
        result["forecast_price"] = round(result["predicted_price"] * growth_factor, -3)
        price_range = result["price_range"]
        result["forecast_price_range"] = (
            {
                "low": round(price_range["low"] * growth_factor, -3),
                "high": round(price_range["high"] * growth_factor, -3),
            }
            if price_range
            else None
        )
        result["warnings"].append(
            "Future price is a scenario based on the assumed annual appreciation rate; "
            "the model is not trained on time-series price changes."
        )
        return result

    area = _norm_text(area_name) if area_name else None
    ptype = _norm_text(property_type) if property_type else None
    blk = None if block_number is None or pd.isna(block_number) else int(block_number)
    warnings: list[str] = []

    for name, val in (("size_sqft", size_sqft), ("bedrooms", bedrooms), ("bathrooms", bathrooms)):
        if val is not None and name not in bundle.optional_features:
            warnings.append(f"'{name}' ignored: not present in the training data.")

    area_known = area in bundle.categories["area_name"]
    type_known = ptype in bundle.categories["property_type"]
    block_known = blk in bundle.known_blocks
    if area and not area_known:
        warnings.append(f"Area '{area_name}' not in training data.")
    if ptype and not type_known:
        warnings.append(f"Property type '{property_type}' has no priced records.")
    if blk is not None and not block_known:
        warnings.append(f"Block {blk} not in training data.")

    combo_seen = (area, blk, ptype) in bundle.fallback.l1

    if area_known and type_known and block_known and combo_seen:
        row = pd.DataFrame([{
            "area_name": area, "property_type": ptype, "block_number": blk,
            "size_sqft": size_sqft, "rooms": rooms, "bedrooms": bedrooms, "bathrooms": bathrooms}])
        price = float(np.expm1(bundle.model.predict(_build_X(row, bundle.feature_cols, bundle.categories))[0]))
        ref = bundle.fallback.estimate(area, ptype, blk, size_sqft)
        std = ref["std"]
        return add_forecast({
            "predicted_price": round(price, -3), "currency": "PKR",
            "prediction_source": "ml_model", "confidence_level": "high" if ref["n"] >= 5 else "medium",
            "price_range": {"low": round(max(price - std, 0), -3), "high": round(price + std, -3)} if std else None,
            "support_count": ref["n"],
            "method_detail": f"{bundle.model_name} on (area, block, type)",
            "warnings": warnings,
        })

    est = bundle.fallback.estimate(area, ptype, blk, size_sqft)
    std = est["std"]
    if est["level"] == 3 and "type unknown" in est["label"]:
        warnings.append("Estimate is an all-types area average, not specific to this property type.")
    return add_forecast({
        "predicted_price": round(est["price"], -3), "currency": "PKR",
        "prediction_source": f"fallback_level_{est['level']}",
        "confidence_level": _CONFIDENCE_BY_LEVEL[est["level"]],
        "price_range": {"low": round(max(est["price"] - std, 0), -3), "high": round(est["price"] + std, -3)} if std else None,
        "support_count": est["n"],
        "method_detail": f"hierarchical mean: {est['label']}",
        "warnings": warnings,
    })


# --------------------------------------------------------------------------- #
# Step 4 - Demonstration
# --------------------------------------------------------------------------- #

def main(argv: Optional[Sequence[str]] = None) -> ModelBundle:
    parser = argparse.ArgumentParser(description="Train the real-estate price model from one or more CSVs.")
    parser.add_argument("sources", nargs="+", help="Folder(s), glob pattern(s) or CSV file path(s)")
    parser.add_argument("--save", default="price_model.joblib", help="Where to store the trained bundle")
    args = parser.parse_args(argv)

    df = load_and_consolidate(args.sources)
    bundle = train_model(df)
    bundle.save(args.save)
    log.info("Saved model bundle to %s", args.save)

    import json
    demo_queries = [
        ("1. Known combo -> 5-year scenario at 5%/year", dict(
            area_name="Clifton", property_type="House", block_number=5,
            forecast_years=5, annual_appreciation_rate=0.05)),
        ("2. Unseen block -> L2 (area+type)",       dict(area_name="Clifton", property_type="House", block_number=45)),
        ("3. Block omitted -> L2 (area+type)",      dict(area_name="Malir", property_type="Plot")),
        ("4. Type not sold in area -> L3",          dict(area_name="Bahria Town", property_type="Penthouse", block_number=2)),
        ("5. Unseen area -> L4 (global baseline)",  dict(area_name="Gadap Town", property_type="Apartment", block_number=3)),
        ("6. Unpriced type (Commercial) -> L3",     dict(area_name="DHA", property_type="Commercial", block_number=4)),
    ]
    for title, q in demo_queries:
        print(f"\n### {title}\nquery: {q}")
        print(json.dumps(predict_property_price(bundle, **q), indent=2))
    return bundle


if __name__ == "__main__":
    # Run through the *imported* module rather than as `__main__`. Otherwise joblib
    # pickles the classes as `__main__.ModelBundle`, and the saved model then fails
    # to load from any other script. Deriving the module name from __file__ keeps
    # this working even if the file is renamed again.
    import importlib
    import sys

    _module_name = os.path.splitext(os.path.basename(__file__))[0]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    importlib.import_module(_module_name).main()
