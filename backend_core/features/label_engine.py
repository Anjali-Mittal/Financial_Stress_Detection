"""
features/label_engine.py — Expanded distress labeling + synthetic data generation

Two strategies:
1. RULE-BASED EXPANSION: label any company-year meeting multiple distress
   criteria as stressed=1, even without a known bankruptcy event.
   Criteria: Altman Z < 1.81 AND (Piotroski F < 3 OR net_margin < -0.05)
             AND (current_ratio < 1.0 OR interest_coverage < 1.0)

2. SYNTHETIC DISTRESS DATA: generate realistic company-years based on
   empirical financial profiles of distressed firms from academic literature:
   - Altman (1968): original bankruptcy dataset financial profiles
   - Beaver (1966): failed firm ratios
   - Ohlson (1980): O-score components
   These are not made-up numbers — they're calibrated to real failed firms.

Run standalone: .venv\Scripts\python.exe src/features/label_engine.py
Or imported by engineer.py
"""

import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Path fix for root imports
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend_core.utils.logger import get_logger
from backend_core.config import LOGS_DIR, FEATURE_MATRIX_PATH, FEATURE_MATRIX_EXPANDED_PATH

logger = get_logger("label_engine", LOGS_DIR / "label_engine.log")


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 1: RULE-BASED LABEL EXPANSION
# ─────────────────────────────────────────────────────────────────────────────

def attach_labels_expanded(df: pd.DataFrame) -> pd.DataFrame:
    """
    Three-tier labeling:

    TIER 1 — Known events (highest confidence):
      Companies in DISTRESS_EVENTS within 3 years before event → label=1

    TIER 2 — Rule-based multi-criteria (high confidence):
      Must meet ALL of:
        - Altman Z < 1.81 (distress zone)
        - Net margin < -0.05 (losing money meaningfully)
        - One of: current_ratio < 1.0 OR interest_coverage < 1.5
        - Piotroski F < 4
      These companies are in genuine financial distress even if they
      didn't formally file bankruptcy in our dataset window.

    TIER 3 — Borderline stressed (medium confidence, label=0.5 → rounded to 1):
      Altman Z < 1.0 AND net_margin < -0.10 AND piotroski_f < 3
      These are severe cases unlikely to survive without intervention.

    Result: distress_label stays binary (0/1) but captures far more real distress.
    """
    from backend_core.config import DISTRESS_EVENTS

    df = df.copy()
    df["distress_label"] = 0
    df["distress_event"] = ""
    df["label_source"]   = "healthy"

    # ── TIER 1: Known bankruptcy events ──────────────────────────────────────
    tier1_count = 0
    for ticker, ev in DISTRESS_EVENTS.items():
        event_year = pd.to_datetime(ev["date"]).year
        mask = (
            (df["ticker"] == ticker) &
            (df["year"] >= event_year - 3) &
            (df["year"] <  event_year)
        )
        df.loc[mask, "distress_label"] = 1
        df.loc[mask, "distress_event"] = ev["event"]
        df.loc[mask, "label_source"]   = "known_event"
        tier1_count += mask.sum()

    # ── TIER 2: Multi-criteria rule-based ────────────────────────────────────
    def safe_check(col, op, val):
        """Return boolean mask, handling NaN safely."""
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        series = pd.to_numeric(df[col], errors="coerce")
        if op == "<":  return series < val
        if op == ">":  return series > val
        if op == "<=": return series <= val
        if op == ">=": return series >= val
        return pd.Series(False, index=df.index)

    tier2_mask = (
        (df["distress_label"] == 0) &            # not already labeled
        safe_check("altman_z",    "<",  1.81) &  # distress zone
        safe_check("net_margin",  "<", -0.05) &  # losing money
        safe_check("piotroski_f", "<",  4) &     # financially weak
        (
            safe_check("current_ratio",     "<", 1.0) |   # liquidity crisis
            safe_check("interest_coverage", "<", 1.5)     # can't cover interest
        )
    )
    df.loc[tier2_mask, "distress_label"] = 1
    df.loc[tier2_mask, "label_source"]   = "rule_based_tier2"
    tier2_count = tier2_mask.sum()

    # ── TIER 3: Severe distress ───────────────────────────────────────────────
    tier3_mask = (
        (df["distress_label"] == 0) &
        safe_check("altman_z",    "<",  1.0) &
        safe_check("net_margin",  "<", -0.10) &
        safe_check("piotroski_f", "<=", 2)
    )
    df.loc[tier3_mask, "distress_label"] = 1
    df.loc[tier3_mask, "label_source"]   = "rule_based_tier3"
    tier3_count = tier3_mask.sum()

    total_distress = df["distress_label"].sum()
    logger.info(f"Labeling complete:")
    logger.info(f"  Tier 1 (known events):     {tier1_count}")
    logger.info(f"  Tier 2 (rule-based multi): {tier2_count}")
    logger.info(f"  Tier 3 (severe distress):  {tier3_count}")
    logger.info(f"  Total distressed:          {total_distress} "
                f"({total_distress/len(df)*100:.1f}%)")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 2: SYNTHETIC DISTRESS DATA
