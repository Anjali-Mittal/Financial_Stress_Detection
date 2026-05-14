"""
eda/analysis.py — Exploratory Data Analysis for Financial Stress Early Warning System

Answers:
1. Which ratios deteriorated fastest before bankruptcy?
2. Which sectors are most stressed right now?
3. Feature correlation heatmap
4. Altman Z distribution: healthy vs distressed
5. Distress signal timeline — how early do signals appear?

Run: .venv\Scripts\python.exe src/visualization/analysis.py
Outputs: reports/plots/ — all charts as PNG
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")
# Path fix for root imports
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend_core.utils.logger import get_logger
from backend_core.config import LOGS_DIR, REPORTS_DIR, FEATURE_MATRIX_PATH, PLOTS_DIR

logger = get_logger("eda", LOGS_DIR / "eda.log")

# ── Style ─────────────────────────────────────────────────────────────────────
DARK_BG    = "#0d1117"
CARD_BG    = "#161b22"
ACCENT     = "#f78166"
ACCENT2    = "#79c0ff"
ACCENT3    = "#56d364"
TEXT       = "#e6edf3"
MUTED      = "#8b949e"
GRID       = "#21262d"

plt.rcParams.update({
    "figure.facecolor":  DARK_BG,
    "axes.facecolor":    CARD_BG,
    "axes.edgecolor":    GRID,
    "axes.labelcolor":   TEXT,
    "axes.titlecolor":   TEXT,
    "text.color":        TEXT,
    "xtick.color":       MUTED,
    "ytick.color":       MUTED,
    "grid.color":        GRID,
    "grid.linestyle":    "--",
    "grid.alpha":        0.5,
    "font.family":       "monospace",
    "figure.dpi":        150,
})

FEATURE_COLS = [
    "debt_to_equity", "interest_coverage", "debt_to_ebitda",
    "current_ratio", "quick_ratio", "cash_ratio", "days_cash",
    "gross_margin", "net_margin", "ebitda_margin", "roe", "roa",
    "altman_z", "piotroski_f", "cf_divergence",
]

FEATURE_LABELS = {
    "debt_to_equity":    "Debt/Equity",
    "interest_coverage": "Interest Coverage",
    "debt_to_ebitda":    "Debt/EBITDA",
    "current_ratio":     "Current Ratio",
    "quick_ratio":       "Quick Ratio",
    "cash_ratio":        "Cash Ratio",
    "days_cash":         "Days Cash on Hand",
    "gross_margin":      "Gross Margin",
    "net_margin":        "Net Margin",
    "ebitda_margin":     "EBITDA Margin",
    "roe":               "Return on Equity",
    "roa":               "Return on Assets",
    "altman_z":          "Altman Z-Score",
    "piotroski_f":       "Piotroski F-Score",
    "cf_divergence":     "CF vs Profit Divergence",
}


def load_data() -> pd.DataFrame:
    path = FEATURE_MATRIX_PATH
    if not os.path.exists(path):
        logger.error(f"{path} not found. Run engineer.py first.")
        sys.exit(1)
    df = pd.read_csv(path)
    logger.info(f"Loaded: {df.shape} | Distressed: {df['distress_label'].sum()}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# PLOT 1: Altman Z-Score Distribution — Healthy vs Distressed
# ─────────────────────────────────────────────────────────────────────────────

def plot_altman_distribution(df: pd.DataFrame):
    """
    Shows the Z-score distributions for healthy vs distressed companies.
    Key insight: do distressed companies cluster below 1.81?
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor(DARK_BG)

    healthy    = df[df["distress_label"] == 0]["altman_z"].dropna()
    distressed = df[df["distress_label"] == 1]["altman_z"].dropna()

    # Clip extreme outliers for readability
    healthy    = healthy.clip(-5, 15)
    distressed = distressed.clip(-5, 15)

    ax.hist(healthy,    bins=60, alpha=0.6, color=ACCENT2,  label=f"Healthy (n={len(healthy)})",    density=True)
    ax.hist(distressed, bins=20, alpha=0.8, color=ACCENT,   label=f"Distressed (n={len(distressed)})", density=True)

    # Threshold lines
    ax.axvline(1.81, color="#ff6b6b", linewidth=2, linestyle="--", alpha=0.9)
    ax.axvline(3.0,  color="#ffd93d", linewidth=2, linestyle="--", alpha=0.9)

    ax.text(1.81, ax.get_ylim()[1]*0.95, " Distress\n Zone", color="#ff6b6b",
            fontsize=9, va="top")
    ax.text(3.0,  ax.get_ylim()[1]*0.95, " Safe\n Zone", color="#ffd93d",
            fontsize=9, va="top")

    ax.set_xlabel("Altman Z-Score", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title("Altman Z-Score Distribution: Healthy vs Distressed Companies",
                 fontsize=14, fontweight="bold", pad=15)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    # Stats annotation
    stats_text = (f"Healthy median: {healthy.median():.2f}\n"
                  f"Distressed median: {distressed.median():.2f}")
    ax.text(0.98, 0.97, stats_text, transform=ax.transAxes,
            fontsize=9, va="top", ha="right", color=MUTED,
            bbox=dict(boxstyle="round", facecolor=CARD_BG, alpha=0.8))

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "01_altman_distribution.png", bbox_inches="tight",
                facecolor=DARK_BG)
    plt.close()
    logger.info("Saved: 01_altman_distribution.png")


