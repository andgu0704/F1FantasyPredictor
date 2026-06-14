"""A small ridge regression model (closed-form, standardized inputs).

Deliberately simple: the dataset is ~hundreds of rows with five features, so a
regularized linear model is the right capacity and needs no heavy ML dependency.
Standardization keeps the L2 penalty fair across features.
"""

from __future__ import annotations

import numpy as np


class RidgeModel:
    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None
        self._coef: np.ndarray | None = None  # includes bias as the first term

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        self._mean = X.mean(axis=0)
        self._std = X.std(axis=0)
        self._std[self._std == 0] = 1.0
        Xs = (X - self._mean) / self._std
        Xb = np.hstack([np.ones((Xs.shape[0], 1)), Xs])  # bias column

        n_features = Xb.shape[1]
        penalty = self.alpha * np.eye(n_features)
        penalty[0, 0] = 0.0  # do not regularize the bias
        self._coef = np.linalg.solve(Xb.T @ Xb + penalty, Xb.T @ y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._coef is None:
            raise RuntimeError("Model is not fitted.")
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        Xs = (X - self._mean) / self._std
        Xb = np.hstack([np.ones((Xs.shape[0], 1)), Xs])
        return Xb @ self._coef
