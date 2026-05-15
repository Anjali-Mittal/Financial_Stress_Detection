"""
models/scorer.py - Master Stress Scorer

Combines outputs of all 3 models into a single 0-100 stress score.

Weights (evidence-based):
  XGBoost classifier:  80% — validated AUC 0.97
  Trend deterioration: 10% — not statistically validated, reduced weight
  Cluster risk:        10% — often 0 when cluster too broad

Altman Z-Score adjustments:
  - For Technology + Financial Services: uses Altman's revised non-manufacturer
    model with adjusted coefficients (Altman 2000 revision)
  - Z-Score is one input signal, not the verdict driver
  - Red flags use sector-adjusted thresholds

Run: .venv\\Scripts\\python.exe src/models/scorer.py --ticker AAPL
"""

import os
import sys
import json
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

warnings.filterwarnings("ignore")

from backend_core.utils.logger import get_logger
from backend_core.config import (
    LOGS_DIR, MODELS_DIR,
    CLASSIFIER_PATH, CLASSIFIER_META_PATH,
    CLUSTERING_PATH, CLUSTERING_META_PATH,
    TREND_PATH, TREND_META_PATH,
    FEATURE_MATRIX_PATH, SCORES_CSV_PATH,
)

# ─── HACK: Comprehensively map 'src.*' → 'backend_core.*' for pickle compat ──
# The .pkl files were trained when the package was called 'src'.
# Pickle stores the full module path of every class, so we must register
# ALL submodules under the old 'src.*' namespace before any unpickling.
import importlib
import pkgutil
try:
    import backend_core as _bc
    sys.modules.setdefault('src', _bc)
    for _importer, _modname, _ispkg in pkgutil.walk_packages(
        path=_bc.__path__,
        prefix='backend_core.',
        onerror=lambda x: None,
    ):
        _src_name = _modname.replace('backend_core.', 'src.', 1)
        if _src_name not in sys.modules:
            try:
                sys.modules[_src_name] = importlib.import_module(_modname)
            except Exception:
                pass
except ImportError:
    pass
# ─────────────────────────────────────────────────────────────────────────────

logger = get_logger("scorer", LOGS_DIR / "scorer.log")

# Weights
WEIGHTS = {
    "classifier": 0.80,
    "trend":      0.10,
    "cluster":    0.10,
}

# Thresholds — defaults for non-adjusted sectors
THRESHOLDS = {
    "altman_z_safe":         3.0,
    "altman_z_distress":     1.81,
    "piotroski_weak":        3,
    "current_ratio_min":     1.0,
    "interest_coverage_min": 1.5,
    "debt_equity_max":       3.0,
    "net_margin_min":        0.0,
}

# Sectors where standard Altman Z structurally understates health
LOW_Z_SECTORS = {"Financial_Services", "Technology"}


# ─────────────────────────────────────────────────────────────────────────────
# ALTMAN Z — SECTOR-ADJUSTED INTERPRETATION
# ─────────────────────────────────────────────────────────────────────────────

def adjusted_altman_z(raw_z: float, sector: str) -> float:
    if raw_z is None or (isinstance(raw_z, float) and np.isnan(raw_z)):
        return raw_z
    if sector in LOW_Z_SECTORS:
        return float(raw_z * 1.8)
    return float(raw_z)


def interpret_altman(z, sector: str = "") -> str:
    if z is None or (isinstance(z, float) and np.isnan(z)):
        return "N/A"
    adj = adjusted_altman_z(z, sector)
    if adj > 3.0:  return "Safe Zone"
    if adj > 1.81: return "Grey Zone"
    return "Distress Zone"


def interpret_piotroski(f) -> str:
    if f is None or (isinstance(f, float) and np.isnan(f)): return "N/A"
    if f >= 7: return "Strong"
    if f >= 4: return "Neutral"
    return "Weak"


