"""
dashboard/server.py — Flask REST API for Financial Stress Dashboard

Serves the static frontend and exposes JSON endpoints that connect
to the existing scorer, live_scorer, and feature matrix modules.

Run:  .venv\\Scripts\\python.exe dashboard/server.py
Open: http://localhost:5000
"""

import os
import sys
import warnings
from pathlib import Path

# ─── THE MEGA-FIX ───────────────────────────────────────────────────────────
import os
import sys
from pathlib import Path
import importlib.util

BASE_DIR = Path(__file__).resolve().parent.parent
print(f"DEBUG: BASE_DIR is {BASE_DIR}")
print(f"DEBUG: BASE_DIR contents: {os.listdir(str(BASE_DIR))}")

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Try to find 'src' directory
SRC_DIR = BASE_DIR / "src"
if not SRC_DIR.exists():
    # If we are inside 'src' already (some hosts do this)
    if (BASE_DIR / "models").exists():
        SRC_DIR = BASE_DIR
    else:
        print("CRITICAL: Could not find 'src' or 'models' directory!")

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    # Attempt 1: Standard import
    from src.config import FEATURE_MATRIX_PATH, SCORES_CSV_PATH
    from src.models.scorer import compute_stress_score, load_all_models, score_all, get_ticker_history
    from src.utils.hf_sync import sync_models
    from src.utils.logger import get_logger
except ImportError as e:
    print(f"DEBUG: Attempt 1 failed: {e}")
    try:
        # Attempt 2: Direct import from src
        from config import FEATURE_MATRIX_PATH, SCORES_CSV_PATH
        from models.scorer import compute_stress_score, load_all_models, score_all, get_ticker_history
        from utils.hf_sync import sync_models
        from utils.logger import get_logger
    except ImportError as e2:
        print(f"DEBUG: Attempt 2 failed: {e2}")
        raise e2
# ─────────────────────────────────────────────────────────────────────────────

logger = get_logger("dashboard", "logs/dashboard.log")

STATIC_DIR = Path(__file__).parent / "static"
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")

_models = None
_scores_df = None


def get_models():
    global _models
    if _models is None:
        logger.info("Loading ML models...")
        _models = load_all_models()
    return _models


def get_scores_df():
    global _scores_df
    if _scores_df is not None:
        return _scores_df
    path = str(SCORES_CSV_PATH)
    if os.path.exists(path):
        _scores_df = pd.read_csv(path)
    else:
        _scores_df = score_all()
    return _scores_df