# ─────────────────────────────────────────────────────────────────────────────
# PLOT 2: Feature Comparison — Healthy vs Distressed (Box plots)
# ─────────────────────────────────────────────────────────────────────────────

def plot_feature_comparison(df: pd.DataFrame):
    """
    Side-by-side box plots for each ratio.
    Shows WHERE the separation between healthy and distressed lies for each metric.
    """
    cols = [c for c in FEATURE_COLS if c in df.columns]
    n    = len(cols)
    ncols = 3
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(18, nrows * 4))
    fig.patch.set_facecolor(DARK_BG)
    fig.suptitle("Financial Ratios: Healthy vs Distressed Companies",
                 fontsize=16, fontweight="bold", color=TEXT, y=1.01)

    axes_flat = axes.flatten()

    for i, col in enumerate(cols):
        ax = axes_flat[i]
        ax.set_facecolor(CARD_BG)

        h = df[df["distress_label"] == 0][col].dropna()
        d = df[df["distress_label"] == 1][col].dropna()

        # Clip outliers per feature
        p1, p99 = df[col].quantile([0.01, 0.99])
        h = h.clip(p1, p99)
        d = d.clip(p1, p99)

        bp = ax.boxplot([h, d],
                        patch_artist=True,
                        widths=0.5,
                        medianprops=dict(color="white", linewidth=2),
                        whiskerprops=dict(color=MUTED),
                        capprops=dict(color=MUTED),
                        flierprops=dict(marker=".", color=MUTED, alpha=0.3, markersize=3))

        bp["boxes"][0].set_facecolor(ACCENT2 + "80")
        bp["boxes"][0].set_edgecolor(ACCENT2)
        if len(bp["boxes"]) > 1:
            bp["boxes"][1].set_facecolor(ACCENT + "80")
            bp["boxes"][1].set_edgecolor(ACCENT)

        ax.set_xticks([1, 2])
        ax.set_xticklabels(["Healthy", "Distressed"], fontsize=9)
        ax.set_title(FEATURE_LABELS.get(col, col), fontsize=10, fontweight="bold")
        ax.grid(True, alpha=0.3, axis="y")

        # T-test p-value
        if len(h) > 5 and len(d) > 5:
            _, pval = stats.ttest_ind(h, d, equal_var=False)
            sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else "ns"
            ax.text(0.98, 0.98, sig, transform=ax.transAxes,
                    fontsize=11, va="top", ha="right",
                    color=ACCENT3 if sig != "ns" else MUTED)

    # Hide unused subplots
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "02_feature_comparison.png", bbox_inches="tight",
                facecolor=DARK_BG)
    plt.close()
    logger.info("Saved: 02_feature_comparison.png")


# ─────────────────────────────────────────────────────────────────────────────
# PLOT 3: Correlation Heatmap
# ─────────────────────────────────────────────────────────────────────────────

