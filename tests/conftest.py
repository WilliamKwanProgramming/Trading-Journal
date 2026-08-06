from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def synthetic_frame(bars: int = 600, periods: tuple[float, ...] = (60.0, 105.0)) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    t = np.arange(bars, dtype=float)
    trend = 100.0 + 0.025 * t
    cycles = sum((5.0 / (index + 1)) * np.sin(2 * np.pi * t / period + index * 0.4) for index, period in enumerate(periods))
    close = trend + cycles + rng.normal(0, 0.25, bars)
    return pd.DataFrame(
        {
            "time": pd.bdate_range("2020-01-01", periods=bars),
            "open": close - 0.2,
            "high": close + 0.8,
            "low": close - 0.9,
            "close": close,
            "Volume": np.arange(bars) + 1_000_000,
            "Ignored indicator": rng.normal(size=bars),
        }
    )


@pytest.fixture
def tradingview_csv() -> bytes:
    return synthetic_frame().to_csv(index=False).encode()

