"""
Model C: sklearn HistGradientBoostingRegressor with ONE fixed configuration,
written down before any Stage 2 result was computed. No hyperparameter
search of any kind.

  - early_stopping=False: sklearn's early stopping carves a RANDOM
    validation split out of the training rows, which would break
    determinism and mix hours across the temporal structure. Disabled.
  - random_state=0: fixes any remaining internal randomness.
  - min_samples_leaf=200: leaves must summarize >= 200 training hours, a
    coarse guard against memorizing individual hours.
  - No input preprocessing (trees are scale-invariant). The only fitted
    transform is sklearn's internal feature binning, which is fit inside
    .fit() on the training rows passed to it.

No serialized model is written; per-fold summaries go to the results JSON.
"""

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

CONFIG = {
    "loss": "squared_error",
    "learning_rate": 0.1,
    "max_iter": 200,
    "max_leaf_nodes": 31,
    "max_depth": None,
    "min_samples_leaf": 200,
    "l2_regularization": 0.0,
    "max_bins": 255,
    "early_stopping": False,
    "random_state": 0,
}


def fit_tree(X_train: np.ndarray, y_train: np.ndarray) -> HistGradientBoostingRegressor:
    X_train = np.asarray(X_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    if np.isnan(X_train).any() or np.isnan(y_train).any():
        raise ValueError("NaN in training data")
    return HistGradientBoostingRegressor(**CONFIG).fit(X_train, y_train)


def predict_tree(model: HistGradientBoostingRegressor, X: np.ndarray) -> np.ndarray:
    return model.predict(np.asarray(X, dtype=float))


def model_summary(model: HistGradientBoostingRegressor, n_train: int) -> dict:
    return {"n_iter": int(model.n_iter_), "n_train": int(n_train), "n_features_in": int(model.n_features_in_)}