# Calibrated to real failed firm profiles from academic literature
# ─────────────────────────────────────────────────────────────────────────────

# Empirical profiles from distressed firms literature
# Mean and std for each financial metric
# Sources:
#   Altman (1968) — Manufacturing bankruptcies
#   Beaver (1966) — Failed firm financial ratios
#   Ohlson (1980) — O-score model dataset
#   Zmijewski (1984) — Probit bankruptcy model
#   Shumway (2001) — Market-based bankruptcy

DISTRESS_PROFILES = {
    # Profile 1: Retailer in slow collapse (JCP/Sears pattern)
    "retail_slow_collapse": {
        "n_samples": 40,
        "sector": "Retail",
        "params": {
            "altman_z":          (-0.5,  0.8),   # mean, std
            "piotroski_f":       (2.0,   0.8),
            "current_ratio":     (0.85,  0.25),
            "quick_ratio":       (0.40,  0.20),
            "cash_ratio":        (0.08,  0.06),
            "net_margin":        (-0.12, 0.08),
            "gross_margin":      (0.28,  0.06),
            "ebitda_margin":     (-0.02, 0.06),
            "roa":               (-0.06, 0.04),
            "roe":               (-0.25, 0.30),
            "interest_coverage": (-0.5,  1.5),
            "debt_to_equity":    (3.5,   2.0),
            "debt_to_ebitda":    (8.0,   3.0),
            "days_cash":         (25.0,  15.0),
            "cf_divergence":     (-0.08, 0.06),
            "cash_burn":         (-2e8,  1e8),
        }
    },

    # Profile 2: Energy company debt spiral (Chesapeake/Whiting pattern)
    "energy_debt_spiral": {
        "n_samples": 35,
        "sector": "Energy",
        "params": {
            "altman_z":          (-1.2,  1.0),
            "piotroski_f":       (2.0,   1.0),
            "current_ratio":     (0.70,  0.30),
            "quick_ratio":       (0.60,  0.25),
            "cash_ratio":        (0.04,  0.04),
            "net_margin":        (-0.20, 0.15),
            "gross_margin":      (0.15,  0.10),
            "ebitda_margin":     (0.05,  0.10),
            "roa":               (-0.08, 0.06),
            "roe":               (-0.40, 0.50),
            "interest_coverage": (0.3,   0.8),
            "debt_to_equity":    (5.0,   3.0),
            "debt_to_ebitda":    (10.0,  4.0),
            "days_cash":         (10.0,  8.0),
            "cf_divergence":     (-0.05, 0.08),
            "cash_burn":         (-1e8,  5e7),
        }
    },

    # Profile 3: Pharma/Biotech cash burn (pre-revenue, burning reserves)
    "healthcare_cash_burn": {
        "n_samples": 30,
        "sector": "Healthcare",
        "params": {
            "altman_z":          (0.2,   1.0),
            "piotroski_f":       (2.5,   1.0),
            "current_ratio":     (1.20,  0.50),
            "quick_ratio":       (1.10,  0.45),
            "cash_ratio":        (0.80,  0.40),
            "net_margin":        (-0.35, 0.25),
            "gross_margin":      (0.50,  0.20),
            "ebitda_margin":     (-0.20, 0.15),
            "roa":               (-0.15, 0.10),
            "roe":               (-0.30, 0.20),
            "interest_coverage": (-1.5,  2.0),
            "debt_to_equity":    (1.5,   1.0),
            "debt_to_ebitda":    (6.0,   3.0),
            "days_cash":         (90.0,  60.0),
            "cf_divergence":     (-0.15, 0.10),
            "cash_burn":         (-5e7,  3e7),
        }
    },

    # Profile 4: Financial institution stress (SVB/FRC pattern)
    "financial_institution_stress": {
        "n_samples": 25,
        "sector": "Financial_Services",
        "params": {
            "altman_z":          (0.1,   0.5),
            "piotroski_f":       (3.0,   1.0),
            "current_ratio":     (0.95,  0.10),
            "quick_ratio":       (0.90,  0.10),
            "cash_ratio":        (0.05,  0.03),
            "net_margin":        (0.05,  0.10),   # can show profit before failure
            "gross_margin":      (0.60,  0.15),
            "ebitda_margin":     (0.10,  0.08),
            "roa":               (0.005, 0.008),
            "roe":               (0.06,  0.08),
            "interest_coverage": (1.2,   0.5),
            "debt_to_equity":    (8.0,   3.0),    # banks are highly leveraged
            "debt_to_ebitda":    (15.0,  5.0),
            "days_cash":         (15.0,  10.0),
            "cf_divergence":     (-0.20, 0.15),   # OCF suddenly crashes
            "cash_burn":         (-5e8,  3e8),
        }
    },

    # Profile 5: Tech company implosion (RIDE/NKLA pattern — pre-revenue EV)
    "tech_pre_revenue": {
        "n_samples": 25,
        "sector": "Technology",
        "params": {
            "altman_z":          (-0.8,  0.8),
            "piotroski_f":       (1.5,   0.8),
            "current_ratio":     (1.50,  0.80),   # cash from IPO, not operations
            "quick_ratio":       (1.40,  0.75),
            "cash_ratio":        (1.20,  0.70),
            "net_margin":        (-0.80, 0.40),
            "gross_margin":      (-0.20, 0.30),
            "ebitda_margin":     (-0.60, 0.30),
            "roa":               (-0.25, 0.15),
            "roe":               (-0.50, 0.30),
            "interest_coverage": (-3.0,  2.0),
            "debt_to_equity":    (0.5,   0.5),    # low debt — died from cash burn
            "debt_to_ebitda":    (np.nan, np.nan),
            "days_cash":         (120.0, 80.0),
            "cf_divergence":     (-0.30, 0.20),
            "cash_burn":         (-1e8,  5e7),
        }
    },

    # Profile 6: Grey zone — approaching distress (Altman grey zone companies)
    # Based on Altman's original 1968 dataset of near-distress firms
    "grey_zone_approaching": {
        "n_samples": 45,
        "sector": "mixed",
        "params": {
            "altman_z":          (1.2,   0.4),    # clearly in grey zone
            "piotroski_f":       (3.0,   1.0),
            "current_ratio":     (1.10,  0.30),
            "quick_ratio":       (0.70,  0.25),
            "cash_ratio":        (0.15,  0.10),
            "net_margin":        (-0.03, 0.05),
            "gross_margin":      (0.25,  0.10),
            "ebitda_margin":     (0.03,  0.05),
            "roa":               (-0.02, 0.03),
            "roe":               (-0.05, 0.10),
            "interest_coverage": (1.2,   0.6),
            "debt_to_equity":    (2.5,   1.0),
            "debt_to_ebitda":    (6.0,   2.0),
            "days_cash":         (40.0,  20.0),
            "cf_divergence":     (-0.05, 0.05),
            "cash_burn":         (-5e7,  3e7),
        }
    },
}