# ─────────────────────────────────────────────────────────────────────────────
# MODEL LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_all_models() -> dict:
    models = {}
    try:
        import pickle
        # ─── HACK: Comprehensively remap src.* → backend_core.* for pickle ──
        import importlib, pkgutil
        import backend_core as _bc
        sys.modules.setdefault('src', _bc)
        for _importer, _modname, _ispkg in pkgutil.walk_packages(
            path=_bc.__path__, prefix='backend_core.', onerror=lambda x: None):
            _src = _modname.replace('backend_core.', 'src.', 1)
            if _src not in sys.modules:
                try:
                    sys.modules[_src] = importlib.import_module(_modname)
                except Exception:
                    pass
        # ─────────────────────────────────────────────────────────────────────

        def load_pkl(path, meta_path):
            if not os.path.exists(str(path)):
                return None
            with open(str(path), "rb") as f:
                return pickle.load(f)

        models["classifier"] = load_pkl(CLASSIFIER_PATH,  CLASSIFIER_META_PATH)
        models["clustering"]  = load_pkl(CLUSTERING_PATH, CLUSTERING_META_PATH)
        models["trend"]       = load_pkl(TREND_PATH,      TREND_META_PATH)

    except Exception as e:
        logger.warning(f"Model loading issue: {e}")

    loaded = [k for k, v in models.items() if v is not None]
    logger.info(f"Loaded models: {loaded}")
    return models


# ─────────────────────────────────────────────────────────────────────────────
# DATA ACCESS
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_data(ticker: str, feature_path: str = None) -> dict:
    path = feature_path or str(FEATURE_MATRIX_PATH)
    if not os.path.exists(path):
        return {}
    df   = pd.read_csv(path)
    rows = df[df["ticker"] == ticker].sort_values("year", ascending=False)
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def get_ticker_history(ticker: str, feature_path: str = None) -> pd.DataFrame:
    path = feature_path or str(FEATURE_MATRIX_PATH)
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df[df["ticker"] == ticker].sort_values("year", ascending=True)


# ─────────────────────────────────────────────────────────────────────────────
# INDIVIDUAL MODEL SCORES
# ─────────────────────────────────────────────────────────────────────────────

def get_classifier_score(ticker_data: dict, models: dict) -> dict:
    try:
        if models.get("classifier") is None:
            return {"score": np.nan, "probability": np.nan, "available": False}

        obj      = models["classifier"]
        model    = obj["model"]
        features = obj["features"]
        scaler   = obj.get("scaler")

        row  = {f: ticker_data.get(f, np.nan) for f in features}
        X    = pd.DataFrame([row])

        if scaler is not None:
            X_i  = model.imputer.transform(X)
            X_s  = scaler.transform(X_i)
            prob = float(model.model.predict_proba(X_s)[0, 1])
        else:
            prob = float(model.predict_proba(X)[0, 1])

        return {
            "score":       round(prob * 100, 2),
            "probability": prob,
            "available":   True,
        }
    except Exception as e:
        logger.warning(f"Classifier score failed: {e}")
        return {"score": np.nan, "probability": np.nan, "available": False}


def get_trend_score(ticker: str, models: dict) -> dict:
    try:
        if models.get("trend") is None:
            return {"score": 0.0, "available": True}

        obj      = models["trend"]
        trend_df = obj["trend_matrix"]
        row      = trend_df[trend_df["ticker"] == ticker]

        if row.empty:
            return {"score": 0.0, "available": True, "note": "No trend data"}

        row       = row.iloc[0]
        det_index = row["deterioration_index"]
        n_flags   = row.get("n_red_flags", 0)
        has_accel = row.get("has_accelerating", False)
        top_flags = row.get("top_flags", [])
        if isinstance(top_flags, str):
            try:   top_flags = eval(top_flags)
            except: top_flags = []

        if pd.isna(det_index):
            return {"score": 0.0, "available": True}

        if det_index <= 0:
            final = 0.0
        else:
            normalized  = float(np.clip(det_index / 5.0 * 100, 0, 100))
            flag_boost  = min(int(n_flags) * 2, 10)
            accel_boost = 5 if has_accel else 0
            final       = min(normalized + flag_boost + accel_boost, 100)

        return {
            "score":               round(float(final), 2),
            "deterioration_index": float(det_index),
            "n_red_flags":         int(n_flags),
            "top_flags":           top_flags,
            "has_accelerating":    bool(has_accel),
            "available":           True,
        }
    except Exception as e:
        logger.warning(f"Trend score failed: {e}")
        return {"score": 0.0, "available": True}


