"""
models/trend.py — Deterioration Trend Scorer

Split awareness:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Loads train/val/test ticker split from classifier_meta.json
- Baseline standard deviations computed on TRAIN companies only
  (used to standardize deterioration slopes)
- Wilcoxon validation run on TRAIN+VAL companies only
  (test companies excluded from validation metrics)
- Test companies still get trend scores (prediction, not training)
- Synthetic data excluded entirely (no real time series)

Why trend needs split awareness:
  The baseline_stds are used to standardize slopes across companies.
  If test companies influence these baselines, the standardization
  leaks information about test distribution into the scoring.

Other best practices:
- Min 3 years for reliable OLS slope
- p < 0.15 significance filter (noisy trends contribute 0)
- Acceleration detection (second derivative)
- Wilcoxon rank-sum validation
- SHA-256 integrity hash

Run: .venv\Scripts\python.exe backend_core.engine/trend.py
"""

import os
import sys
import json
import hashlib
import pickle
import warnings
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

warnings.filterwarnings("ignore")

from backend_core.utils.logger import get_logger
from backend_core.config import (
    LOGS_DIR, MODELS_DIR,
    TREND_PATH, TREND_META_PATH,
    CLASSIFIER_META_PATH,
    FEATURE_MATRIX_EXPANDED_PATH, FEATURE_MATRIX_PATH,
)

logger = get_logger("trend", LOGS_DIR / "trend.log")

MODEL_PATH    = TREND_PATH
META_PATH     = TREND_META_PATH
MIN_YEARS     = 3
SIG_THRESHOLD = 0.15
SYNTHETIC_TAG = "synthetic"

TREND_METRICS = {
    "altman_z":          "down",
    "piotroski_f":       "down",
    "current_ratio":     "down",
    "quick_ratio":       "down",
    "cash_ratio":        "down",
    "net_margin":        "down",
    "gross_margin":      "down",
    "roa":               "down",
    "roe":               "down",
    "interest_coverage": "down",
    "debt_to_equity":    "up",
    "debt_to_ebitda":    "up",
    "cf_divergence":     "down",
}

METRIC_WEIGHTS = {
    "altman_z":          3.0,
    "interest_coverage": 2.5,
    "net_margin":        2.5,
    "piotroski_f":       2.0,
    "current_ratio":     2.0,
    "roa":               2.0,
    "debt_to_equity":    1.5,
    "debt_to_ebitda":    1.5,
    "gross_margin":      1.5,
    "cf_divergence":     2.0,
    "cash_ratio":        1.5,
    "quick_ratio":       1.0,
    "roe":               1.0,
}


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────────────────────────────────────

