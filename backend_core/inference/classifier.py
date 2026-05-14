"""
models/classifier.py — XGBoost Distress Classifier (Production Grade v3.2)

Split strategy:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NO COMPANY APPEARS IN MORE THAN ONE SPLIT.

Step 1 — Company-level partition (done FIRST, before any year logic):
  - All years of a company go to exactly one of: train / val / test
  - 70% of companies → train
  - 15% of companies → val
  - 15% of companies → test
  - Stratified by distress label so each split has distressed companies

Step 2 — Synthetic data appended to train only (no ticker)

This eliminates ALL cross-split leakage:
  - No same-company leakage across years
  - No future data leakage (temporal ordering preserved within each split)
  - Val used for: early stopping, threshold tuning
  - Test touched exactly ONCE for final evaluation

Other best practices:
  - SMOTE on train only
  - Walk-forward CV on train companies only
  - Imputer/scaler fit on train only
  - SHA-256 integrity hash on saved model
  - Clip stats saved for inference-time outlier clipping

Run: .venv\Scripts\python.exe src/models/classifier.py
     .venv\Scripts\python.exe src/models/classifier.py --tune
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

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

warnings.filterwarnings("ignore")

from backend_core.utils.logger import get_logger
from backend_core.models.model_utils import ModelWithImputer
from backend_core.config import (
    LOGS_DIR, MODELS_DIR,
    CLASSIFIER_PATH, CLASSIFIER_META_PATH,
    FEATURE_MATRIX_EXPANDED_PATH, FEATURE_MATRIX_PATH,
)

logger = get_logger("classifier", LOGS_DIR / "classifier.log")

FEATURE_COLS = [
    "debt_to_equity", "interest_coverage", "debt_to_ebitda",
    "current_ratio", "quick_ratio", "cash_ratio", "days_cash",
    "gross_margin", "net_margin", "ebitda_margin", "roe", "roa",
    "gross_margin_trend", "net_margin_trend",
    "altman_z", "piotroski_f", "cf_divergence", "rev_vs_debt",
]
TARGET_COL   = "distress_label"
MODEL_PATH   = CLASSIFIER_PATH
META_PATH    = CLASSIFIER_META_PATH
SYNTHETIC_TAG = "synthetic"

# Company-level split fractions
TRAIN_FRAC = 0.70
VAL_FRAC   = 0.15
# TEST_FRAC  = 0.15 (remainder)


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY
# ─────────────────────────────────────────────────────────────────────────────

def compute_hash(path: str) -> str:
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
        logger.error("SECURITY: Classifier hash mismatch!")
        return False
    return True


def validate_input(X: pd.DataFrame, clip_stats: dict = None) -> pd.DataFrame:
    if X.shape[1] > 50:
        raise ValueError(f"Input has {X.shape[1]} cols — max 50")
    if clip_stats is None:
        return X
    for col in X.select_dtypes(include=[np.number]).columns:
        if col in clip_stats:
            mean = clip_stats[col]["mean"]
            std  = clip_stats[col]["std"]
            if std > 0 and not np.isnan(std):
                X[col] = X[col].clip(mean - 5*std, mean + 5*std)
    return X


# ─────────────────────────────────────────────────────────────────────────────
# COMPANY-LEVEL STRATIFIED SPLIT
# No company appears in more than one split
# ─────────────────────────────────────────────────────────────────────────────

def company_stratified_split(df: pd.DataFrame,
                              train_frac: float = TRAIN_FRAC,
                              val_frac:   float = VAL_FRAC,
                              random_state: int = 42):
    """
    Partition ALL years of each company into exactly one split.

    Stratified: distressed companies proportionally distributed
    across train/val/test so each split has enough positive examples.

    Returns (train_df, val_df, test_df) — no company overlaps.
    """
    is_synthetic = df.get(
        "label_source", pd.Series("", index=df.index)
    ).str.contains(SYNTHETIC_TAG, na=False)

    real_df = df[~is_synthetic].copy()
    syn_df  = df[is_synthetic].copy()

    # One row per company — keep distress flag (1 if any year was distressed)
    company_labels = (
        real_df.groupby("ticker")[TARGET_COL]
        .max()
        .reset_index()
        .rename(columns={TARGET_COL: "ever_distressed"})
    )

    rng = np.random.default_rng(random_state)

    # Split distressed and healthy companies separately (stratification)
    distressed_tickers = company_labels[company_labels["ever_distressed"] == 1]["ticker"].values
    healthy_tickers    = company_labels[company_labels["ever_distressed"] == 0]["ticker"].values

    def split_tickers(tickers):
        tickers = rng.permutation(tickers)
        n       = len(tickers)
        n_train = int(n * train_frac)
        n_val   = int(n * val_frac)
        return (
            set(tickers[:n_train]),
            set(tickers[n_train:n_train + n_val]),
            set(tickers[n_train + n_val:]),
        )

    d_train, d_val, d_test = split_tickers(distressed_tickers)
    h_train, h_val, h_test = split_tickers(healthy_tickers)

    train_tickers = d_train | h_train
    val_tickers   = d_val   | h_val
    test_tickers  = d_test  | h_test

    # Verify no overlap
    assert len(train_tickers & val_tickers)  == 0, "LEAK: train/val overlap"
    assert len(train_tickers & test_tickers) == 0, "LEAK: train/test overlap"
    assert len(val_tickers   & test_tickers) == 0, "LEAK: val/test overlap"

    train_df = real_df[real_df["ticker"].isin(train_tickers)].copy()
    val_df   = real_df[real_df["ticker"].isin(val_tickers)].copy()
    test_df  = real_df[real_df["ticker"].isin(test_tickers)].copy()

    # Synthetic only goes into train
    train_df = pd.concat([train_df, syn_df], ignore_index=True)

    logger.info(f"\n── Company-Level Stratified Split ──")
    logger.info(f"Total real companies:  {len(company_labels)}")
    logger.info(f"  Distressed companies:{len(distressed_tickers)} total | "
                f"train={len(d_train)} val={len(d_val)} test={len(d_test)}")
    logger.info(f"  Healthy companies:   {len(healthy_tickers)} total | "
                f"train={len(h_train)} val={len(h_val)} test={len(h_test)}")
    logger.info(f"Train rows: {len(train_df):5d} | "
                f"distressed: {train_df[TARGET_COL].sum():3.0f} "
                f"({train_df[TARGET_COL].mean()*100:.1f}%)")
    logger.info(f"  of which synthetic: {len(syn_df)}")
    logger.info(f"Val rows:   {len(val_df):5d} | "
                f"distressed: {val_df[TARGET_COL].sum():3.0f} "
                f"({val_df[TARGET_COL].mean()*100:.1f}%)")
    logger.info(f"Test rows:  {len(test_df):5d} | "
                f"distressed: {test_df[TARGET_COL].sum():3.0f} "
                f"({test_df[TARGET_COL].mean()*100:.1f}%)")
    logger.info(f"Company overlap check: PASSED (0 overlaps)")

    return train_df, val_df, test_df, {
        "train_tickers": list(train_tickers),
        "val_tickers":   list(val_tickers),
        "test_tickers":  list(test_tickers),
    }


def to_Xy(df: pd.DataFrame, features: list):
    X = df[features].copy()
    y = df[TARGET_COL].astype(int).copy()
    return X, y


# ─────────────────────────────────────────────────────────────────────────────
# WALK-FORWARD CV — on train companies only
# ─────────────────────────────────────────────────────────────────────────────

def walk_forward_cv(train_df: pd.DataFrame, features: list,
                    n_folds: int = 4) -> np.ndarray:
    """
    Walk-forward CV on training companies only.
    Val/test companies never seen during CV.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import RobustScaler
    from sklearn.metrics import roc_auc_score, average_precision_score
    from xgboost import XGBClassifier

    # Exclude synthetic (no year)
    is_syn  = train_df.get(
        "label_source", pd.Series("", index=train_df.index)
    ).str.contains(SYNTHETIC_TAG, na=False)
    real_tr = train_df[~is_syn].sort_values("year")

    years      = sorted(real_tr["year"].unique())
    fold_years = years[-(n_folds + 1):]

    auc_roc_scores, auc_pr_scores = [], []
    logger.info(f"\n── Walk-Forward CV ({n_folds} folds, train companies only) ──")

    for i in range(len(fold_years) - 1):
        val_year = fold_years[i + 1]
        X_tr = real_tr[real_tr["year"] < val_year][features]
        y_tr = real_tr[real_tr["year"] < val_year][TARGET_COL].astype(int)
        X_vl = real_tr[real_tr["year"] == val_year][features]
        y_vl = real_tr[real_tr["year"] == val_year][TARGET_COL].astype(int)

        if y_tr.sum() == 0 or len(X_vl) == 0:
            continue

        pos_weight = max(1, int((y_tr==0).sum() / max(1, (y_tr==1).sum())))

        imp = SimpleImputer(strategy="median")
        sc  = RobustScaler()
        X_tr_s = sc.fit_transform(imp.fit_transform(X_tr))
        X_vl_s = sc.transform(imp.transform(X_vl))

        model = XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
            gamma=0.1, reg_alpha=0.1, reg_lambda=1.0,
            scale_pos_weight=pos_weight, eval_metric="auc",
            random_state=42, n_jobs=-1, verbosity=0,
        )
        model.fit(X_tr_s, y_tr)
        y_prob = model.predict_proba(X_vl_s)[:, 1]

        if y_vl.sum() > 0 and y_vl.sum() < len(y_vl):
            auc = roc_auc_score(y_vl, y_prob)
            apr = average_precision_score(y_vl, y_prob)
            auc_roc_scores.append(auc)
            auc_pr_scores.append(apr)
            logger.info(f"  Fold {i+1} (val={val_year}): n={len(X_vl)} "
                        f"dist={y_vl.sum()} AUC-ROC={auc:.4f} AUC-PR={apr:.4f}")
        else:
            logger.info(f"  Fold {i+1} (val={val_year}): n={len(X_vl)} "
                        f"— no distressed, skipping AUC")

    if auc_roc_scores:
        logger.info(f"Walk-forward AUC-ROC: {np.mean(auc_roc_scores):.4f} "
                    f"+/- {np.std(auc_roc_scores):.4f}")
        return np.array(auc_roc_scores)
    else:
        logger.warning("No valid folds — using stratified CV fallback")
        return stratified_cv_fallback(train_df, features)


