"""
src/models/live_scorer.py — Score any ticker live, even if not in dataset

Fetches fresh data from SEC EDGAR + yfinance, computes features on the fly,
then runs all 3 models. Used by the dashboard for unknown tickers.

Usage:
    from backend_core.models.live_scorer import score_live_ticker
    report = score_live_ticker("NVDA")
"""

import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

warnings.filterwarnings("ignore")

from backend_core.utils.logger import get_logger
from backend_core.config import RAW_DIR, FEATURE_MATRIX_PATH

logger = get_logger("live_scorer", "logs/live_scorer.log")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: FETCH LIVE DATA
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_data(ticker: str) -> dict:
    """
    Fetch financial statements for a ticker using SEC EDGAR + yfinance.
    Returns dict of {income: df, balance: df, cashflow: df} or empty if failed.
    """
    ticker = ticker.upper().strip()

    # Try SEC EDGAR first (most reliable, 10+ years)
    edgar_data = _fetch_edgar(ticker)
    if edgar_data:
        logger.info(f"{ticker}: fetched from SEC EDGAR")
        return edgar_data

    # Fall back to yfinance (4 years but reliable for active tickers)
    yf_data = _fetch_yfinance(ticker)
    if yf_data:
        logger.info(f"{ticker}: fetched from yfinance (EDGAR unavailable)")
        return yf_data

    logger.warning(f"{ticker}: could not fetch data from any source")
    return {}


def _fetch_edgar(ticker: str) -> dict:
    """Fetch from SEC EDGAR XBRL API."""
    try:
        import requests

        HEADERS = {"User-Agent": "FinancialStressResearch research@finstress.com"}

        # Get CIK
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS, timeout=15
        )
        tickers_map = {
            v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in r.json().values()
        }
        cik = tickers_map.get(ticker)
        if not cik:
            return {}

        # Fetch company facts
        r = requests.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            headers=HEADERS, timeout=30
        )
        if r.status_code != 200:
            return {}

        facts = r.json()

        # Use the same extraction logic as fetch_edgar.py
        from backend_core.data.fetch_edgar import build_statements
        statements = build_statements(ticker, facts)
        return statements if statements else {}

    except Exception as e:
        logger.warning(f"EDGAR fetch failed for {ticker}: {e}")
        return {}


def _fetch_yfinance(ticker: str) -> dict:
    """Fetch from yfinance as fallback."""
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)

        def clean(df):
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.T.copy()
            df.index = pd.to_datetime(df.index, errors="coerce").year
            df.index.name = "date"
            df = df.apply(pd.to_numeric, errors="coerce")
            df = df[(df.index >= 1990) & (df.index <= 2030)]
            return df

        return {
            "income":   clean(t.financials),
            "balance":  clean(t.balance_sheet),
            "cashflow": clean(t.cashflow),
        }
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {ticker}: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: COMPUTE FEATURES ON THE FLY
# ─────────────────────────────────────────────────────────────────────────────

def compute_live_features(ticker: str, statements: dict) -> tuple:
    """
    Compute all 20+ financial ratios from fresh statements.
    Returns a tuple of ({feature: value} for most recent year, feat_df).
    """
    try:
        # Save statements to temp CSV files so engineer.py can load them
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp())

        for name, df in statements.items():
            if not df.empty:
                df.to_csv(tmp_dir / f"{ticker}_{name}.csv")

        # Temporarily override RAW_DIR and compute
        from backend_core.features.engineer import (
            compute_features, COLS,
            load_statements as _load_statements,
        )

        # Load from temp dir
        stmts = {}
        for name in ["income", "balance", "cashflow"]:
            path = tmp_dir / f"{ticker}_{name}.csv"
            if path.exists():
                df = pd.read_csv(path, index_col=0)
                df.index = pd.to_numeric(df.index, errors="coerce")
                df = df[(df.index >= 1990) & (df.index <= 2030)].sort_index(ascending=False)
                df = df.apply(pd.to_numeric, errors="coerce")
                stmts[name] = df
            else:
                stmts[name] = pd.DataFrame()

        # Monkey-patch load_statements for this call
        import backend_core.features.engineer as eng_module
        original_load = eng_module.load_statements

        def patched_load(t):
            return stmts if t == ticker else original_load(t)

        eng_module.load_statements = patched_load

        try:
            feat_df = compute_features(ticker)
        finally:
            eng_module.load_statements = original_load

        # Cleanup
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        if feat_df.empty:
            return {}, pd.DataFrame()

        # Return most recent year's features as dict
        latest = feat_df.sort_values("year", ascending=False).iloc[0].to_dict()
        return latest, feat_df

    except Exception as e:
        logger.error(f"Feature computation failed for {ticker}: {e}")
        return {}, pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: SCORE LIVE TICKER
# ─────────────────────────────────────────────────────────────────────────────