def plot_correlation_heatmap(df: pd.DataFrame):
    """
    Pearson correlation between all features + distress label.
    Shows which features are most correlated with distress.
    """
    cols = [c for c in FEATURE_COLS + ["distress_label"] if c in df.columns]
    corr = df[cols].corr()

    labels = [FEATURE_LABELS.get(c, c) for c in cols[:-1]] + ["DISTRESS"]

    fig, ax = plt.subplots(figsize=(14, 12))
    fig.patch.set_facecolor(DARK_BG)

    mask = np.zeros_like(corr, dtype=bool)
    mask[np.triu_indices_from(mask, k=1)] = True

    cmap = sns.diverging_palette(220, 10, as_cmap=True)
    sns.heatmap(corr,
                mask=mask,
                cmap=cmap,
                center=0,
                vmin=-1, vmax=1,
                square=True,
                linewidths=0.5,
                linecolor=DARK_BG,
                annot=True,
                fmt=".2f",
                annot_kws={"size": 7},
                xticklabels=labels,
                yticklabels=labels,
                ax=ax,
                cbar_kws={"shrink": 0.8})

    ax.set_title("Feature Correlation Matrix (with Distress Label)",
                 fontsize=14, fontweight="bold", pad=20, color=TEXT)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.tick_params(axis="y", rotation=0,  labelsize=8)

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "03_correlation_heatmap.png", bbox_inches="tight",
                facecolor=DARK_BG)
    plt.close()
    logger.info("Saved: 03_correlation_heatmap.png")


# ─────────────────────────────────────────────────────────────────────────────
# PLOT 4: Sector Stress Heatmap — current stress levels
# ─────────────────────────────────────────────────────────────────────────────

def plot_sector_stress(df: pd.DataFrame):
    """
    Shows average stress indicators by sector for the most recent year.
    Darker = more stressed.
    """
    recent = df[df["year"] >= df["year"].max() - 1].copy()

    metrics = {
        "altman_z":          ("Altman Z", True),   # True = higher is better
        "piotroski_f":       ("Piotroski F", True),
        "current_ratio":     ("Current Ratio", True),
        "net_margin":        ("Net Margin", True),
        "interest_coverage": ("Interest Coverage", True),
        "debt_to_equity":    ("Debt/Equity", False),  # False = lower is better
        "debt_to_ebitda":    ("Debt/EBITDA", False),
    }

    sectors = [s for s in recent["sector"].unique() if s != "Unknown"]
    metric_names  = [v[0] for v in metrics.values()]
    metric_cols   = list(metrics.keys())
    higher_better = [v[1] for v in metrics.values()]

    matrix = []
    for sector in sectors:
        s_data = recent[recent["sector"] == sector]
        row = []
        for col, (_, hb) in zip(metric_cols, metrics.values()):
            val = s_data[col].median()
            row.append(val)
        matrix.append(row)

    matrix_df = pd.DataFrame(matrix, index=sectors, columns=metric_names)

    # Normalize 0-1 per column, flip if lower=better
    norm = matrix_df.copy()
    for j, (col, hb) in enumerate(zip(metric_names, higher_better)):
        col_data = norm[col]
        mn, mx = col_data.min(), col_data.max()
        if mx > mn:
            norm[col] = (col_data - mn) / (mx - mn)
        if not hb:
            norm[col] = 1 - norm[col]  # flip so 1=always good

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 6),
                                    gridspec_kw={"width_ratios": [2, 1]})
    fig.patch.set_facecolor(DARK_BG)

    # Heatmap
    ax1.set_facecolor(CARD_BG)
    cmap = sns.color_palette("RdYlGn", as_cmap=True)
    sns.heatmap(norm,
                cmap=cmap,
                vmin=0, vmax=1,
                annot=matrix_df.round(2),
                fmt="g",
                annot_kws={"size": 9},
                linewidths=1,
                linecolor=DARK_BG,
                ax=ax1,
                cbar_kws={"label": "Health Score (green=healthy, red=stressed)"})

    ax1.set_title("Sector Financial Health Heatmap (Most Recent Year)",
                  fontsize=13, fontweight="bold", pad=15, color=TEXT)
    ax1.tick_params(axis="x", rotation=30, labelsize=9)
    ax1.tick_params(axis="y", rotation=0,  labelsize=10)

    # Overall stress score bar chart
    overall = norm.mean(axis=1).sort_values()
    colors  = [ACCENT if v < 0.4 else ACCENT2 for v in overall]

    ax2.set_facecolor(CARD_BG)
    bars = ax2.barh(overall.index, overall.values, color=colors, edgecolor="none", height=0.6)
    ax2.axvline(0.5, color=MUTED, linewidth=1, linestyle="--", alpha=0.6)
    ax2.set_xlabel("Overall Health Score (0=stressed, 1=healthy)", fontsize=10)
    ax2.set_title("Sector Overall Health", fontsize=12, fontweight="bold", color=TEXT)
    ax2.set_xlim(0, 1)
    ax2.grid(True, alpha=0.3, axis="x")

    for bar, val in zip(bars, overall.values):
        ax2.text(val + 0.01, bar.get_y() + bar.get_height()/2,
                 f"{val:.2f}", va="center", fontsize=9, color=TEXT)

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "04_sector_stress.png", bbox_inches="tight",
                facecolor=DARK_BG)
    plt.close()
    logger.info("Saved: 04_sector_stress.png")