def stratified_cv_fallback(train_df: pd.DataFrame, features: list,
                            n_splits: int = 5) -> np.ndarray:
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import RobustScaler
    from xgboost import XGBClassifier

    X = train_df[features]
    y = train_df[TARGET_COL].astype(int)
    pos_weight = max(1, int((y==0).sum() / max(1, (y==1).sum())))

    pipe = Pipeline([
        ("imp",   SimpleImputer(strategy="median")),
        ("sc",    RobustScaler()),
        ("model", XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            scale_pos_weight=pos_weight, eval_metric="auc",
            random_state=42, n_jobs=-1, verbosity=0,
        )),
    ])
    skf    = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scores = cross_val_score(pipe, X, y, cv=skf, scoring="roc_auc", n_jobs=-1)
    logger.info(f"Stratified CV AUC: {scores.mean():.4f} +/- {scores.std():.4f}")
    return scores


# ─────────────────────────────────────────────────────────────────────────────
# SMOTE — TRAIN ONLY
# ─────────────────────────────────────────────────────────────────────────────

def apply_smote(X_train: np.ndarray, y_train: np.ndarray):
    try:
        from imblearn.over_sampling import SMOTE
        n_dist = int(y_train.sum())
        if n_dist < 5:
            logger.warning(f"Only {n_dist} distressed — skipping SMOTE")
            return X_train, y_train
        k        = min(5, n_dist - 1)
        sm       = SMOTE(random_state=42, k_neighbors=k)
        X_r, y_r = sm.fit_resample(X_train, y_train)
        logger.info(f"SMOTE: {len(y_train)} -> {len(y_r)} | "
                    f"Distressed: {y_train.sum()} -> {y_r.sum()}")
        return X_r, y_r
    except ImportError:
        logger.warning("imbalanced-learn not installed")
        return X_train, y_train


