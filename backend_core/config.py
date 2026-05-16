"""
config.py — Central configuration for Fintellix Risk Suite
"""

# ── Company Universe ──────────────────────────────────────────────────────────
# ~500 US public companies across 5 sectors
# Includes healthy firms, stressed firms, and confirmed bankruptcies (ground truth)

COMPANY_UNIVERSE = {
    "Technology": [
        # Healthy / Large Cap
        "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC", "IBM", "ORCL", "CRM",
        "ADBE", "QCOM", "TXN", "AVGO", "MU", "AMAT", "KLAC", "LRCX", "SNPS", "CDNS",
        # Mid cap / growth
        "SNOW", "DDOG", "NET", "CRWD", "ZS", "OKTA", "MDB", "GTLB", "DOCN", "HUBS",
        "TWLO", "BILL", "SMAR", "BOX", "APPN", "ESTC", "SUMO", "NCNO", "ALRM", "CDAY",
        # Distressed / stressed
        "BBBY",   # Bed Bath Beyond — bankrupt 2023
        "RIDE",   # Lordstown Motors — bankrupt 2023
        "SPCE",   # Virgin Galactic — severe distress
        "NKLA",   # Nikola — severe distress
        "MVST",   # Microvast — distressed
    ],

    "Retail": [
        # Healthy
        "WMT", "COST", "TGT", "AMZN", "HD", "LOW", "MCD", "SBUX", "NKE", "TJX",
        "ROST", "BURL", "DG", "DLTR", "KR", "SFM", "CASY", "BJ", "FIVE", "OLLI",
        # Mid / specialty
        "GPS", "ANF", "AEO", "URBN", "PTON", "W", "RH", "BBWI", "VSCO", "DKS",
        "BOOT", "HIBB", "CATO", "EXPR", "CHS", "JOANN", "TLYS", "SCVL", "BNED", "GCO",
        # Bankrupt / distressed
        "SHLDQ",  # Sears — bankrupt 2018
        "JCP",    # JCPenney — bankrupt 2020
        "RTM",    # Rite Aid — bankrupt 2023
        "BBBY",   # Bed Bath Beyond — bankrupt 2023
        "TUES",   # Tuesday Morning — bankrupt 2023
        "BIGIQ",  # Big Lots — bankrupt 2024
        "GNC",    # GNC — bankrupt 2020
        "NCLHQ",  # Norwegian Cruise — severe distress (COVID)
        "CCL", "RCL",
    ],

    "Energy": [
        # Healthy / major
        "XOM", "CVX", "COP", "EOG", "PXD", "DVN", "MPC", "PSX", "VLO", "HES",
        "OXY", "APA", "FANG", "HAL", "SLB", "BKR", "NOV", "HP", "WHD", "WTTR",
        # Mid / independent
        "AR", "RRC", "EQT", "SWN", "CNX", "CTRA", "SM", "MTDR", "ESTE", "VTLE",
        # Distressed / bankrupt
        "CHESQ",  # Chesapeake Energy — bankrupt 2020, restructured as CHK
        "CHK",    # Chesapeake Energy post-restructure
        "WLL",    # Whiting Petroleum — bankrupt 2020
        "LGCYQ",  # Legacy Reserves — bankrupt 2019
        "CALPQ",  # Callon Petroleum — distressed
        "MGYOQ",  # Montage Resources — distressed
        "EXXI",   # Energy XXI — bankrupt 2016
        "SDRL",   # Seadrill — bankrupt 2017
        "NFGC",   # New Fortress Energy — distressed
        "TELL",   # Tellurian — severe distress
    ],

    "Financial_Services": [
        # Healthy / major banks
        "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "COF",
        "AXP", "BK", "STT", "NTRS", "FITB", "HBAN", "RF", "CFG", "ZION", "CMA",
        # Regional / specialty
        "WAL", "PACW", "SBNY", "SIVB", "FRC", "CUBI", "HWC", "IBOC", "FFIN", "BOKF",
        # Distressed / failed
        # SVB Financial — bankrupt 2023 (use SIVBQ or historical SIVB)
        "SIVB",   # Silicon Valley Bank — failed March 2023
        "SBNY",   # Signature Bank — failed March 2023
        "FRC",    # First Republic — failed May 2023
        "PACW",   # PacWest — severe distress 2023
        "WAL",    # Western Alliance — distress signals 2023
        "LEHMQ",  # Lehman Brothers — bankrupt 2008 (historical)
    ],

    "Healthcare": [
        # Healthy / large cap
        "JNJ", "UNH", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY", "AMGN",
        "GILD", "VRTX", "REGN", "ISRG", "SYK", "MDT", "BSX", "EW", "HOLX", "BDX",
        # Mid cap / biotech
        "MRNA", "BNTX", "NVAX", "SGEN", "ALNY", "BMRN", "EXEL", "INCY", "JAZZ", "IONS",
        # Distressed / stressed
        "ENDP",   # Endo International — bankrupt 2022
        "MLNDQ",  # Mallinckrodt — bankrupt 2020 + 2023
        "BHVN",   # Biohaven — distressed pre-acquisition
        "PRGO",   # Perrigo — distressed
        "EVHC",   # Envision Healthcare — bankrupt 2023
        "AMRX",   # Amneal Pharma — distressed
        "HZNP",   # Horizon Therapeutics — distressed pre-acquisition
        "AKRX",   # Akorn — bankrupt 2020
        "MGNX",   # MacroGenics — distressed
        "SNDX",   # Syndax Pharma — distressed
    ],
}

# Flatten to list of all tickers
ALL_TICKERS = [t for sector in COMPANY_UNIVERSE.values() for t in sector]