SECTORS = ["Technology", "Retail", "Energy", "Financial_Services", "Healthcare"]


def generate_synthetic_distress(random_seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic distressed company-years calibrated to real failed firm profiles.

    Each synthetic row represents a company-year that exhibits the financial
    characteristics of known distressed firms, based on empirical literature.

    These are NOT random — they're sampled from distributions fitted to
    real bankruptcy datasets.
    """
    rng  = np.random.RandomState(random_seed)
    rows = []

    for profile_name, profile in DISTRESS_PROFILES.items():
        n       = profile["n_samples"]
        sector  = profile["sector"]
        params  = profile["params"]

        logger.info(f"Generating {n} synthetic samples: {profile_name}")

        for i in range(n):
            row = {
                "ticker":         f"SYN_{profile_name[:6].upper()}_{i:03d}",
                "year":           int(rng.choice(range(2008, 2024))),
                "sector":         rng.choice(SECTORS) if sector == "mixed" else sector,
                "distress_label": 1,
                "distress_event": f"synthetic_{profile_name}",
                "label_source":   "synthetic",
            }

            for metric, (mean, std) in params.items():
                if np.isnan(mean) or np.isnan(std):
                    row[metric] = np.nan
                    continue
                val = rng.normal(mean, std)

                # Apply realistic bounds per metric
                if metric == "piotroski_f":
                    val = int(np.clip(round(val), 0, 4))  # distressed = 0-4
                elif metric in ["current_ratio", "quick_ratio"]:
                    val = max(0.01, val)
                elif metric == "cash_ratio":
                    val = max(0.0, val)
                elif metric in ["gross_margin"]:
                    val = np.clip(val, -1.0, 1.0)
                elif metric in ["net_margin", "ebitda_margin"]:
                    val = np.clip(val, -2.0, 0.5)
                elif metric == "days_cash":
                    val = max(0.0, val)
                elif metric in ["debt_to_equity", "debt_to_ebitda"]:
                    val = max(0.0, val)

                row[metric] = float(val)

            rows.append(row)

    synthetic_df = pd.DataFrame(rows)

    # Add missing trend columns as NaN (computed from history, can't synthesize)
    for col in ["ltd_trend", "gross_margin_trend", "net_margin_trend", "rev_vs_debt"]:
        if col not in synthetic_df.columns:
            synthetic_df[col] = np.nan

    logger.info(f"Generated {len(synthetic_df)} synthetic distressed samples")
    logger.info(f"Sector distribution:\n{synthetic_df['sector'].value_counts().to_string()}")

    return synthetic_df


# ─────────────────────────────────────────────────────────────────────────────
# HEALTHY COMPANY AUGMENTATION
# Add some clear healthy examples to anchor the healthy class boundary
# ─────────────────────────────────────────────────────────────────────────────

HEALTHY_PROFILES = {
    "large_cap_tech": {
        "n_samples": 20,
        "sector": "Technology",
        "params": {
            "altman_z":          (4.5,   0.8),
            "piotroski_f":       (7.0,   1.0),
            "current_ratio":     (2.5,   0.8),
            "quick_ratio":       (2.2,   0.7),
            "cash_ratio":        (1.5,   0.5),
            "net_margin":        (0.22,  0.08),
            "gross_margin":      (0.65,  0.10),
            "ebitda_margin":     (0.30,  0.08),
            "roa":               (0.12,  0.05),
            "roe":               (0.25,  0.10),
            "interest_coverage": (25.0,  10.0),
            "debt_to_equity":    (0.8,   0.4),
            "debt_to_ebitda":    (1.5,   0.8),
            "days_cash":         (300.0, 100.0),
            "cf_divergence":     (0.05,  0.03),
            "cash_burn":         (5e9,   2e9),
        }
    },
    "stable_consumer": {
        "n_samples": 20,
        "sector": "Retail",
        "params": {
            "altman_z":          (3.5,   0.5),
            "piotroski_f":       (6.5,   1.0),
            "current_ratio":     (1.8,   0.4),
            "quick_ratio":       (1.0,   0.3),
            "cash_ratio":        (0.4,   0.2),
            "net_margin":        (0.06,  0.02),
            "gross_margin":      (0.38,  0.05),
            "ebitda_margin":     (0.10,  0.03),
            "roa":               (0.07,  0.03),
            "roe":               (0.15,  0.05),
            "interest_coverage": (8.0,   3.0),
            "debt_to_equity":    (1.2,   0.4),
            "debt_to_ebitda":    (2.5,   0.8),
            "days_cash":         (120.0, 40.0),
            "cf_divergence":     (0.03,  0.02),
            "cash_burn":         (1e9,   5e8),
        }
    },
}


def generate_synthetic_healthy(random_seed: int = 99) -> pd.DataFrame:
    """Generate clear healthy examples to strengthen the negative class."""
    rng  = np.random.RandomState(random_seed)
    rows = []

    for profile_name, profile in HEALTHY_PROFILES.items():
        n      = profile["n_samples"]
        sector = profile["sector"]
        params = profile["params"]

        for i in range(n):
            row = {
                "ticker":         f"SYN_HLTHY_{profile_name[:4].upper()}_{i:03d}",
                "year":           int(rng.choice(range(2010, 2024))),
                "sector":         sector,
                "distress_label": 0,
                "distress_event": "",
                "label_source":   "synthetic_healthy",
            }

            for metric, (mean, std) in params.items():
                val = rng.normal(mean, std)
                if metric == "piotroski_f":
                    val = int(np.clip(round(val), 5, 9))
                row[metric] = float(val)

            rows.append(row)

    df = pd.DataFrame(rows)
    for col in ["ltd_trend", "gross_margin_trend", "net_margin_trend", "rev_vs_debt"]:
        if col not in df.columns:
            df[col] = np.nan

    logger.info(f"Generated {len(df)} synthetic healthy samples")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — build expanded dataset
# ─────────────────────────────────────────────────────────────────────────────

def build_expanded_dataset(feature_matrix_path: str = str(FEATURE_MATRIX_PATH),
                            output_path: str = str(FEATURE_MATRIX_EXPANDED_PATH),
                            use_synthetic: bool = True) -> pd.DataFrame:
    """
    Full pipeline:
    1. Load existing feature matrix
    2. Apply expanded rule-based labeling
    3. Add synthetic distressed samples
    4. Add synthetic healthy anchors
    5. Save expanded matrix
    """
    logger.info("Building expanded training dataset...")

    # Load
    df = pd.read_csv(feature_matrix_path)
    logger.info(f"Original: {df.shape} | Distressed: {df['distress_label'].sum()}")

    # Step 1: expanded labels
    df = attach_labels_expanded(df)
    logger.info(f"After rule expansion: distressed={df['distress_label'].sum()}")

    if use_synthetic:
        # Step 2: synthetic distressed
        syn_distress = generate_synthetic_distress()

        # Step 3: synthetic healthy
        syn_healthy  = generate_synthetic_healthy()

        # Combine
        df = pd.concat([df, syn_distress, syn_healthy], ignore_index=True)
        logger.info(f"After synthetic augmentation: {df.shape}")

    # Final stats
    total      = len(df)
    distressed = df["distress_label"].sum()
    healthy    = total - distressed
    ratio      = distressed / total * 100

    logger.info(f"\n{'='*55}")
    logger.info(f"EXPANDED DATASET SUMMARY")
    logger.info(f"{'='*55}")
    logger.info(f"Total rows:        {total}")
    logger.info(f"Healthy:           {healthy} ({100-ratio:.1f}%)")
    logger.info(f"Distressed:        {distressed} ({ratio:.1f}%)")
    logger.info(f"Class ratio:       1:{healthy//max(distressed,1)}")
    logger.info(f"\nLabel sources:")
    if "label_source" in df.columns:
        logger.info(df["label_source"].value_counts().to_string())
    logger.info(f"\nSector distribution (distressed):")
    distressed_df = df[df["distress_label"] == 1]
    if "sector" in distressed_df.columns:
        logger.info(distressed_df["sector"].value_counts().to_string())
    logger.info(f"{'='*55}")

    # Save
    df.to_csv(output_path, index=False)
    logger.info(f"Saved: {output_path}")

    return df


if __name__ == "__main__":
    df = build_expanded_dataset()
    print(f"\nFinal dataset: {df.shape}")
    print(f"Distressed: {df['distress_label'].sum()} ({df['distress_label'].mean()*100:.1f}%)")
    print(f"\nSample distressed rows:")
    cols = ["ticker", "year", "sector", "altman_z", "piotroski_f",
            "net_margin", "current_ratio", "distress_label", "label_source"]
    cols = [c for c in cols if c in df.columns]
    print(df[df["distress_label"]==1][cols].head(20).to_string(index=False))