# ─────────────────────────────────────────────────────────────────────────────
# PLOT 5: Distress Signal Timeline — how early do signals appear?
# ─────────────────────────────────────────────────────────────────────────────

def plot_distress_timeline(df: pd.DataFrame):
    """
    For each bankrupt company: shows Altman Z trajectory leading up to bankruptcy.
    Key question: how many years before collapse does Z drop below 1.81?
    """
    from backend_core.config import DISTRESS_EVENTS

    distress_tickers = [t for t in DISTRESS_EVENTS
                        if t in df["ticker"].values]

    if not distress_tickers:
        logger.warning("No distress tickers in feature matrix for timeline plot")
        return

    fig, axes = plt.subplots(2, 4, figsize=(20, 10))
    fig.patch.set_facecolor(DARK_BG)
    fig.suptitle("Altman Z-Score Trajectory Before Bankruptcy\n(Dashed line = event date)",
                 fontsize=15, fontweight="bold", color=TEXT, y=1.02)

    axes_flat = axes.flatten()

    plotted = 0
    for ticker in distress_tickers:
        if plotted >= 8:
            break

        ticker_df = df[df["ticker"] == ticker].sort_values("year")
        z_data    = ticker_df[["year", "altman_z"]].dropna()

        if len(z_data) < 2:
            continue

        ax = axes_flat[plotted]
        ax.set_facecolor(CARD_BG)

        event_year = pd.to_datetime(
            DISTRESS_EVENTS[ticker]["date"]).year

        ax.plot(z_data["year"], z_data["altman_z"],
                color=ACCENT2, linewidth=2.5, marker="o",
                markersize=6, markerfacecolor=ACCENT2)

        # Threshold lines
        ax.axhline(1.81, color=ACCENT,  linewidth=1.5, linestyle="--", alpha=0.8,
                   label="Distress threshold (1.81)")
        ax.axhline(3.0,  color=ACCENT3, linewidth=1.5, linestyle="--", alpha=0.6,
                   label="Safe zone (3.0)")
        ax.axvline(event_year, color="#ff4444", linewidth=2,
                   linestyle="-", alpha=0.9, label=f"Event: {event_year}")

        ax.set_title(f"{ticker}\n{DISTRESS_EVENTS[ticker]['event'].upper()}",
                     fontsize=10, fontweight="bold", color=ACCENT)
        ax.set_xlabel("Year", fontsize=8)
        ax.set_ylabel("Altman Z", fontsize=8)
        ax.grid(True, alpha=0.3)

        if plotted == 0:
            ax.legend(fontsize=7, loc="upper right")

        plotted += 1

    # Hide unused
    for j in range(plotted, len(axes_flat)):
        axes_flat[j].set_visible(False)

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "05_distress_timeline.png", bbox_inches="tight",
                facecolor=DARK_BG)
    plt.close()
    logger.info("Saved: 05_distress_timeline.png")


# ─────────────────────────────────────────────────────────────────────────────
# PLOT 6: Feature Importance (correlation with distress label)
# ─────────────────────────────────────────────────────────────────────────────