def compute_hash(path) -> str:
    sha256 = hashlib.sha256()
    with open(str(path), "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_integrity(model_path=MODEL_PATH, meta_path=META_PATH) -> bool:
    if not os.path.exists(str(model_path)) or not os.path.exists(str(meta_path)):
        return False
    with open(str(meta_path)) as f:
        meta = json.load(f)
    if compute_hash(model_path) != meta.get("model_hash"):
        logger.error("SECURITY: Trend model hash mismatch!")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# LOAD TICKER SPLIT
# ─────────────────────────────────────────────────────────────────────────────

def load_ticker_split() -> tuple:
    """Load train/val/test tickers from classifier_meta.json."""
    meta_path = str(CLASSIFIER_META_PATH)
    if not os.path.exists(meta_path):
        logger.warning(
            "classifier_meta.json not found. Run classifier.py first. "
            "Falling back to all companies for baseline computation."
        )
        return None, None, None

    with open(meta_path) as f:
        meta = json.load(f)

    train = set(meta.get("train_tickers", []))
    val   = set(meta.get("val_tickers",   []))
    test  = set(meta.get("test_tickers",  []))

    logger.info(f"Loaded ticker split: train={len(train)} val={len(val)} test={len(test)}")
    return train, val, test


# ─────────────────────────────────────────────────────────────────────────────
# TREND COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_trend(values: pd.Series) -> dict:
    values = pd.to_numeric(values, errors="coerce").dropna()
    n      = len(values)

    null = {"slope": np.nan, "acceleration": np.nan, "r_squared": np.nan,
            "p_value": np.nan, "significant": False,
            "direction": "insufficient_data", "n_years": n}

    if n < MIN_YEARS:
        return null

    x = np.arange(n, dtype=float)
    y = values.values.astype(float)

    # Remove within-series outliers
    s_std = y.std()
    if s_std > 0:
        mask = np.abs(y - y.mean()) <= 3 * s_std
        if mask.sum() >= MIN_YEARS:
            x, y = x[mask], y[mask]

    if len(y) < MIN_YEARS:
        return null

    try:
        slope, _, r, p, _ = stats.linregress(x, y)
    except Exception:
        return null

    try:
        coeffs       = np.polyfit(x, y, 2)
        acceleration = float(coeffs[0] * 2)
    except Exception:
        acceleration = np.nan

    significant = p < SIG_THRESHOLD and abs(slope) > 1e-6
    direction   = ("stable_or_noisy" if not significant else
                   "increasing"      if slope > 0 else "decreasing")

    return {"slope": float(slope), "acceleration": acceleration,
            "r_squared": float(r**2), "p_value": float(p),
            "significant": significant, "direction": direction,
            "n_years": int(len(y))}


def compute_company_trends(ticker_df: pd.DataFrame) -> dict:
    ticker_df = ticker_df.sort_values("year", ascending=True)
    trends    = {}

    for metric, detr_dir in TREND_METRICS.items():
        if metric not in ticker_df.columns:
            continue
        trend = compute_trend(ticker_df[metric])
        trend["metric"]   = metric
        trend["detr_dir"] = detr_dir

        if not np.isnan(trend["slope"]) and trend["significant"]:
            trend["detr_slope"] = (-trend["slope"] if detr_dir == "down"
                                   else trend["slope"])
        else:
            trend["detr_slope"] = np.nan

        trends[metric] = trend
    return trends


def compute_deterioration_index(trends: dict, baseline_stds: dict) -> float:
    weighted = []
    for metric, trend in trends.items():
        detr_slope = trend.get("detr_slope", np.nan)
        if not trend.get("significant", False) or np.isnan(detr_slope):
            continue
        baseline_std = baseline_stds.get(metric, 1.0)
        if baseline_std <= 0 or np.isnan(baseline_std):
            continue
        standardized = detr_slope / baseline_std
        weight       = METRIC_WEIGHTS.get(metric, 1.0)
        weighted.append(standardized * weight)

    return float(np.mean(weighted)) if weighted else np.nan


def detect_red_flags(trends: dict) -> list:
    flags = []
    for metric, trend in trends.items():
        if not trend.get("significant", False):
            continue
        detr_slope = trend.get("detr_slope", np.nan)
        if np.isnan(detr_slope) or detr_slope <= 0:
            continue

        accel    = trend.get("acceleration", np.nan)
        detr_dir = trend.get("detr_dir", "down")
        p_value  = trend.get("p_value", 1.0)

        severity     = "HIGH" if p_value < 0.05 else "MODERATE"
        accelerating = (not np.isnan(accel) and
                        ((detr_dir == "down" and accel < -0.005) or
                         (detr_dir == "up"   and accel >  0.005)))

        flags.append({"metric": metric, "severity": severity,
                      "detr_slope": round(float(detr_slope), 5),
                      "p_value": round(float(p_value), 4),
                      "r_squared": round(float(trend.get("r_squared", 0)), 4),
                      "accelerating": accelerating,
                      "n_years": int(trend.get("n_years", 0))})

    flags.sort(key=lambda x: (x["severity"]=="HIGH", x["detr_slope"]), reverse=True)
    return flags


# ─────────────────────────────────────────────────────────────────────────────
# BUILD TREND MATRIX
# ─────────────────────────────────────────────────────────────────────────────

def build_trend_matrix(df: pd.DataFrame,
                        baseline_stds: dict) -> pd.DataFrame:
    """Compute trend scores for all real companies."""
    is_synthetic = df.get(
        "label_source", pd.Series("", index=df.index)
    ).str.contains(SYNTHETIC_TAG, na=False)
    real_df = df[~is_synthetic].copy()

    tickers = real_df["ticker"].unique()
    rows    = []
    skipped = 0

    for ticker in tickers:
        t_df = real_df[real_df["ticker"] == ticker].sort_values("year")
        if len(t_df) < MIN_YEARS:
            skipped += 1
            continue

        trends    = compute_company_trends(t_df)
        det_index = compute_deterioration_index(trends, baseline_stds)
        flags     = detect_red_flags(trends)
        n_sig     = sum(1 for t in trends.values() if t.get("significant", False))

        row = {
            "ticker":               ticker,
            "sector":               t_df["sector"].iloc[-1] if "sector" in t_df else "Unknown",
            "n_years":              len(t_df),
            "n_significant_trends": n_sig,
            "deterioration_index":  det_index,
            "n_red_flags":          len(flags),
            "n_high_flags":         sum(1 for f in flags if f["severity"] == "HIGH"),
            "has_accelerating":     any(f["accelerating"] for f in flags),
            "top_flags":            [f["metric"] for f in flags[:3]],
            "distress_label":       int(t_df["distress_label"].max())
                                    if "distress_label" in t_df else 0,
        }
        for metric, trend in trends.items():
            row[f"{metric}_slope"] = trend.get("slope", np.nan)
            row[f"{metric}_detr"]  = trend.get("detr_slope", np.nan)
            row[f"{metric}_sig"]   = int(trend.get("significant", False))

        rows.append(row)

    trend_df = pd.DataFrame(rows)
    logger.info(f"Trend matrix: {trend_df.shape} | Skipped: {skipped} (<{MIN_YEARS} years)")
    return trend_df


# ─────────────────────────────────────────────────────────────────────────────
# WILCOXON VALIDATION — train+val only
# ─────────────────────────────────────────────────────────────────────────────

def validate_trend_scorer(trend_df: pd.DataFrame,
                           validation_tickers: set = None) -> dict:
    """
    Wilcoxon rank-sum test on validation (train+val) companies only.
    Test companies excluded — they must not influence validation metrics.
    """
    if validation_tickers is not None:
        val_df = trend_df[trend_df["ticker"].isin(validation_tickers)]
    else:
        val_df = trend_df

    valid      = val_df.dropna(subset=["deterioration_index", "distress_label"])
    healthy    = valid[valid["distress_label"] == 0]["deterioration_index"]
    distressed = valid[valid["distress_label"] == 1]["deterioration_index"]

    logger.info(f"\n--- Wilcoxon Validation (train+val companies only) ---")
    logger.info(f"Healthy    n={len(healthy):4d} | median={healthy.median():.4f}")
    logger.info(f"Distressed n={len(distressed):4d} | median={distressed.median():.4f}")

    validation = {
        "healthy_n":         len(healthy),
        "distressed_n":      len(distressed),
        "healthy_median":    float(healthy.median())    if len(healthy)    > 0 else 0.0,
        "distressed_median": float(distressed.median()) if len(distressed) > 0 else 0.0,
        "test_excluded":     True,
    }

    if len(distressed) < 3:
        logger.warning("Too few distressed samples for Wilcoxon (n<3)")
        validation["note"] = "insufficient_distressed_samples"
        return validation

    try:
        stat, p = stats.mannwhitneyu(distressed, healthy, alternative="greater")
        logger.info(f"Mann-Whitney U: {stat:.2f} | p-value (one-sided): {p:.4f}")
        if p < 0.05:
            logger.info("[VALIDATED] Distressed score higher (p<0.05)")
        elif p < 0.10:
            logger.info("[MARGINAL] Borderline significant (p<0.10)")
        else:
            logger.warning(f"[NOT VALIDATED] p={p:.4f} — trend scorer weak signal")
            logger.warning("Score included in ensemble with reduced weight (10%)")

        validation["stat"]      = float(stat)
        validation["p_value"]   = float(p)
        validation["validated"] = bool(p < 0.10)
    except Exception as e:
        logger.warning(f"Wilcoxon failed: {e}")
        validation["note"] = str(e)

    return validation


# ─────────────────────────────────────────────────────────────────────────────
# SAVE / LOAD
# ─────────────────────────────────────────────────────────────────────────────

def save_model(trend_df, baseline_stds, validation, train_tickers, test_tickers):
    obj = {
        "trend_matrix":   trend_df,
        "baseline_stds":  baseline_stds,
        "metric_weights": METRIC_WEIGHTS,
        "trend_metrics":  TREND_METRICS,
        "validation":     validation,
        "min_years":      MIN_YEARS,
        "sig_threshold":  SIG_THRESHOLD,
        "train_tickers":  list(train_tickers) if train_tickers else [],
        "test_tickers":   list(test_tickers)  if test_tickers  else [],
        "version":        "2.2",
    }

    with open(str(MODEL_PATH), "wb") as f:
        pickle.dump(obj, f)

    model_hash = compute_hash(MODEL_PATH)
    meta = {
        "version":         "2.2",
        "trained_at":      datetime.utcnow().isoformat() + "Z",
        "model_hash":      model_hash,
        "n_companies":     len(trend_df),
        "metrics_tracked": list(TREND_METRICS.keys()),
        "min_years":       MIN_YEARS,
        "sig_threshold":   SIG_THRESHOLD,
        "algorithm":       "OLS per metric + quadratic acceleration",
        "split_aware":     True,
        "baseline_from":   "train companies only",
        "validation":      validation,
        "validated":       validation.get("validated", False),
    }
    with open(str(META_PATH), "w") as f:
        json.dump(meta, f, indent=2)

    trend_df.to_csv(str(MODELS_DIR / "trend_scores.csv"), index=False)
    logger.info(f"\nTrend model saved: {MODEL_PATH}")
    logger.info(f"Hash: {model_hash[:16]}...")


def load_model(model_path=MODEL_PATH, meta_path=META_PATH):
    if not verify_integrity(model_path, meta_path):
        raise ValueError("Trend integrity check failed")
    with open(str(model_path), "rb") as f:
        return pickle.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# PREDICT API
# ─────────────────────────────────────────────────────────────────────────────

def predict_trend(ticker: str,
                  model_path=MODEL_PATH, meta_path=META_PATH) -> dict:
    obj      = load_model(model_path, meta_path)
    trend_df = obj["trend_matrix"]
    row      = trend_df[trend_df["ticker"] == ticker]

    if row.empty:
        return {"deterioration_index": np.nan, "n_red_flags": 0,
                "top_flags": [], "has_accelerating": False,
                "note": f"No trend data for {ticker} (needs >={MIN_YEARS} years)"}

    r = row.iloc[0]
    return {
        "deterioration_index":  float(r["deterioration_index"])
                                if not pd.isna(r["deterioration_index"]) else np.nan,
        "n_red_flags":          int(r["n_red_flags"]),
        "n_high_flags":         int(r["n_high_flags"]),
        "n_significant_trends": int(r["n_significant_trends"]),
        "top_flags":            r["top_flags"] if isinstance(r["top_flags"], list) else [],
        "has_accelerating":     bool(r["has_accelerating"]),
        "n_years":              int(r["n_years"]),
    }


def predict_trend_from_history(ticker_df: pd.DataFrame,
                                model_path=MODEL_PATH,
                                meta_path=META_PATH) -> dict:
    obj           = load_model(model_path, meta_path)
    baseline_stds = obj["baseline_stds"]
    trends        = compute_company_trends(ticker_df)
    det_index     = compute_deterioration_index(trends, baseline_stds)
    flags         = detect_red_flags(trends)
    return {
        "deterioration_index": det_index,
        "n_red_flags":         len(flags),
        "n_high_flags":        sum(1 for f in flags if f["severity"] == "HIGH"),
        "top_flags":           [f["metric"] for f in flags[:3]],
        "has_accelerating":    any(f["accelerating"] for f in flags),
        "detailed_flags":      flags,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run():
    logger.info("=" * 60)
    logger.info("MODEL C - Deterioration Trend Scorer v2.2 (Production)")
    logger.info("Split-aware | Baseline from train only | Test excluded from validation")
    logger.info("=" * 60)

    # 1. Load data
    path = str(FEATURE_MATRIX_EXPANDED_PATH)
    if not os.path.exists(path):
        path = str(FEATURE_MATRIX_PATH)
        logger.warning(f"Using original matrix: {path}")

    df = pd.read_csv(path)
    logger.info(f"Data: {df.shape}")

    # 2. Load ticker split
    train_tickers, val_tickers, test_tickers = load_ticker_split()

    # 3. Baseline stds from TRAIN companies only
    is_synthetic = df.get(
        "label_source", pd.Series("", index=df.index)
    ).str.contains(SYNTHETIC_TAG, na=False)
    real_df = df[~is_synthetic].copy()

    if train_tickers is not None:
        train_df = real_df[real_df["ticker"].isin(train_tickers)]
        logger.info(f"Baseline computed from {train_df['ticker'].nunique()} train companies")
    else:
        train_df = real_df
        logger.warning("No split info — using all companies for baseline")

    baseline_stds = {}
    for metric in TREND_METRICS:
        if metric in train_df.columns:
            std = train_df[metric].std()
            baseline_stds[metric] = max(float(std), 1e-6)

    # 4. Build trend matrix for ALL real companies
    logger.info(f"Computing trends for {real_df['ticker'].nunique()} real tickers...")
    trend_df = build_trend_matrix(df, baseline_stds)

    if trend_df.empty:
        logger.error("No trends computed.")
        return

    # 5. Wilcoxon validation on train+val only (exclude test)
    if train_tickers is not None and val_tickers is not None:
        validation_tickers = train_tickers | val_tickers
    else:
        validation_tickers = None

    validation = validate_trend_scorer(trend_df, validation_tickers)

    # 6. Top deteriorating companies
    logger.info(f"\n--- Top 15 Most Deteriorating Companies ---")
    top_cols = ["ticker", "sector", "deterioration_index", "n_red_flags",
                "n_high_flags", "n_years", "has_accelerating", "top_flags",
                "distress_label"]
    top = trend_df.nlargest(15, "deterioration_index")[top_cols]
    logger.info(top.to_string(index=False))

    # 7. Stats by label
    logger.info(f"\n--- Trend Score Stats by Label ---")
    for label in [0, 1]:
        sub = trend_df[trend_df["distress_label"] == label]["deterioration_index"].dropna()
        name = "Healthy" if label == 0 else "Distressed"
        if len(sub) > 0:
            logger.info(f"{name}: n={len(sub)} | median={sub.median():.4f} | "
                        f"mean={sub.mean():.4f} | std={sub.std():.4f}")

    # 8. Save
    save_model(trend_df, baseline_stds, validation,
               train_tickers or set(), test_tickers or set())

    logger.info("\n" + "=" * 60)
    logger.info("Trend scorer complete.")
    logger.info(f"Companies scored: {len(trend_df)}")
    logger.info(f"Validated: {validation.get('validated', 'N/A')}")
    logger.info("=" * 60)

    return trend_df


if __name__ == "__main__":
    run()