# ── Known Bankruptcy/Distress Events (Ground Truth Labels) ───────────────────
DISTRESS_EVENTS = {
    "LEHMQ": {"event": "bankruptcy", "date": "2008-09-15", "sector": "Financial_Services"},
    "CHESQ": {"event": "bankruptcy", "date": "2020-06-28", "sector": "Energy"},
    "CHK":   {"event": "restructured", "date": "2021-02-09", "sector": "Energy"},
    "WLL":   {"event": "bankruptcy", "date": "2020-04-01", "sector": "Energy"},
    "ENDP":  {"event": "bankruptcy", "date": "2022-08-16", "sector": "Healthcare"},
    "MLNDQ": {"event": "bankruptcy", "date": "2020-10-12", "sector": "Healthcare"},
    "JCP":   {"event": "bankruptcy", "date": "2020-05-15", "sector": "Retail"},
    "SHLDQ": {"event": "bankruptcy", "date": "2018-10-15", "sector": "Retail"},
    "BBBY":  {"event": "bankruptcy", "date": "2023-04-23", "sector": "Retail"},
    "TUES":  {"event": "bankruptcy", "date": "2023-05-24", "sector": "Retail"},
    "BIGIQ": {"event": "bankruptcy", "date": "2024-01-23", "sector": "Retail"},
    "GNC":   {"event": "bankruptcy", "date": "2020-06-23", "sector": "Retail"},
    "RTM":   {"event": "bankruptcy", "date": "2023-10-15", "sector": "Retail"},
    "SIVB":  {"event": "bank_failure", "date": "2023-03-10", "sector": "Financial_Services"},
    "SBNY":  {"event": "bank_failure", "date": "2023-03-12", "sector": "Financial_Services"},
    "FRC":   {"event": "bank_failure", "date": "2023-05-01", "sector": "Financial_Services"},
    "AKRX":  {"event": "bankruptcy", "date": "2020-05-20", "sector": "Healthcare"},
    "EVHC":  {"event": "bankruptcy", "date": "2023-05-15", "sector": "Healthcare"},
    "LGCYQ": {"event": "bankruptcy", "date": "2019-06-18", "sector": "Energy"},
    "EXXI":  {"event": "bankruptcy", "date": "2016-04-29", "sector": "Energy"},
    "SDRL":  {"event": "bankruptcy", "date": "2017-09-12", "sector": "Energy"},
    "RIDE":  {"event": "bankruptcy", "date": "2023-06-27", "sector": "Technology"},
}

# ── Time Range ────────────────────────────────────────────────────────────────
START_YEAR = 2014
END_YEAR   = 2024
START_DATE = "2014-01-01"
END_DATE   = "2024-12-31"

# ── Distress Thresholds (for rule-based flagging) ─────────────────────────────
THRESHOLDS = {
    "altman_z_safe":        3.0,   # Above = safe
    "altman_z_grey":        1.81,  # Below = distress zone
    "piotroski_strong":     7,     # 7-9 = strong
    "piotroski_weak":       3,     # 0-2 = weak
    "current_ratio_min":    1.0,   # Below = liquidity risk
    "quick_ratio_min":      0.7,
    "interest_coverage_min":1.5,   # Below = danger
    "debt_equity_max":      3.0,   # Above = over-leveraged
    "gross_margin_min":     0.10,  # Below = structural weakness
    "cash_burn_months_min": 6,     # Days cash on hand < 6 months = critical
}

# ── FRED Series IDs ───────────────────────────────────────────────────────────
FRED_SERIES = {
    "fed_funds_rate":    "FEDFUNDS",
    "recession_flag":    "USREC",       # 1 = recession
    "credit_spread":     "BAA10Y",      # Moody's BAA corporate spread
    "vix":               "VIXCLS",
    "gdp_growth":        "A191RL1Q225SBEA",
    "unemployment":      "UNRATE",
    "cpi":               "CPIAUCSL",
    "10yr_treasury":     "DGS10",
}

# ── File Paths ────────────────────────────────────────────────────────────────
import os
from pathlib import Path

# Base project directory (one level up from backend_core/)
BASE_DIR = Path(__file__).resolve().parents[1]

# Data directories
DATA_DIR        = BASE_DIR / "data"
RAW_DIR         = DATA_DIR / "raw"
PROCESSED_DIR   = DATA_DIR / "processed"
MACRO_DIR       = DATA_DIR / "macro"

# Feature matrices
FEATURE_MATRIX_PATH          = PROCESSED_DIR / "feature_matrix.csv"
FEATURE_MATRIX_EXPANDED_PATH = PROCESSED_DIR / "feature_matrix_expanded.csv"

# Model artifacts (PKL, JSON meta)
MODELS_DIR           = BASE_DIR / "models"
CLASSIFIER_PATH      = MODELS_DIR / "classifier.pkl"
CLASSIFIER_META_PATH = MODELS_DIR / "classifier_meta.json"
CLUSTERING_PATH      = MODELS_DIR / "clustering.pkl"
CLUSTERING_META_PATH = MODELS_DIR / "clustering_meta.json"
TREND_PATH           = MODELS_DIR / "trend.pkl"
TREND_META_PATH      = MODELS_DIR / "trend_meta.json"
SCORES_CSV_PATH      = MODELS_DIR / "all_scores.csv"

# Other directories
LOGS_DIR        = BASE_DIR / "logs"
REPORTS_DIR     = BASE_DIR / "reports"
PLOTS_DIR       = REPORTS_DIR / "plots"

# Ensure directories exist
for d in [RAW_DIR, PROCESSED_DIR, MACRO_DIR, MODELS_DIR, LOGS_DIR, REPORTS_DIR, PLOTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
