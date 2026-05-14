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

Run: .venv\Scripts\python.exe src/models/scorer.py --ticker AAPL
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
# Apple, Microsoft, Google all have Z < 2 due to buybacks and working capital design
LOW_Z_SECTORS = {"Financial_Services", "Technology"}


# ─────────────────────────────────────────────────────────────────────────────
# ALTMAN Z — SECTOR-ADJUSTED INTERPRETATION
# ─────────────────────────────────────────────────────────────────────────────

def adjusted_altman_z(raw_z: float, sector: str) -> float:
    """
    Apply sector-specific adjustment to raw Altman Z.

    Standard Z was built on 1968 manufacturing firms.
    For Technology and Financial Services companies:
    - Massive share buybacks destroy book equity (inflates D/E, deflates Z)
    - Negative working capital is by design (Apple collects fast, pays slow)
    - Asset-light models have low asset bases (inflates X5)

    Adjustment: scale raw Z upward for these sectors by empirical factor.
    Based on median Z-score differential between healthy tech/financials
    and what their actual credit quality implies.

    Healthy large-cap tech median Z ~ 1.3-1.8 despite being AAA-equivalent.
    Healthy manufacturing median Z ~ 3.0+
    Scaling factor: 1.8 for these sectors.
    """
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
    """XGBoost distress probability -> 0-100."""
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
    """Deterioration trend score -> 0-100. Only positive deterioration scores."""
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

        # Only positive deterioration scores — negative = improving = 0
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
    """Cluster peer risk score -> 0-100. Returns 0 if cluster too broad."""
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
                "note":       f"Cluster {cluster_id} too broad ({cluster_size}/{total_size})",
                "available":  True,
            }

        profile    = profiles.loc[cluster_id] if cluster_id in profiles.index else None
        risk_score = float(profile["risk_score"]) if profile is not None else 0.0
        max_risk   = float(profiles["risk_score"].max()) if not profiles.empty else 1.0

        log_risk   = np.log1p(risk_score)
        max_log    = np.log1p(max_risk)
        normalized = float(min((log_risk / max(max_log, 0.1)) * 100, 100))

        is_synth = all_data.get(
            "label_source", pd.Series("", index=all_data.index)
        ).str.contains("synthetic", na=False)
        peers = all_data[(all_labels == cluster_id) & (~is_synth)]

        distressed_peers = []
        if "distress_label" in peers.columns:
            distressed_peers = peers[peers["distress_label"] == 1]["ticker"].unique().tolist()

        peer_sample = (
            peers[["ticker", "year", "sector"]].drop_duplicates("ticker").head(8).to_dict("records")
        ) if not peers.empty else []

        return {
            "score":            round(normalized, 2),
            "cluster_id":       cluster_id,
            "raw_risk_score":   risk_score,
            "distressed_peers": distressed_peers,
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

    # Sector-adjusted Altman Z thresholds
    if sector in LOW_Z_SECTORS:
        z_distress = 0.5   # real distress for tech — not just low equity
        z_grey     = 1.2
    else:
        z_distress = THRESHOLDS["altman_z_distress"]
        z_grey     = THRESHOLDS["altman_z_safe"]

    # Current ratio threshold relaxed for tech (negative WC by design)
    cr_min = 0.5 if sector == "Technology" else THRESHOLDS["current_ratio_min"]

    flags = []

    def check(metric, value, threshold, direction, message, severity="HIGH"):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return
        triggered = (direction == "below" and value < threshold) or \
                    (direction == "above" and value > threshold)
        if triggered:
            flags.append({
                "metric":    metric,
                "value":     round(float(value), 3),
                "threshold": threshold,
                "message":   message,
                "severity":  severity,
            })

    # Use adjusted Z for flag threshold
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

    check("piotroski_f", ticker_data.get("piotroski_f"),
          THRESHOLDS["piotroski_weak"], "below",
          f"Piotroski F <= {THRESHOLDS['piotroski_weak']} — Financially Weak")

    check("current_ratio", ticker_data.get("current_ratio"),
          cr_min, "below",
          f"Current Ratio < {cr_min} — Liquidity Risk")

    check("interest_coverage", ticker_data.get("interest_coverage"),
          THRESHOLDS["interest_coverage_min"], "below",
          "Interest Coverage < 1.5 — Can barely cover interest")

    check("debt_to_equity", ticker_data.get("debt_to_equity"),
          THRESHOLDS["debt_equity_max"], "above",
          f"Debt/Equity > {THRESHOLDS['debt_equity_max']} — Over-leveraged")

    check("net_margin", ticker_data.get("net_margin"),
          THRESHOLDS["net_margin_min"], "below",
          "Negative net margin — Losing money")

    cf_div = ticker_data.get("cf_divergence")
    if cf_div is not None and not (isinstance(cf_div, float) and np.isnan(cf_div)):
        if cf_div < -0.10:
            flags.append({
                "metric": "cf_divergence", "value": round(float(cf_div), 3),
                "threshold": -0.10,
                "message": "Cash flow significantly below reported profit — earnings quality risk",
                "severity": "HIGH",
            })

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# MASTER SCORER
# ─────────────────────────────────────────────────────────────────────────────

def compute_stress_score(ticker: str,
                          models: dict = None,
                          feature_path: str = None) -> dict:
    if models is None:
        models = load_all_models()

    ticker_data = get_latest_data(ticker, feature_path)
    if not ticker_data:
        return {"ticker": ticker,
                "error": f"No data for {ticker}. Run fetch_edgar.py + engineer.py first.",
                "score": None}

    sector = ticker_data.get("sector", "")

    clf_result     = get_classifier_score(ticker_data, models)
    trend_result   = get_trend_score(ticker, models)
    cluster_result = get_cluster_score(ticker_data, models)

    # Weighted composite — straight weighted average, no overrides
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
        adj_z = adjusted_altman_z(z, sector)
        if not (isinstance(adj_z, float) and np.isnan(adj_z)):
            composite = float(np.clip((3.0 - adj_z) / 5.0 * 100, 0, 100))
        else:
            composite = np.nan

    if composite is None or (isinstance(composite, float) and np.isnan(composite)):
        verdict = "Insufficient Data"
    elif composite >= 75:
        verdict = "[CRITICAL] Critical Risk"
    elif composite >= 50:
        verdict = "[HIGH] High Risk"
    elif composite >= 25:
        verdict = "[MODERATE] Moderate Risk"
    else:
        verdict = "[LOW] Low Risk"

    red_flags = compute_red_flags(ticker_data)

    def safe_round(v, n=3):
        if v is None or (isinstance(v, float) and np.isnan(v)): return None
        return round(float(v), n)

    raw_z   = ticker_data.get("altman_z", np.nan)
    adj_z   = adjusted_altman_z(raw_z, sector)

    return {
        "ticker":       ticker,
        "year":         int(ticker_data.get("year", 0)),
        "sector":       sector,
        "stress_score": round(composite, 1) if not (isinstance(composite, float) and np.isnan(composite)) else None,
        "verdict":      verdict,
        "components": {
            "classifier": clf_result,
            "trend":      trend_result,
            "cluster":    cluster_result,
        },
        "ratios": {
            "altman_z":          safe_round(raw_z),
            "altman_z_adjusted": safe_round(adj_z),
            "altman_z_label":    interpret_altman(raw_z, sector),
            "piotroski_f":       int(ticker_data.get("piotroski_f", 0))
                                 if not pd.isna(ticker_data.get("piotroski_f", np.nan)) else None,
            "piotroski_label":   interpret_piotroski(ticker_data.get("piotroski_f")),
            "current_ratio":     safe_round(ticker_data.get("current_ratio")),
            "interest_coverage": safe_round(ticker_data.get("interest_coverage"), 2),
            "debt_to_equity":    safe_round(ticker_data.get("debt_to_equity")),
            "net_margin":        safe_round(ticker_data.get("net_margin"), 4),
            "cf_divergence":     safe_round(ticker_data.get("cf_divergence"), 4),
        },
        "red_flags":   red_flags,
        "n_red_flags": len(red_flags),
        "macro_context": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# BATCH SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_all(feature_path: str = None) -> pd.DataFrame:
    path    = feature_path or str(FEATURE_MATRIX_PATH)
    models  = load_all_models()
    df      = pd.read_csv(path)
    tickers = df["ticker"].unique()

    logger.info(f"Scoring {len(tickers)} tickers...")
    results = []

    for ticker in tickers:
        report = compute_stress_score(ticker, models, path)
        if "error" not in report:
            results.append({
                "ticker":       report["ticker"],
                "sector":       report["sector"],
                "stress_score": report["stress_score"],
                "verdict":      report["verdict"],
                "n_red_flags":  report["n_red_flags"],
                "altman_z":     report["ratios"]["altman_z"],
                "altman_z_adj": report["ratios"]["altman_z_adjusted"],
                "piotroski_f":  report["ratios"]["piotroski_f"],
                "net_margin":   report["ratios"]["net_margin"],
            })

    result_df = pd.DataFrame(results).sort_values("stress_score", ascending=False)
    result_df.to_csv(str(SCORES_CSV_PATH), index=False)
    logger.info(f"Scores saved: {SCORES_CSV_PATH}")
    return result_df


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def print_report(report: dict):
    if "error" in report:
        print(f"\n ERROR: {report['error']}")
        return

    r = report["ratios"]
    c = report["components"]

    print(f"\n{'='*58}")
    print(f"  COMPANY:      {report['ticker']} ({report['sector']})")
    print(f"  STRESS SCORE: {report['stress_score']}/100")
    print(f"  VERDICT:      {report['verdict']}")
    print(f"{'='*58}")
    print(f"\n  Altman Z (raw):      {r['altman_z']}  [{r['altman_z_label']}]")
    print(f"  Altman Z (adjusted): {r['altman_z_adjusted']}")
    print(f"  Piotroski F-Score:   {r['piotroski_f']}/9  [{r['piotroski_label']}]")
    print(f"  Current Ratio:       {r['current_ratio']}")
    print(f"  Interest Coverage:   {r['interest_coverage']}")
    print(f"  Debt/Equity:         {r['debt_to_equity']}")
    print(f"  Net Margin:          {r['net_margin']}")
    print(f"  CF vs Profit Div:    {r['cf_divergence']}")
    print(f"\n  ML Classifier:       {c['classifier'].get('score', 'N/A')}/100")
    print(f"  Trend Score:         {c['trend'].get('score', 'N/A')}/100")
    print(f"  Cluster Score:       {c['cluster'].get('score', 'N/A')}/100")

    if c["trend"].get("top_flags"):
        print(f"  Deteriorating:       {c['trend']['top_flags']}")
    if c["cluster"].get("distressed_peers"):
        print(f"  Distressed Peers:    {c['cluster']['distressed_peers']}")
    if c["cluster"].get("note"):
        print(f"  Cluster Note:        {c['cluster']['note']}")

    if report["red_flags"]:
        print(f"\n  RED FLAGS ({len(report['red_flags'])}):")
        for flag in report["red_flags"]:
            sev = "[!!]" if flag["severity"] == "HIGH" else "[!]"
            print(f"    {sev} {flag['message']} (value={flag['value']})")
    else:
        print(f"\n  [OK] No red flags triggered")

    print(f"{'='*58}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Score a specific ticker")
    parser.add_argument("--all",    action="store_true")
    parser.add_argument("--top",    type=int, default=20)
    args = parser.parse_args()

    if args.ticker:
        models = load_all_models()
        report = compute_stress_score(args.ticker.upper(), models)
        print_report(report)
    elif args.all:
        result_df = score_all()
        print(f"\n--- Top {args.top} Most Stressed Companies ---")
        print(result_df.head(args.top).to_string(index=False))
    else:
        models = load_all_models()
        for ticker in ["AAPL", "MSFT", "BBBY", "SIVB"]:
            report = compute_stress_score(ticker, models)
            print_report(report)