def plot_feature_importance(df: pd.DataFrame):
    """
    Which features are most correlated with the distress label?
    Horizontal bar chart ranked by absolute correlation.
    """
    cols = [c for c in FEATURE_COLS if c in df.columns]
    corrs = {}
    for col in cols:
        sub = df[["distress_label", col]].dropna()
        if len(sub) > 10:
            r, p = stats.pointbiserialr(sub["distress_label"], sub[col])
            corrs[col] = (r, p)

    corr_df = pd.DataFrame(corrs, index=["r", "p"]).T
    corr_df["abs_r"] = corr_df["r"].abs()
    corr_df = corr_df.sort_values("abs_r", ascending=True)
    corr_df["label"] = [FEATURE_LABELS.get(c, c) for c in corr_df.index]

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(CARD_BG)

    colors = [ACCENT if r < 0 else ACCENT2 for r in corr_df["r"]]
    bars   = ax.barh(corr_df["label"], corr_df["r"],
                     color=colors, edgecolor="none", height=0.7)

    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_xlabel("Point-biserial Correlation with Distress Label", fontsize=11)
    ax.set_title("Feature Correlation with Financial Distress\n(red = negative correlation, blue = positive)",
                 fontsize=13, fontweight="bold", pad=15, color=TEXT)
    ax.grid(True, alpha=0.3, axis="x")

    # Significance markers
    for i, (_, row) in enumerate(corr_df.iterrows()):
        sig = "***" if row["p"] < 0.001 else "**" if row["p"] < 0.01 else "*" if row["p"] < 0.05 else ""
        if sig:
            x = row["r"] + (0.01 if row["r"] >= 0 else -0.01)
            ha = "left" if row["r"] >= 0 else "right"
            ax.text(x, i, sig, va="center", ha=ha, fontsize=9, color=ACCENT3)

    ax.text(0.98, 0.02,
            "* p<0.05  ** p<0.01  *** p<0.001",
            transform=ax.transAxes, fontsize=8,
            color=MUTED, ha="right", va="bottom")

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "06_feature_importance.png", bbox_inches="tight",
                facecolor=DARK_BG)
    plt.close()
    logger.info("Saved: 06_feature_importance.png")


# ─────────────────────────────────────────────────────────────────────────────
# PRINT: Statistical summary
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    print(f"\n{'='*60}")
    print("FINANCIAL STRESS EDA SUMMARY")
    print(f"{'='*60}")
    print(f"Total company-years:  {len(df)}")
    print(f"Unique tickers:       {df['ticker'].nunique()}")
    print(f"Year range:           {df['year'].min()} – {df['year'].max()}")
    print(f"Distressed rows:      {df['distress_label'].sum()} ({df['distress_label'].mean()*100:.1f}%)")
    print(f"Sectors:              {sorted(df['sector'].unique())}")

    print(f"\n── Median Ratios: Healthy vs Distressed ──")
    cols = [c for c in FEATURE_COLS if c in df.columns]
    h = df[df["distress_label"] == 0]
    d = df[df["distress_label"] == 1]
    print(f"{'Feature':<25} {'Healthy':>10} {'Distressed':>12}")
    print("-" * 50)
    for col in cols:
        hm = h[col].median()
        dm = d[col].median()
        label = FEATURE_LABELS.get(col, col)
        flag = " ◄" if abs(hm - dm) > 0.5 * abs(hm) else ""
        print(f"{label:<25} {hm:>10.3f} {dm:>12.3f}{flag}")

    print(f"\n── Most Stressed Companies Right Now ──")
    recent = df[df["year"] == df["year"].max()]
    if "altman_z" in recent.columns:
        stressed = recent[recent["altman_z"] < 1.81][
            ["ticker", "sector", "altman_z", "piotroski_f", "net_margin"]
        ].sort_values("altman_z").head(15)
        print(stressed.to_string(index=False))
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# RUN ALL
# ─────────────────────────────────────────────────────────────────────────────

def run():
    df = load_data()
    print_summary(df)

    logger.info("Generating plots...")
    plot_altman_distribution(df)
    plot_feature_comparison(df)
    plot_correlation_heatmap(df)
    plot_sector_stress(df)
    plot_distress_timeline(df)
    plot_feature_importance(df)

    logger.info("\nAll plots saved to eda/plots/")
    print("Plots saved to: eda/plots/")
    print("  01_altman_distribution.png  — Z-score: healthy vs distressed")
    print("  02_feature_comparison.png   — Box plots: all ratios")
    print("  03_correlation_heatmap.png  — Feature correlations")
    print("  04_sector_stress.png        — Sector health heatmap")
    print("  05_distress_timeline.png    — Z-score before bankruptcy")
    print("  06_feature_importance.png   — Which features predict distress")


if __name__ == "__main__":
    run()