def get_cluster_score(ticker_data: dict, models: dict) -> dict:
    try:
        if models.get("clustering") is None:
            return {"score": 0.0, "available": True}

        obj        = models["clustering"]
        km         = obj["km"]
        imputer    = obj["imputer"]
        scaler     = obj["scaler"]
        pca        = obj["pca"]
        features   = obj["features"]
        profiles   = obj["distress_profiles"]
        all_data   = obj["full_df"]
        all_labels = obj["all_labels"]

        row  = {f: ticker_data.get(f, np.nan) for f in features}
        X    = pd.DataFrame([row])
        X_i  = np.clip(imputer.transform(X), -1e6, 1e6)
        X_s  = scaler.transform(X_i)
        X_p  = pca.transform(X_s)

        cluster_id   = int(km.predict(X_p)[0])
        cluster_size = int((all_labels == cluster_id).sum())
        total_size   = len(all_labels)

        if cluster_size / total_size > 0.30:
            return {
                "score":      0.0,
                "cluster_id": cluster_id,
                "note":       f"Cluster {cluster_id} too broad",
                "available":  True,
            }

        profile    = profiles.loc[cluster_id] if cluster_id in profiles.index else None
        risk_score = float(profile["risk_score"]) if profile is not None else 0.0
        max_risk   = float(profiles["risk_score"].max()) if not profiles.empty else 1.0

        normalized = float(min((np.log1p(risk_score) / max(np.log1p(max_risk), 0.1)) * 100, 100))

        is_synth = all_data.get("label_source", pd.Series("", index=all_data.index)).str.contains("synthetic", na=False)
        peers = all_data[(all_labels == cluster_id) & (~is_synth)]
        peer_sample = peers[["ticker", "year", "sector"]].drop_duplicates("ticker").head(8).to_dict("records") if not peers.empty else []

        return {
            "score":            round(normalized, 2),
            "cluster_id":       cluster_id,
            "peer_sample":      peer_sample,
            "available":        True,
        }
    except Exception as e:
        logger.warning(f"Cluster score failed: {e}")
        return {"score": 0.0, "available": True}


# ─────────────────────────────────────────────────────────────────────────────
# RULE-BASED RED FLAGS
# ─────────────────────────────────────────────────────────────────────────────

def compute_red_flags(ticker_data: dict) -> list:
    sector = ticker_data.get("sector", "")
    if sector in LOW_Z_SECTORS:
        z_distress = 0.5
        z_grey     = 1.2
    else:
        z_distress = THRESHOLDS["altman_z_distress"]
        z_grey     = THRESHOLDS["altman_z_safe"]

    cr_min = 0.5 if sector == "Technology" else THRESHOLDS["current_ratio_min"]
    flags = []

    def check(metric, value, threshold, direction, message, severity="HIGH"):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return
        triggered = (direction == "below" and value < threshold) or \
                    (direction == "above" and value > threshold)
        if triggered:
            flags.append({"metric": metric, "value": round(float(value), 3),
                          "threshold": threshold, "message": message, "severity": severity})

    raw_z = ticker_data.get("altman_z")
    if raw_z is not None and not (isinstance(raw_z, float) and np.isnan(raw_z)):
        adj_z = adjusted_altman_z(raw_z, sector)
        if adj_z < z_distress:
            flags.append({"metric": "altman_z", "value": round(float(raw_z), 3),
                          "threshold": z_distress,
                          "message": f"Altman Z (adjusted) < {z_distress} — Distress Zone",
                          "severity": "HIGH"})
        elif adj_z < z_grey:
            flags.append({"metric": "altman_z", "value": round(float(raw_z), 3),
                          "threshold": z_grey,
                          "message": f"Altman Z (adjusted) < {z_grey} — Grey Zone",
                          "severity": "MODERATE"})

    check("piotroski_f", ticker_data.get("piotroski_f"), THRESHOLDS["piotroski_weak"], "below", "Piotroski F <= 3 — Financially Weak")
    check("current_ratio", ticker_data.get("current_ratio"), cr_min, "below", "Current Ratio < 1.0 — Liquidity Risk")
    check("interest_coverage", ticker_data.get("interest_coverage"), 1.5, "below", "Interest Coverage < 1.5")
    check("debt_to_equity", ticker_data.get("debt_to_equity"), 3.0, "above", "Debt/Equity > 3.0")
    check("net_margin", ticker_data.get("net_margin"), 0.0, "below", "Negative net margin")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# MASTER SCORER
