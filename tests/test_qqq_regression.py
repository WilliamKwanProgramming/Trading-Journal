from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cycle_engine import AnalysisSettings, load_tradingview_csv, run_cycle_analysis


def _find_qqq_csv() -> Path | None:
    candidates = [
        path for path in Path(__file__).resolve().parents[1].rglob("*.csv")
        if "qqq" in path.name.lower() and ".venv" not in path.parts
    ]
    return candidates[0] if candidates else None


def test_qqq_daily_known_baseline_periods_when_fixture_is_available() -> None:
    path = _find_qqq_csv()
    if path is None:
        pytest.skip("No QQQ daily CSV was supplied in this workspace.")
    frame, metadata = load_tradingview_csv(path, path.name, "close")
    settings = AnalysisSettings(
        min_period=30,
        max_period=200,
        detection_window=min(1000, len(frame)),
        detrending_method="EMA",
        detrend_length=400,
        spectrum_method="Harmonic DFT (baseline)",
        fractional_periods=False,
        num_cycles=3,
        phase_window=min(250, len(frame)),
        min_fit=0.0,
        min_stability=0.0,
        min_separation=10,
        bartels_enabled=False,
        forecast_horizon=120,
    )
    result = run_cycle_analysis(frame, metadata, settings)
    detected = result.selected_cycles["period"].to_numpy()
    expected = np.array([80.0, 119.0, 191.0])
    distances = np.array([np.min(np.abs(detected - target)) for target in expected])
    assert np.all(distances <= 12), f"Expected periods near {expected.tolist()}, got {detected.tolist()}"

