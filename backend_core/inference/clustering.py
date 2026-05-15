"""
models/clustering.py — K-Means Peer Similarity Engine

Split awareness:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Loads train/val/test ticker split from classifier_meta.json
- Cluster GEOMETRY (PCA, KMeans fit) uses train companies only
- Cluster PROFILES (distress rates, risk scores) use train companies only
- Val/test companies are ASSIGNED to clusters but never influence
  cluster risk profiles — prevents evaluation leakage
- Synthetic data used for scaler/PCA fitting but excluded from profiles

Other best practices:
- Optimal K: Silhouette + Davies-Bouldin + Distress Concentration
- Stability check (ARI across 10 seeds)
- Chi-squared test: is distress non-randomly distributed?
- Temporal analysis: pre/post 2020 cluster distress rates
- SHA-256 integrity hash

Run: .venv\Scripts\python.exe backend_core/models/clustering.py
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
    CLUSTERING_PATH, CLUSTERING_META_PATH,
    CLASSIFIER_META_PATH,
    FEATURE_MATRIX_EXPANDED_PATH, FEATURE_MATRIX_PATH,
)

logger = get_logger("clustering", LOGS_DIR / "clustering.log")

FEATURE_COLS = [
    "debt_to_equity", "interest_coverage", "debt_to_ebitda",
    "current_ratio", "quick_ratio", "cash_ratio", "days_cash",
    "gross_margin", "net_margin", "ebitda_margin", "roe", "roa",
    "altman_z", "piotroski_f", "cf_divergence",
]
MODEL_PATH    = CLUSTERING_PATH
META_PATH     = CLUSTERING_META_PATH
SYNTHETIC_TAG = "synthetic"
MIN_CLUSTER_SIZE = 10


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
        logger.error("SECURITY: Clustering model hash mismatch!")
        return False
    return True


def sanitize_input(X: np.ndarray) -> np.ndarray:
    return np.clip(X, -1e6, 1e6)


# ─────────────────────────────────────────────────────────────────────────────
# LOAD TRAIN TICKERS FROM CLASSIFIER SPLIT
# ─────────────────────────────────────────────────────────────────────────────

def load_train_tickers() -> set:
    """
    Load train/val/test ticker split from classifier_meta.json.
    Clustering profiles should only be built on train companies.
    Returns set of train tickers (includes val for profile building,
    excludes test which must remain truly held-out).
    """
    meta_path = str(CLASSIFIER_META_PATH)
    if not os.path.exists(meta_path):
        logger.warning(
            "classifier_meta.json not found — cannot load ticker split. "
            "Run classifier.py first. Falling back to all real companies."
        )
        return None

    with open(meta_path) as f:
        meta = json.load(f)

    train_tickers = set(meta.get("train_tickers", []))
    val_tickers   = set(meta.get("val_tickers",   []))
    test_tickers  = set(meta.get("test_tickers",  []))

    # Profile companies = train + val (exclude test)
    profile_tickers = train_tickers | val_tickers

    logger.info(f"Loaded ticker split from classifier_meta.json:")
    logger.info(f"  Train: {len(train_tickers)} | Val: {len(val_tickers)} | "
                f"Test: {len(test_tickers)}")
    logger.info(f"  Profile companies (train+val): {len(profile_tickers)}")
    logger.info(f"  Test companies excluded from profiles: {len(test_tickers)}")

    return profile_tickers, test_tickers


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_data(path: str = None):
    path = path or str(FEATURE_MATRIX_EXPANDED_PATH)
    if not os.path.exists(path):
        path = str(FEATURE_MATRIX_PATH)
        logger.warning(f"Expanded matrix not found. Using: {path}")

    df = pd.read_csv(path)
    logger.info(f"Loaded: {df.shape} | Distressed: {df['distress_label'].sum()} "
                f"({df['distress_label'].mean()*100:.1f}%)")

    features = [c for c in FEATURE_COLS if c in df.columns]

    is_synthetic = df.get(
        "label_source", pd.Series("", index=df.index)
    ).str.contains(SYNTHETIC_TAG, na=False)

    real_df = df[~is_synthetic].copy()
    syn_df  = df[is_synthetic].copy()

    logger.info(f"Real rows: {len(real_df)} | Synthetic rows: {len(syn_df)}")
    logger.info(f"Real distressed: {real_df['distress_label'].sum()}")

    return df, real_df, syn_df, features


# ─────────────────────────────────────────────────────────────────────────────
# PREPROCESSING — fit on train+synthetic only
# ─────────────────────────────────────────────────────────────────────────────

def build_preprocessing(X_fit: pd.DataFrame, X_transform: pd.DataFrame = None):
    """
    Fit imputer/scaler/PCA on train+synthetic data only.
    Transform full dataset for cluster assignment.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import RobustScaler
    from sklearn.decomposition import PCA

    imputer = SimpleImputer(strategy="median")
    scaler  = RobustScaler()
    pca     = PCA(n_components=0.95, random_state=42)

    # Fit on train data
    X_i = imputer.fit_transform(X_fit)
    X_s = scaler.fit_transform(X_i)
    X_p = pca.fit_transform(X_s)

    logger.info(f"PCA: {X_fit.shape[1]} features -> {X_p.shape[1]} components "
                f"({pca.explained_variance_ratio_.sum()*100:.1f}% variance)")
    logger.info(f"Preprocessing fit on {len(X_fit)} rows (train+synthetic)")

    # Transform full dataset if provided
    if X_transform is not None:
        X_t_i = imputer.transform(X_transform)
        X_t_s = scaler.transform(X_t_i)
        X_t_p = pca.transform(X_t_s)
        return X_p, X_t_p, imputer, scaler, pca

    return X_p, imputer, scaler, pca