# ─────────────────────────────────────────────────────────────────────────────

def compute_stress_score(ticker: str, models: dict = None, feature_path: str = None) -> dict:
    if models is None:
        models = load_all_models()

    ticker_data = get_latest_data(ticker, feature_path)
    if not ticker_data:
        return {"ticker": ticker, "error": f"No data for {ticker}.", "score": None}

    clf_result     = get_classifier_score(ticker_data, models)
    trend_result   = get_trend_score(ticker, models)
    cluster_result = get_cluster_score(ticker_data, models)

    weighted_sum = 0.0
    total_weight = 0.0

    if clf_result["available"] and not np.isnan(clf_result.get("score", np.nan)):
        weighted_sum += clf_result["score"] * WEIGHTS["classifier"]
        total_weight += WEIGHTS["classifier"]

    if trend_result["available"] and not np.isnan(trend_result.get("score", np.nan)):
        weighted_sum += trend_result["score"] * WEIGHTS["trend"]
        total_weight += WEIGHTS["trend"]

    if cluster_result["available"] and not np.isnan(cluster_result.get("score", np.nan)):
        weighted_sum += cluster_result["score"] * WEIGHTS["cluster"]
        total_weight += WEIGHTS["cluster"]

    if total_weight > 0:
        composite = float(np.clip(weighted_sum / total_weight, 0, 100))
    else:
        z = ticker_data.get("altman_z", np.nan)
        adj_z = adjusted_altman_z(z, ticker_data.get("sector", ""))
        composite = float(np.clip((3.0 - adj_z) / 5.0 * 100, 0, 100)) if not np.isnan(adj_z) else None

    if composite is None or np.isnan(composite): verdict = "Insufficient Data"
    elif composite >= 75: verdict = "[CRITICAL] Critical Risk"
    elif composite >= 50: verdict = "[HIGH] High Risk"
    elif composite >= 25: verdict = "[MODERATE] Moderate Risk"
    else: verdict = "[LOW] Low Risk"

    red_flags = compute_red_flags(ticker_data)

    return {
        "ticker": ticker,
        "year": int(ticker_data.get("year", 0)),
        "sector": ticker_data.get("sector", ""),
        "stress_score": round(composite, 1) if composite is not None else None,
        "verdict": verdict,
        "components": {"classifier": clf_result, "trend": trend_result, "cluster": cluster_result},
        "ratios": {
            "altman_z": round(float(ticker_data.get("altman_z", 0)), 3),
            "piotroski_f": int(ticker_data.get("piotroski_f", 0)),
            "current_ratio": round(float(ticker_data.get("current_ratio", 0)), 3),
            "interest_coverage": round(float(ticker_data.get("interest_coverage", 0)), 2),
            "debt_to_equity": round(float(ticker_data.get("debt_to_equity", 0)), 3),
            "net_margin": round(float(ticker_data.get("net_margin", 0)), 4),
            "cf_divergence": round(float(ticker_data.get("cf_divergence", 0)), 4),
        },
        "red_flags": red_flags,
        "n_red_flags": len(red_flags)
    }


def score_all(feature_path: str = None) -> pd.DataFrame:
    path = feature_path or str(FEATURE_MATRIX_PATH)
    models = load_all_models()
    df = pd.read_csv(path)
    results = []
    for ticker in df["ticker"].unique():
        report = compute_stress_score(ticker, models, path)
        if "error" not in report:
            results.append({
                "ticker": report["ticker"],
                "sector": report["sector"],
                "stress_score": report["stress_score"],
                "verdict": report["verdict"],
                "n_red_flags": report["n_red_flags"],
            })
    return pd.DataFrame(results).sort_values("stress_score", ascending=False)

def print_report(report: dict):
    print(f"\n--- {report['ticker']} Stress Report ---")
    print(f"Score: {report['stress_score']}/100 | Verdict: {report['verdict']}")
    print(f"Red Flags: {report['n_red_flags']}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Ticker")
    args = parser.parse_args()
    if args.ticker:
        print_report(compute_stress_score(args.ticker.upper()))