def score_live_ticker(ticker: str, models: dict = None,
                       progress_callback=None) -> dict:
    """
    Full pipeline for a ticker not in the dataset:
    1. Fetch from SEC EDGAR / yfinance
    2. Compute 20+ financial ratios
    3. Run all 3 models
    4. Return full report

    Args:
        ticker:            stock ticker (e.g. "NVDA")
        models:            preloaded model dict (pass to avoid reloading)
        progress_callback: optional callable(step, message) for UI progress

    Returns:
        Same dict format as compute_stress_score()
    """
    ticker = ticker.upper().strip()

    def progress(step, msg):
        logger.info(f"{ticker} [{step}] {msg}")
        if progress_callback:
            progress_callback(step, msg)

    # 1. Check if already in dataset
    if os.path.exists(str(FEATURE_MATRIX_PATH)):
        df = pd.read_csv(str(FEATURE_MATRIX_PATH))
        if ticker in df["ticker"].values:
            progress("cache", "Found in dataset — using cached features")
            from backend_core.inference.scorer import compute_stress_score, load_all_models
            if models is None:
                models = load_all_models()
            return compute_stress_score(ticker, models)

    # 2. Fetch live data
    progress("fetch", "Fetching financial data from SEC EDGAR...")
    statements = fetch_live_data(ticker)

    if not statements or all(
        df is None or (hasattr(df, 'empty') and df.empty)
        for df in statements.values()
    ):
        return {
            "ticker": ticker,
            "error":  (
                f"Could not fetch data for {ticker}. "
                "This ticker may be delisted, private, or not an SEC filer. "
                "Only US public companies listed on NYSE/NASDAQ are supported."
            ),
            "score": None,
        }

    # 3. Compute features
    progress("compute", "Computing financial ratios...")
    ticker_data, feat_df = compute_live_features(ticker, statements)

    if not ticker_data:
        return {
            "ticker": ticker,
            "error":  f"Could not compute features for {ticker}. Insufficient financial data.",
            "score":  None,
        }

    # Try to get sector from yfinance metadata
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        ticker_data["sector"] = info.get("sector", "Unknown")
        ticker_data["ticker"] = ticker
        ticker_data["year"]   = pd.Timestamp.now().year
    except:
        ticker_data["sector"] = "Unknown"
        ticker_data["ticker"] = ticker
        ticker_data["year"]   = pd.Timestamp.now().year

    # 4. Run models
    progress("score", "Running distress models...")
    if models is None:
        from backend_core.inference.scorer import load_all_models
        models = load_all_models()

    from backend_core.inference.scorer import (
        get_classifier_score, get_trend_score, get_cluster_score,
        compute_red_flags, interpret_altman, interpret_piotroski,
        adjusted_altman_z, WEIGHTS, LOW_Z_SECTORS,
    )

    sector = ticker_data.get("sector", "")

    clf_result     = get_classifier_score(ticker_data, models)
    # Trend: compute from history if we have multiple years
    trend_result   = {"score": 0.0, "available": True,
                      "note": "Live fetch — trend requires historical data"}

    # Try to get trend from history
    try:
        from backend_core.inference.trend import predict_trend_from_history
        # Build a DataFrame from all available years
        all_years_data = []
        income   = statements.get("income",   pd.DataFrame())
        balance  = statements.get("balance",  pd.DataFrame())
        cashflow = statements.get("cashflow", pd.DataFrame())

        if not income.empty:
            for year in income.index:
                row = {"ticker": ticker, "year": int(year)}
                # Add key metrics per year
                for col in income.columns:
                    row[col] = income.loc[year, col] if year in income.index else np.nan
                all_years_data.append(row)

        if all_years_data and len(all_years_data) >= 3:
            hist_df = pd.DataFrame(all_years_data)
            # Map to feature names
            from backend_core.features.engineer import compute_features as _cf
            trend_result = predict_trend_from_history(hist_df)
            trend_result["available"] = True
    except Exception as e:
        logger.warning(f"Trend from history failed: {e}")

    cluster_result = get_cluster_score(ticker_data, models)
    red_flags      = compute_red_flags(ticker_data)

    # Composite score
    weighted_sum = 0.0
    total_weight = 0.0

    if clf_result["available"] and not np.isnan(clf_result.get("score", np.nan)):
        weighted_sum += clf_result["score"] * WEIGHTS["classifier"]
        total_weight += WEIGHTS["classifier"]
    if trend_result.get("available") and not np.isnan(trend_result.get("score", 0) or 0):
        weighted_sum += (trend_result.get("score") or 0) * WEIGHTS["trend"]
        total_weight += WEIGHTS["trend"]
    if cluster_result.get("available") and not np.isnan(cluster_result.get("score", np.nan)):
        weighted_sum += cluster_result["score"] * WEIGHTS["cluster"]
        total_weight += WEIGHTS["cluster"]

    composite = float(np.clip(weighted_sum / total_weight, 0, 100)) \
                if total_weight > 0 else np.nan

    if composite is None or np.isnan(composite):
        verdict = "Insufficient Data"
    elif composite >= 75:   verdict = "[CRITICAL] Critical Risk"
    elif composite >= 50:   verdict = "[HIGH] High Risk"
    elif composite >= 25:   verdict = "[MODERATE] Moderate Risk"
    else:                   verdict = "[LOW] Low Risk"

    def safe_round(v, n=3):
        if v is None or (isinstance(v, float) and np.isnan(v)): return None
        return round(float(v), n)

    raw_z = ticker_data.get("altman_z", np.nan)
    adj_z = adjusted_altman_z(raw_z, sector)

    return {
        "ticker":       ticker,
        "year":         int(ticker_data.get("year", 0)),
        "sector":       sector,
        "stress_score": round(composite, 1) if not np.isnan(composite) else None,
        "verdict":      verdict,
        "live":         True,   # flag that this was a live fetch
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
        "data_source": "SEC EDGAR (live fetch)",
        "history": feat_df.sort_values("year", ascending=True).replace({np.nan: None}).to_dict("records") if not feat_df.empty else [],
    }