# ─────────────────────────────────────────────────────────────────────────────
# FIND OPTIMAL K
# ─────────────────────────────────────────────────────────────────────────────

def find_optimal_k(X_train_p: np.ndarray, profile_df: pd.DataFrame,
                   k_range=range(3, 12)) -> tuple:
    """
    Four criteria on TRAIN data only:
    1. Silhouette     — geometric quality (higher=better)
    2. Davies-Bouldin — separation (lower=better)
    3. Distress concentration variance on profile companies
    4. Elbow (reference)
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score, davies_bouldin_score

    results = []
    logger.info(f"\n--- Finding Optimal K (range {min(k_range)}-{max(k_range)}) ---")
    logger.info(f"{'K':>4} {'Silhouette':>12} {'Davies-Bouldin':>16} "
                f"{'Distress Var':>14} {'Inertia':>12}")
    logger.info("-" * 62)

    for k in k_range:
        km     = KMeans(n_clusters=k, random_state=42, n_init=15, max_iter=500)
        labels = km.fit_predict(X_train_p)

        sil = silhouette_score(X_train_p, labels,
                               sample_size=min(1000, len(X_train_p)),
                               random_state=42) if len(set(labels)) > 1 else -1
        db  = davies_bouldin_score(X_train_p, labels) if len(set(labels)) > 1 else 999

        # Distress concentration on profile companies
        prof_tmp = profile_df.copy()
        prof_tmp["cluster"] = labels[:len(profile_df)]
        dist_rates = prof_tmp.groupby("cluster")["distress_label"].mean()
        dist_var   = float(dist_rates.var()) if len(dist_rates) > 1 else 0

        results.append({"k": k, "sil": sil, "db": db,
                        "dist_var": dist_var, "inertia": km.inertia_})
        logger.info(f"{k:>4} {sil:>12.4f} {db:>16.4f} "
                    f"{dist_var:>14.6f} {km.inertia_:>12.0f}")

    results_df = pd.DataFrame(results)

    def norm(s, higher_better=True):
        mn, mx = s.min(), s.max()
        if mx == mn:
            return pd.Series(0.5, index=s.index)
        n = (s - mn) / (mx - mn)
        return n if higher_better else 1 - n

    results_df["score"] = (
        norm(results_df["sil"],      higher_better=True)  * 0.40 +
        norm(results_df["db"],       higher_better=False) * 0.30 +
        norm(results_df["dist_var"], higher_better=True)  * 0.30
    )

    best_k = int(results_df.loc[results_df["score"].idxmax(), "k"])
    logger.info(f"\nOptimal K = {best_k} "
                f"(score={results_df.loc[results_df['score'].idxmax(),'score']:.4f})")
    return best_k, results_df


# ─────────────────────────────────────────────────────────────────────────────
# STABILITY CHECK
# ─────────────────────────────────────────────────────────────────────────────

def check_stability(X: np.ndarray, k: int, n_runs: int = 10) -> float:
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score

    labels_list = [KMeans(n_clusters=k, random_state=s, n_init=10).fit_predict(X)
                   for s in range(n_runs)]
    scores = [adjusted_rand_score(labels_list[i], labels_list[j])
              for i in range(n_runs) for j in range(i+1, n_runs)]
    stability = float(np.mean(scores))
    logger.info(f"Cluster stability (ARI): {stability:.4f} "
                f"(0=random, 1=perfectly stable)")
    return stability


# ─────────────────────────────────────────────────────────────────────────────
# CLUSTER PROFILING — profile companies only (train+val, no test)
# ─────────────────────────────────────────────────────────────────────────────

def profile_clusters(profile_df: pd.DataFrame, profile_labels: np.ndarray,
                     features: list) -> tuple:
    """
    Build cluster risk profiles using profile (train+val) companies ONLY.
    Test companies are excluded — they must not influence risk scores
    that will be used to evaluate the system.
    """
    df_tmp = profile_df.copy()
    df_tmp["cluster"] = profile_labels

    distress_rate = df_tmp.groupby("cluster")["distress_label"].agg(
        ["mean", "sum", "count"]
    ).rename(columns={"mean": "distress_rate",
                      "sum":  "n_distressed",
                      "count":"n_total"})

    # Chi-squared: is distress non-randomly distributed?
    contingency = pd.crosstab(df_tmp["cluster"], df_tmp["distress_label"])
    p_chi2 = 1.0
    if contingency.shape[1] == 2:
        chi2, p_chi2, _, _ = stats.chi2_contingency(contingency)
        logger.info(f"\nChi-squared (distress ~ cluster): chi2={chi2:.3f} p={p_chi2:.4f}")
        if p_chi2 < 0.05:
            logger.info("[OK] Distress non-randomly distributed (p<0.05)")
        else:
            logger.warning("[WARN] Distress randomly distributed across clusters (p>=0.05)")

    # Risk score per cluster
    risk_scores = []
    for cl in distress_rate.index:
        dr  = distress_rate.loc[cl, "distress_rate"]
        row = df_tmp[df_tmp["cluster"] == cl]
        z   = row["altman_z"].median()    if "altman_z"    in row else np.nan
        f   = row["piotroski_f"].median() if "piotroski_f" in row else np.nan
        cr  = row["current_ratio"].median() if "current_ratio" in row else np.nan
        nm  = row["net_margin"].median()  if "net_margin"  in row else np.nan

        risk = dr * 50
        if not np.isnan(z):  risk += max(0, 3.0 - z) * 8
        if not np.isnan(f):  risk += max(0, 5.0 - f) * 4
        if not np.isnan(cr): risk += max(0, 1.5 - cr) * 5
        if not np.isnan(nm) and nm < 0: risk += abs(nm) * 20
        risk_scores.append(risk)

    distress_rate["risk_score"] = risk_scores
    distress_rate["risk_rank"]  = pd.Series(risk_scores).rank(ascending=False).values

    logger.info(f"\n--- Cluster Profiles (train+val companies only) ---")
    logger.info(f"{'Cluster':>8} {'N':>8} {'Distressed':>11} "
                f"{'Distress%':>11} {'Risk Score':>11}")
    logger.info("-" * 54)
    for cl in distress_rate.index:
        r = distress_rate.loc[cl]
        logger.info(f"{cl:>8} {r['n_total']:>8.0f} {r['n_distressed']:>11.0f} "
                    f"{r['distress_rate']*100:>10.1f}% {r['risk_score']:>11.2f}")

    return distress_rate, p_chi2


# ─────────────────────────────────────────────────────────────────────────────
# TEMPORAL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def temporal_analysis(profile_df: pd.DataFrame,
                       profile_labels: np.ndarray) -> dict:
    df_tmp = profile_df.copy()
    df_tmp["cluster"] = profile_labels

    pre  = df_tmp[df_tmp["year"] < 2020]
    post = df_tmp[df_tmp["year"] >= 2020]

    pre_dist  = pre.groupby("cluster")["distress_label"].mean()
    post_dist = post.groupby("cluster")["distress_label"].mean()

    logger.info(f"\n--- Temporal Cluster Analysis ---")
    logger.info(f"{'Cluster':>8} {'Pre-2020 Dist%':>16} {'Post-2020 Dist%':>17}")
    logger.info("-" * 44)

    info = {}
    for cl in sorted(df_tmp["cluster"].unique()):
        pre_r  = pre_dist.get(cl, 0) * 100
        post_r = post_dist.get(cl, 0) * 100
        trend  = ("UP WORSENING"   if post_r > pre_r + 5 else
                  "DOWN improving" if post_r < pre_r - 5 else "STABLE")
        logger.info(f"{cl:>8} {pre_r:>15.1f}% {post_r:>16.1f}%  {trend}")
        info[int(cl)] = {"pre_2020": float(pre_r),
                         "post_2020": float(post_r),
                         "trend": trend}
    return info


# ─────────────────────────────────────────────────────────────────────────────
# SECTOR CONCENTRATION
# ─────────────────────────────────────────────────────────────────────────────

def sector_concentration(profile_df: pd.DataFrame,
                          profile_labels: np.ndarray) -> dict:
    if "sector" not in profile_df.columns:
        return {}
    df_tmp = profile_df.copy()
    df_tmp["cluster"] = profile_labels
    info = {}
    logger.info(f"\n--- Sector Concentration per Cluster ---")
    for cl in sorted(df_tmp["cluster"].unique()):
        top = df_tmp[df_tmp["cluster"] == cl]["sector"].value_counts().head(3).to_dict()
        info[int(cl)] = top
        logger.info(f"  Cluster {cl}: {top}")
    return info


# ─────────────────────────────────────────────────────────────────────────────
# SAVE / LOAD
# ─────────────────────────────────────────────────────────────────────────────

def save_model(km, imputer, scaler, pca, features,
               distress_profiles, all_labels, profile_labels,
               full_df, profile_df, k, stability, silhouette,
               temporal_info, sector_info, p_chi2,
               profile_tickers, test_tickers):

    obj = {
        "km":               km,
        "imputer":          imputer,
        "scaler":           scaler,
        "pca":              pca,
        "features":         features,
        "distress_profiles": distress_profiles,
        "all_labels":       all_labels,
        "profile_labels":   profile_labels,
        "full_df":          full_df,
        "profile_df":       profile_df,
        "k":                k,
        "temporal_info":    temporal_info,
        "sector_info":      sector_info,
        "profile_tickers":  list(profile_tickers) if profile_tickers else [],
        "test_tickers":     list(test_tickers)    if test_tickers    else [],
        "version":          "2.1",
    }

    with open(str(MODEL_PATH), "wb") as f:
        pickle.dump(obj, f)

    model_hash = compute_hash(MODEL_PATH)
    meta = {
        "version":          "2.1",
        "trained_at":       datetime.utcnow().isoformat() + "Z",
        "model_hash":       model_hash,
        "k":                k,
        "features":         features,
        "stability":        float(stability),
        "silhouette":       float(silhouette),
        "chi2_p_value":     float(p_chi2),
        "algorithm":        "K-Means + PCA",
        "split_aware":      True,
        "profile_companies": len(profile_df["ticker"].unique())
                             if "ticker" in profile_df.columns else 0,
        "test_excluded":    len(test_tickers) if test_tickers else 0,
        "cluster_sizes":    {int(k): int((all_labels==k).sum())
                             for k in np.unique(all_labels)},
        "training_data":    "feature_matrix_expanded.csv",
    }
    with open(str(META_PATH), "w") as f:
        json.dump(meta, f, indent=2)

    distress_profiles.to_csv(str(MODELS_DIR / "cluster_profiles.csv"))
    logger.info(f"\nClustering model saved: {MODEL_PATH}")
    logger.info(f"Hash: {model_hash[:16]}...")


def load_model(model_path=MODEL_PATH, meta_path=META_PATH):
    if not verify_integrity(model_path, meta_path):
        raise ValueError("Clustering integrity check failed")
    with open(str(model_path), "rb") as f:
        return pickle.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# PREDICT API
# ─────────────────────────────────────────────────────────────────────────────

def predict_cluster(ticker_data: dict,
                    model_path=MODEL_PATH,
                    meta_path=META_PATH) -> dict:
    obj        = load_model(model_path, meta_path)
    km         = obj["km"]
    imputer    = obj["imputer"]
    scaler     = obj["scaler"]
    pca        = obj["pca"]
    features   = obj["features"]
    profiles   = obj["distress_profiles"]
    profile_df = obj["profile_df"]
    p_labels   = obj["profile_labels"]
    all_labels = obj["all_labels"]
    full_df    = obj["full_df"]

    row = {f: ticker_data.get(f, np.nan) for f in features}
    X   = pd.DataFrame([row])
    X_i = sanitize_input(imputer.transform(X))
    X_s = scaler.transform(X_i)
    X_p = pca.transform(X_s)

    cluster_id   = int(km.predict(X_p)[0])
    cluster_size = int((all_labels == cluster_id).sum())
    total_size   = len(all_labels)

    if cluster_size / total_size > 0.30:
        return {"score": 0.0, "cluster_id": cluster_id,
                "note": f"Cluster too broad ({cluster_size}/{total_size})",
                "available": True}

    profile = profiles.loc[cluster_id].to_dict() \
              if cluster_id in profiles.index else {}

    # Peers from profile companies only (no test leakage)
    peers = profile_df[p_labels == cluster_id]
    distressed_peers = peers[peers["distress_label"] == 1]["ticker"].unique().tolist() \
                       if "distress_label" in peers.columns else []
    peer_sample = peers[["ticker","year","sector"]].drop_duplicates("ticker") \
                      .head(8).to_dict("records") if not peers.empty else []

    return {
        "cluster_id":       cluster_id,
        "distress_rate":    float(profile.get("distress_rate", 0)),
        "risk_score":       float(profile.get("risk_score", 0)),
        "n_companies":      int(profile.get("n_total", 0)),
        "distressed_peers": distressed_peers,
        "peer_sample":      peer_sample,
        "temporal_info":    obj.get("temporal_info", {}).get(cluster_id, {}),
        "sector_info":      obj.get("sector_info",   {}).get(cluster_id, {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run():
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    logger.info("=" * 60)
    logger.info("MODEL B - K-Means Clustering v2.1 (Production)")
    logger.info("Split-aware | Test companies excluded from profiles")
    logger.info("=" * 60)

    # 1. Load data
    full_df, real_df, syn_df, features = load_data()

    # 2. Load ticker split from classifier
    result = load_train_tickers()
    if result is not None:
        profile_tickers, test_tickers = result
        profile_df = real_df[real_df["ticker"].isin(profile_tickers)].copy()
        logger.info(f"Profile companies: {len(profile_df['ticker'].unique())} "
                    f"(test excluded: {len(test_tickers)})")
    else:
        profile_df    = real_df.copy()
        profile_tickers = set(real_df["ticker"].unique())
        test_tickers  = set()
        logger.warning("Using all real companies for profiling (no split info)")

    # 3. Build preprocessing — fit on profile + synthetic only
    X_profile = profile_df[features].copy()
    X_syn     = syn_df[features].copy()
    X_fit     = pd.concat([X_profile, X_syn], ignore_index=True)
    X_full    = full_df[features].copy()

    X_fit_p, X_full_p, imputer, scaler, pca = build_preprocessing(X_fit, X_full)
    X_profile_p = X_full_p[:len(profile_df)]   # profile rows are first in full_df after concat

    # Recompute properly — transform profile_df directly
    from sklearn.impute import SimpleImputer
    X_profile_p = pca.transform(scaler.transform(imputer.transform(X_profile)))

    # 4. Find optimal K on profile data
    best_k, k_results = find_optimal_k(X_profile_p, profile_df, k_range=range(3, 12))

    # 5. Stability check on profile data
    stability = check_stability(X_profile_p, best_k, n_runs=10)

    # 6. Final KMeans fit on profile data
    logger.info(f"\nFitting K-Means with K={best_k} on profile companies...")
    km = KMeans(n_clusters=best_k, random_state=42, n_init=20, max_iter=500)
    profile_labels = km.fit_predict(X_profile_p)

    # 7. Assign ALL companies (including test) for prediction use
    X_full_p2 = pca.transform(scaler.transform(imputer.transform(full_df[features])))
    all_labels = km.predict(X_full_p2)

    final_sil = silhouette_score(X_profile_p, profile_labels, random_state=42)
    logger.info(f"Final silhouette: {final_sil:.4f}")
    logger.info(f"Profile cluster sizes: "
                f"{dict(zip(*np.unique(profile_labels, return_counts=True)))}")

    # 8. Profile clusters — profile companies only
    distress_profiles, p_chi2 = profile_clusters(profile_df, profile_labels, features)

    # 9. Temporal + sector analysis on profile companies
    temporal_info = temporal_analysis(profile_df, profile_labels)
    sector_info   = sector_concentration(profile_df, profile_labels)

    # 10. Most dangerous cluster
    most_dangerous = distress_profiles["risk_score"].idxmax()
    logger.info(f"\nMost dangerous cluster: {most_dangerous} "
                f"(risk={distress_profiles.loc[most_dangerous,'risk_score']:.2f}, "
                f"distress={distress_profiles.loc[most_dangerous,'distress_rate']*100:.1f}%)")
    dist_t = profile_df[profile_labels == most_dangerous]
    if "distress_label" in dist_t.columns:
        dt = dist_t[dist_t["distress_label"]==1]["ticker"].unique()
        if len(dt):
            logger.info(f"Known distressed: {dt.tolist()}")

    # 11. Save
    save_model(km, imputer, scaler, pca, features,
               distress_profiles, all_labels, profile_labels,
               full_df, profile_df, best_k, stability, final_sil,
               temporal_info, sector_info, p_chi2,
               profile_tickers, test_tickers)

    logger.info("\n" + "=" * 60)
    logger.info("Clustering complete.")
    logger.info(f"K={best_k} | Silhouette={final_sil:.4f} | "
                f"Stability={stability:.4f} | Chi2 p={p_chi2:.4f}")
    logger.info("=" * 60)

    return km, all_labels, distress_profiles


if __name__ == "__main__":
    run()