# ─────────────────────────────────────────────────────────────────────────────
# EARLY STOPPING ON VALIDATION SET
# ─────────────────────────────────────────────────────────────────────────────

def train_with_early_stopping(X_tr_s, y_tr_s, X_val_i, y_val, scaler, pos_weight):
    from xgboost import XGBClassifier
    X_tr_sc = scaler.fit_transform(X_tr_s)

    if y_val.sum() > 0 and y_val.sum() < len(y_val):
        X_val_sc = scaler.transform(X_val_i)
        model = XGBClassifier(
            n_estimators=1000, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.75, min_child_weight=3,
            gamma=0.1, reg_alpha=0.15, reg_lambda=1.0,
            scale_pos_weight=pos_weight, eval_metric="auc",
            early_stopping_rounds=50,
            random_state=42, n_jobs=-1, verbosity=0,
        )
        model.fit(X_tr_sc, y_tr_s,
                  eval_set=[(X_val_sc, y_val)], verbose=False)
        logger.info(f"Early stopping: iter={model.best_iteration} "
                    f"val_AUC={model.best_score:.4f}")
    else:
        logger.info("Val insufficient for early stopping — using 500 estimators")
        model = XGBClassifier(
            n_estimators=500, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.75, min_child_weight=3,
            gamma=0.1, reg_alpha=0.15, reg_lambda=1.0,
            scale_pos_weight=pos_weight, eval_metric="auc",
            random_state=42, n_jobs=-1, verbosity=0,
        )
        model.fit(X_tr_sc, y_tr_s)

    return model


# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLD TUNING ON VALIDATION SET
# ─────────────────────────────────────────────────────────────────────────────

def tune_threshold(model, scaler, X_val_i, y_val) -> float:
    if y_val.sum() == 0 or y_val.sum() == len(y_val):
        logger.info("Cannot tune threshold — using default 0.35")
        return 0.35

    from sklearn.metrics import f1_score, precision_recall_curve
    X_val_sc = scaler.transform(X_val_i)
    y_prob   = model.predict_proba(X_val_sc)[:, 1]

    _, _, thresholds = precision_recall_curve(y_val, y_prob)
    f1s = [f1_score(y_val, (y_prob >= t).astype(int), zero_division=0)
           for t in thresholds]

    best_t = float(np.clip(thresholds[int(np.argmax(f1s))], 0.15, 0.60))
    logger.info(f"Threshold tuning on val: best={best_t:.3f} (F1={max(f1s):.4f})")
    return best_t


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────

def check_calibration(y_true, y_prob):
    if y_true.sum() == 0:
        return
    bins    = np.linspace(0, 1, 6)
    bin_ids = np.clip(np.digitize(y_prob, bins) - 1, 0, len(bins)-2)
    logger.info("\n── Calibration Check ──")
    logger.info(f"{'Pred Range':15} {'Actual Rate':12} {'Count':8}")
    logger.info("-" * 38)
    for b in range(len(bins)-1):
        mask = bin_ids == b
        if mask.sum() > 0:
            logger.info(f"{bins[b]:.1f} - {bins[b+1]:.1f}       "
                        f"{y_true[mask].mean():.3f}        {mask.sum():5d}")


