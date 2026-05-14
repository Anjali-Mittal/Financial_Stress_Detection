"""
models/model_utils.py — Shared classes and utilities for all models.

ModelWithImputer MUST live here (not inside classifier.py) so pickle
can find the class definition when loading from any module.
"""

import numpy as np
import pandas as pd


class ModelWithImputer:
    """
    Production wrapper that bundles imputer + trained pipeline.
    Defined at module level so pickle can serialize/deserialize correctly
    regardless of which script loads it.
    """
    def __init__(self, imputer, model):
        self.imputer = imputer
        self.model   = model

    def predict_proba(self, X):
        if isinstance(X, pd.DataFrame):
            X = X.values
        X_i = self.imputer.transform(X)
        return self.model.predict_proba(X_i)

    def predict(self, X):
        if isinstance(X, pd.DataFrame):
            X = X.values
        X_i = self.imputer.transform(X)
        return self.model.predict(X_i)

    def predict_proba_df(self, df: pd.DataFrame, features: list) -> float:
        """Convenience: takes a DataFrame and feature list, returns distress prob."""
        row = df[features].values
        return float(self.predict_proba(row)[0, 1])
