"""Transparent EMA and Hodrick-Prescott detrending implementations."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import spsolve


def hp_lambda_from_cutoff(cutoff_bars: int) -> float:
    """Map a readable cutoff length to an HP lambda using its frequency response."""
    cutoff = max(float(cutoff_bars), 3.0)
    denominator = 16.0 * np.sin(np.pi / cutoff) ** 4
    return float(1.0 / max(denominator, np.finfo(float).eps))


def ema_detrend(values: pd.Series, length: int) -> tuple[pd.Series, pd.Series]:
    numeric = pd.Series(values, dtype=float).reset_index(drop=True)
    trend = numeric.ewm(span=max(3, int(length)), adjust=False, min_periods=1).mean()
    return numeric - trend, trend


def hp_detrend(values: pd.Series, length: int) -> tuple[pd.Series, pd.Series]:
    numeric = pd.Series(values, dtype=float).reset_index(drop=True)
    n = len(numeric)
    if n < 4:
        raise ValueError("HP detrending requires at least four observations.")
    diagonals = [np.ones(n - 2), -2 * np.ones(n - 2), np.ones(n - 2)]
    difference = sparse.diags(diagonals, [0, 1, 2], shape=(n - 2, n), format="csc")
    penalty = hp_lambda_from_cutoff(length)
    system = sparse.eye(n, format="csc") + penalty * (difference.T @ difference)
    trend_values = spsolve(system, numeric.to_numpy())
    trend = pd.Series(trend_values, index=numeric.index, name="trend")
    return numeric - trend, trend


def detrend(values: pd.Series, method: str, length: int) -> tuple[pd.Series, pd.Series]:
    if method.upper() == "EMA":
        return ema_detrend(values, length)
    if method.upper() in {"HP", "HP FILTER", "HP-FILTER"}:
        return hp_detrend(values, length)
    raise ValueError(f"Unknown detrending method: {method}")