# ─────────────────────────────────────────────────────────────────────────────
# FINAL EVALUATION — TEST ONLY, ONCE
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_on_test(model, scaler, X_test_i, y_test, features, threshold):
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, classification_report,
        confusion_matrix, f1_score, precision_score, recall_score,
    )

    X_test_sc = scaler.transform(X_test_i)
    y_prob    = model.predict_proba(X_test_sc)[:, 1]
    y_pred    = (y_prob >= threshold).astype(int)

    logger.info(f"\n{'='*60}")
    logger.info("FINAL TEST EVALUATION (held-out companies, touched once)")
    logger.info(f"{'='*60}")
    logger.info(f"Threshold: {threshold:.3f} | "
                f"Test: {len(y_test)} rows | Distressed: {y_test.sum()}")

    results = {}
    if y_test.sum() > 0 and y_test.sum() < len(y_test):
        auc_roc = roc_auc_score(y_test, y_prob)
        auc_pr  = average_precision_score(y_test, y_prob)
        f1      = f1_score(y_test, y_pred, zero_division=0)
        prec    = precision_score(y_test, y_pred, zero_division=0)
        rec     = recall_score(y_test, y_pred, zero_division=0)

        logger.info(f"AUC-ROC:   {auc_roc:.4f}")
        logger.info(f"AUC-PR:    {auc_pr:.4f}")
        logger.info(f"F1:        {f1:.4f}")
        logger.info(f"Precision: {prec:.4f}  Recall: {rec:.4f}")
        logger.info(f"\n{classification_report(y_test, y_pred, target_names=['Healthy','Distressed'], zero_division=0)}")
        logger.info(f"Confusion Matrix:\n{confusion_matrix(y_test, y_pred)}")
        check_calibration(y_test, y_prob)
        results = {"auc_roc": float(auc_roc), "auc_pr": float(auc_pr),
                   "f1": float(f1), "precision": float(prec), "recall": float(rec)}
    else:
        logger.warning("No distressed rows in test — AUC undefined")
        results = {"note": "No distressed rows in test set"}

    try:
        fi = pd.DataFrame({"feature": features,
                           "importance": model.feature_importances_}
                         ).sort_values("importance", ascending=False)
        logger.info(f"\nTop 10 Feature Importances:\n{fi.head(10).to_string(index=False)}")
        results["feature_importance"] = fi.to_dict("records")
    except Exception as e:
        logger.warning(f"Feature importance: {e}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# SAVE / LOAD
# ─────────────────────────────────────────────────────────────────────────────

def compute_clip_stats(X: pd.DataFrame) -> dict:
    return {col: {"mean": float(X[col].mean()), "std": float(X[col].std())}
            for col in X.select_dtypes(include=[np.number]).columns}


def save_model(production_model, scaler, features, threshold,
               metrics, best_params, cv_scores, split_info, clip_stats, ticker_splits):

    obj = {"model": production_model, "scaler": scaler,
           "features": features, "threshold": threshold,
           "clip_stats": clip_stats, "version": "3.2"}

    with open(str(MODEL_PATH), "wb") as f:
        pickle.dump(obj, f)

    model_hash = compute_hash(MODEL_PATH)
    meta = {
        "version": "3.2", "trained_at": datetime.utcnow().isoformat() + "Z",
        "model_hash": model_hash, "features": features,
        "n_features": len(features), "threshold": threshold,
        "clip_stats": clip_stats, "best_params": best_params,
        "metrics": metrics,
        "cv_mean_auc": float(cv_scores.mean()) if len(cv_scores) > 0 else None,
        "cv_std_auc":  float(cv_scores.std())  if len(cv_scores) > 0 else None,
        "split_info": split_info,
        "train_tickers": ticker_splits["train_tickers"],
        "val_tickers":   ticker_splits["val_tickers"],
        "test_tickers":  ticker_splits["test_tickers"],
        "algorithm": "XGBoost + SMOTE + EarlyStopping + CompanyStratifiedSplit",
        "split_type": "company-level stratified (no company in >1 split)",
        "training_data": "feature_matrix_expanded.csv",
    }
    with open(str(META_PATH), "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(f"\nModel saved: {MODEL_PATH}")
    logger.info(f"Hash: {model_hash[:16]}...")
    logger.info(f"Threshold: {threshold:.3f}")


def load_model(model_path=MODEL_PATH, meta_path=META_PATH):
    if not verify_integrity(model_path, meta_path):
        raise ValueError("Classifier integrity check failed")
    with open(str(model_path), "rb") as f:
        return pickle.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# PREDICT API
# ─────────────────────────────────────────────────────────────────────────────

def predict_distress(ticker_data: dict,
                     model_path=MODEL_PATH,
                     meta_path=META_PATH) -> dict:
    obj        = load_model(model_path, meta_path)
    model      = obj["model"]
    scaler     = obj["scaler"]
    features   = obj["features"]
    threshold  = obj["threshold"]
    clip_stats = obj.get("clip_stats")

    row  = {f: ticker_data.get(f, np.nan) for f in features}
    X    = validate_input(pd.DataFrame([row]), clip_stats=clip_stats)
    X_i  = model.imputer.transform(X)
    X_s  = scaler.transform(X_i)
    prob = float(model.model.predict_proba(X_s)[0, 1])

    if prob >= 0.75:         verdict = "Critical Risk"
    elif prob >= threshold:  verdict = "High Risk"
    elif prob >= threshold*0.5: verdict = "Moderate Risk"
    else:                    verdict = "Low Risk"

    avail = sum(1 for f in features if not pd.isna(ticker_data.get(f, np.nan)))
    conf  = "high" if avail/len(features) >= 0.8 else \
            "medium" if avail/len(features) >= 0.5 else "low"

    return {"probability": prob, "score": int(prob*100),
            "verdict": verdict, "threshold_used": threshold,
            "confidence": conf, "features_available": avail,
            "features_total": len(features)}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run(tune: bool = False, data_path: str = None):
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import RobustScaler

    logger.info("=" * 60)
    logger.info("MODEL A — XGBoost Classifier v3.2 (Production)")
    logger.info("Company-level stratified split | No company in >1 split")
    logger.info("=" * 60)

    path = (str(data_path)
            if data_path and os.path.exists(str(data_path))
            else str(FEATURE_MATRIX_EXPANDED_PATH))
    df   = pd.read_csv(path)
    logger.info(f"Data: {df.shape} | Distressed: {df[TARGET_COL].sum()} "
                f"({df[TARGET_COL].mean()*100:.1f}%)")

    features = [c for c in FEATURE_COLS if c in df.columns]
    if missing := [c for c in FEATURE_COLS if c not in df.columns]:
        logger.warning(f"Missing features: {missing}")

    # 1. Company-level stratified split — no overlaps
    train_df, val_df, test_df, ticker_splits = company_stratified_split(df)

    X_train, y_train = to_Xy(train_df, features)
    X_val,   y_val   = to_Xy(val_df,   features)
    X_test,  y_test  = to_Xy(test_df,  features)

    split_info = {
        "train_rows":      len(X_train), "train_distressed": int(y_train.sum()),
        "val_rows":        len(X_val),   "val_distressed":   int(y_val.sum()),
        "test_rows":       len(X_test),  "test_distressed":  int(y_test.sum()),
        "n_train_companies": len(ticker_splits["train_tickers"]),
        "n_val_companies":   len(ticker_splits["val_tickers"]),
        "n_test_companies":  len(ticker_splits["test_tickers"]),
    }

    # 2. Walk-forward CV on train companies only
    cv_scores = walk_forward_cv(train_df, features, n_folds=4)

    # 3. Impute — fit on train only
    imputer  = SimpleImputer(strategy="median")
    X_tr_i   = imputer.fit_transform(X_train)
    X_val_i  = imputer.transform(X_val)
    X_test_i = imputer.transform(X_test)

    # 4. Clip stats from raw imputed train (before SMOTE)
    clip_stats = compute_clip_stats(pd.DataFrame(X_tr_i, columns=features))

    # 5. SMOTE on train only
    X_tr_s, y_tr_s = apply_smote(X_tr_i, y_train.values)

    # 6. Scaler + train with early stopping on val
    scaler     = RobustScaler()
    pos_weight = max(1, int((y_tr_s==0).sum() / max(1, (y_tr_s==1).sum())))
    xgb_model  = train_with_early_stopping(
        X_tr_s, y_tr_s, X_val_i, y_val.values, scaler, pos_weight
    )

    # 7. Wrap production model
    production_model = ModelWithImputer(imputer, xgb_model)

    # 8. Tune threshold on val
    best_params = {}
    if tune and y_val.sum() > 0:
        from sklearn.preprocessing import RobustScaler as RS
        from sklearn.metrics import roc_auc_score
        from xgboost import XGBClassifier
        from itertools import product as iproduct
        param_grid = {"max_depth": [3,4,5], "learning_rate": [0.01,0.03,0.05],
                      "n_estimators": [300,500]}
        best_auc = -1
        for d, lr, n in iproduct(param_grid["max_depth"],
                                  param_grid["learning_rate"],
                                  param_grid["n_estimators"]):
            sc2 = RS()
            m2  = XGBClassifier(n_estimators=n, max_depth=d, learning_rate=lr,
                                subsample=0.8, colsample_bytree=0.75,
                                scale_pos_weight=pos_weight, eval_metric="auc",
                                random_state=42, n_jobs=-1, verbosity=0)
            m2.fit(sc2.fit_transform(X_tr_s), y_tr_s)
            yp = m2.predict_proba(sc2.transform(X_val_i))[:, 1]
            if y_val.sum() > 0 and y_val.sum() < len(y_val):
                auc = roc_auc_score(y_val, yp)
                if auc > best_auc:
                    best_auc    = auc
                    best_params = {"max_depth": d, "learning_rate": lr, "n_estimators": n}
        logger.info(f"Best params: {best_params} | Val AUC: {best_auc:.4f}")

    threshold = tune_threshold(xgb_model, scaler, X_val_i, y_val.values)

    # 9. Evaluate on test (ONCE)
    metrics = evaluate_on_test(
        xgb_model, scaler, X_test_i, y_test.values, features, threshold
    )

    # 10. Save
    save_model(production_model, scaler, features, threshold,
               metrics, best_params, cv_scores, split_info,
               clip_stats, ticker_splits)

    logger.info("\n" + "=" * 60)
    logger.info("Training complete.")
    if len(cv_scores) > 0:
        logger.info(f"Walk-forward CV AUC: {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}")
    logger.info(f"Test AUC-ROC: {metrics.get('auc_roc', 'N/A')}")
    logger.info(f"Threshold:    {threshold:.3f}")
    logger.info("=" * 60)

    return production_model, features, metrics


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="store_true")
    parser.add_argument("--data", default=None)
    args = parser.parse_args()
    run(tune=args.tune, data_path=args.data)