def safe_val(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        if np.isnan(v) or np.isinf(v):
            return None
        return round(float(v), 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def clean_dict(d):
    if isinstance(d, dict):
        return {k: clean_dict(v) for k, v in d.items()}
    if isinstance(d, list):
        return [clean_dict(i) for i in d]
    return safe_val(d)


# ─── Static Frontend ─────────────────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(str(STATIC_DIR), "index.html")


# ─── API: Overview KPIs ──────────────────────────────────────────────────────

@app.route("/api/overview")
def api_overview():
    df = get_scores_df()
    total = len(df)
    avg_stress = df["stress_score"].mean()
    risk_dist = {
        "critical": int((df["stress_score"] >= 75).sum()),
        "high": int(((df["stress_score"] >= 50) & (df["stress_score"] < 75)).sum()),
        "moderate": int(((df["stress_score"] >= 25) & (df["stress_score"] < 50)).sum()),
        "low": int((df["stress_score"] < 25).sum()),
    }
    flagged = int((df["n_red_flags"] > 0).sum())
    sector_avg = df.groupby("sector")["stress_score"].mean().round(1).to_dict()
    top_stressed = (
        df.nlargest(10, "stress_score")[
            ["ticker", "sector", "stress_score", "verdict", "n_red_flags"]
        ].to_dict("records")
    )
    return jsonify(clean_dict({
        "total_companies": total,
        "avg_stress_score": round(float(avg_stress), 1) if not np.isnan(avg_stress) else 0,
        "risk_distribution": risk_dist,
        "flagged_companies": flagged,
        "sector_avg_stress": sector_avg,
        "top_stressed": top_stressed,
    }))


# ─── API: All Scores (filterable) ────────────────────────────────────────────

@app.route("/api/scores")
def api_scores():
    df = get_scores_df().copy()
    sector = request.args.get("sector")
    risk = request.args.get("risk")
    search = request.args.get("search", "").upper().strip()
    sort_by = request.args.get("sort", "stress_score")
    order = request.args.get("order", "desc")

    if sector and sector != "all":
        df = df[df["sector"] == sector]
    if risk and risk != "all":
        risk_map = {
            "critical": df["stress_score"] >= 75,
            "high": (df["stress_score"] >= 50) & (df["stress_score"] < 75),
            "moderate": (df["stress_score"] >= 25) & (df["stress_score"] < 50),
            "low": df["stress_score"] < 25,
        }
        if risk in risk_map:
            df = df[risk_map[risk]]
    if search:
        df = df[df["ticker"].str.contains(search, na=False)]
    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=(order != "desc"), na_position="last")

    return jsonify(clean_dict({"count": len(df), "companies": df.to_dict("records")}))


# ─── API: Single Company ─────────────────────────────────────────────────────

@app.route("/api/company/<ticker>")
def api_company(ticker):
    ticker = ticker.upper().strip()
    report = compute_stress_score(ticker, get_models())
    return jsonify(clean_dict(report))


# ─── API: Sector Aggregates ──────────────────────────────────────────────────

@app.route("/api/sectors")
def api_sectors():
    path = str(FEATURE_MATRIX_PATH)
    if not os.path.exists(path):
        return jsonify({"error": "Feature matrix not found"}), 404

    df = pd.read_csv(path)
    latest_year = df["year"].max()
    recent = df[df["year"] >= latest_year - 1]
    metrics = ["altman_z", "piotroski_f", "current_ratio", "net_margin",
               "interest_coverage", "debt_to_equity"]
    sectors = []
    for sector in sorted(recent["sector"].dropna().unique()):
        if sector == "Unknown":
            continue
        s_data = recent[recent["sector"] == sector]
        row = {"sector": sector, "count": int(s_data["ticker"].nunique())}
        for m in metrics:
            if m in s_data.columns:
                row[f"{m}_median"] = safe_val(s_data[m].median())
        sectors.append(row)

    scores_df = get_scores_df()
    for s in sectors:
        ss = scores_df[scores_df["sector"] == s["sector"]]
        s["avg_stress"] = safe_val(ss["stress_score"].mean()) if len(ss) > 0 else None
    return jsonify(clean_dict({"sectors": sectors}))


# ─── API: Ticker History ─────────────────────────────────────────────────────

@app.route("/api/history/<ticker>")
def api_history(ticker):
    ticker = ticker.upper().strip()
    hist = get_ticker_history(ticker)
    if hist.empty:
        return jsonify({"ticker": ticker, "history": []})
    cols = ["year", "altman_z", "piotroski_f", "current_ratio", "net_margin",
            "debt_to_equity", "interest_coverage", "roa", "roe", "cf_divergence"]
    available = [c for c in cols if c in hist.columns]
    return jsonify(clean_dict({"ticker": ticker, "history": hist[available].to_dict("records")}))


# ─── API: Live Scorer ────────────────────────────────────────────────────────

@app.route("/api/live/<ticker>")
def api_live(ticker):
    ticker = ticker.upper().strip()
    try:
        from src.models.live_scorer import score_live_ticker
        report = score_live_ticker(ticker, get_models())
        return jsonify(clean_dict(report))
    except Exception as e:
        logger.error(f"Live scoring failed for {ticker}: {e}")
        return jsonify({"ticker": ticker, "error": str(e), "score": None}), 500


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Financial Stress Dashboard on http://localhost:8000")
    get_models()
    get_scores_df()
    app.run(host="0.0.0.0", port=8000, debug=False)
