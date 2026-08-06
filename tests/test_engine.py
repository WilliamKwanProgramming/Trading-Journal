from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from cycle_engine import AnalysisSettings, InsufficientHistoryError, load_tradingview_csv
from cycle_engine.analysis import run_cycle_analysis, run_locked_analysis
from cycle_engine.composite import projected_turns_table
from cycle_engine.exports import markdown_report
from cycle_engine.spectrum import goertzel_amplitude, harmonic_fit
from conftest import synthetic_frame


def _settings(**overrides) -> AnalysisSettings:
    base = AnalysisSettings(
        min_period=30,
        max_period=130,
        detection_window=500,
        detrend_length=260,
        num_cycles=3,
        phase_window=180,
        min_fit=0.0,
        min_stability=0.0,
        min_separation=12,
        forecast_horizon=60,
    )
    return replace(base, **overrides)


def test_short_history_has_readable_message() -> None:
    csv = synthetic_frame(150).to_csv(index=False).encode()
    frame, metadata = load_tradingview_csv(csv)
    with pytest.raises(InsufficientHistoryError, match="Insufficient history"):
        run_cycle_analysis(frame, metadata, _settings(max_period=100))


def test_dataset_below_one_thousand_bars_does_not_crash(tradingview_csv: bytes) -> None:
    frame, metadata = load_tradingview_csv(tradingview_csv)
    result = run_cycle_analysis(frame, metadata, _settings())
    assert len(result.raw_data) == 600
    assert 1 <= len(result.selected_cycles) <= 3
    assert len(result.composite.values.query("segment == 'forecast'")) == 60
    turns = projected_turns_table(result.composite, len(result.raw_data))
    assert list(turns.columns) == ["date", "turn", "bars_ahead", "composite"]
    assert turns["date"].is_monotonic_increasing
    assert (turns["bars_ahead"] >= 1).all()
    assert len(result.composite.historical_peaks) > 0
    assert len(result.composite.historical_troughs) > 0


def test_goertzel_matches_harmonic_amplitude_at_dft_bin() -> None:
    period = 40.0
    times = np.arange(400, dtype=float)
    values = 3.25 * np.sin(2 * np.pi * times / period + 0.7)
    harmonic_amplitude, _, fit, _ = harmonic_fit(values, times, period)
    assert goertzel_amplitude(values, period) == pytest.approx(harmonic_amplitude, rel=1e-10)
    assert fit == pytest.approx(1.0)


def test_locked_report_view_does_not_mutate_forecast(tradingview_csv: bytes) -> None:
    frame, metadata = load_tradingview_csv(tradingview_csv)
    as_of = frame["timestamp"].iloc[520]
    locked = run_locked_analysis(frame, metadata, _settings(), as_of)
    before = locked.composite.values.copy(deep=True)
    _ = markdown_report(locked)
    pd.testing.assert_frame_equal(before, locked.composite.values)


def test_future_projection_does_not_use_future_prices() -> None:
    original = synthetic_frame(600)
    as_of_position = 519
    prefix_bytes = original.iloc[: as_of_position + 1].to_csv(index=False).encode()
    altered = original.copy()
    altered.loc[as_of_position + 1 :, "close"] += np.linspace(0, 10_000, len(altered) - as_of_position - 1)
    altered.loc[as_of_position + 1 :, ["open", "high", "low"]] = altered.loc[
        as_of_position + 1 :, ["close", "close", "close"]
    ].to_numpy()
    full_bytes = altered.to_csv(index=False).encode()

    prefix, prefix_metadata = load_tradingview_csv(prefix_bytes)
    full, full_metadata = load_tradingview_csv(full_bytes)
    settings = _settings()
    prefix_result = run_cycle_analysis(prefix, prefix_metadata, settings)
    locked_result = run_locked_analysis(full, full_metadata, settings, prefix["timestamp"].iloc[-1])
    np.testing.assert_allclose(
        prefix_result.composite.values["composite"],
        locked_result.composite.values["composite"],
        rtol=1e-12,
        atol=1e-12,
    )
