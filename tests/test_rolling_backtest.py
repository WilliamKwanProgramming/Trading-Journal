from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cycle_engine import AnalysisSettings, load_tradingview_csv
from cycle_engine.rolling_backtest import (
    BacktestSettings,
    earliest_backtest_date,
    generate_rolling_signals,
    minimum_backtest_bars,
    resolve_start_index,
    run_rolling_backtest,
    simulate_trades,
)
from conftest import synthetic_frame


def _small_analysis_settings() -> AnalysisSettings:
    return AnalysisSettings(
        min_period=8,
        max_period=20,
        detection_window=40,
        detrend_length=30,
        num_cycles=2,
        phase_window=30,
        min_fit=0.0,
        min_stability=0.0,
        min_separation=3,
        forecast_horizon=10,
    )


def _execution_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2025-01-01", periods=9)
    frame = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [100, 101, 102, 103, 104, 105, 106, 107, 108],
            "high": [101, 102, 103, 104, 105, 106, 107, 108, 109],
            "low": [99, 100, 101, 102, 103, 104, 105, 106, 107],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5],
        }
    )
    signal_names = ["None", "Bullish", "None", "Bearish", "Bullish", "None", "None"]
    rows = []
    for offset, signal in enumerate(signal_names, start=2):
        rows.append(
            {
                "date": dates[offset],
                "bar_index": offset,
                "signal": signal,
                "selected_cycle_periods": (12.0, 18.0),
            }
        )
    return frame, pd.DataFrame(rows)


def test_cutoff_is_configuration_derived_and_rejects_early_date() -> None:
    raw = synthetic_frame(75, (12.0, 18.0)).to_csv(index=False).encode()
    frame, _ = load_tradingview_csv(raw)
    settings = _small_analysis_settings()
    assert minimum_backtest_bars(settings) == 64
    earliest = earliest_backtest_date(frame, settings)
    assert earliest == frame["timestamp"].iloc[63]
    with pytest.raises(ValueError, match="too early"):
        resolve_start_index(frame, settings, frame["timestamp"].iloc[62])


def test_strategy_starts_flat_waits_then_reverses_on_next_bar_open() -> None:
    frame, signals = _execution_fixture()
    equity, trades, _ = simulate_trades(frame, signals, BacktestSettings())
    assert equity["position"].iloc[0] == "Flat"
    assert trades["signal_date"].iloc[0] == signals["date"].iloc[1]
    assert trades["entry_date"].iloc[0] == frame["timestamp"].iloc[4]
    assert trades["entry_price"].iloc[0] == pytest.approx(frame["open"].iloc[4])
    assert trades["direction"].tolist() == ["Long", "Short", "Long"]
    assert trades["entry_signal_type"].tolist() == ["Bullish", "Bearish", "Bullish"]
    assert trades["exit_signal_type"].iloc[0] == "Bearish"
    assert trades["exit_signal_type"].iloc[1] == "Bullish"
    assert trades["exit_signal_type"].iloc[-1] == "end of data"
    assert equity["position"].iloc[-1] == "Flat"


def test_missing_next_open_falls_back_to_next_close() -> None:
    frame, signals = _execution_fixture()
    frame.loc[4, "open"] = np.nan
    _, trades, summary = simulate_trades(frame, signals, BacktestSettings())
    assert trades["entry_price"].iloc[0] == pytest.approx(frame["close"].iloc[4])
    assert summary["open_to_close_fallbacks"] == 1


def test_future_mutation_does_not_change_prior_rolling_signals() -> None:
    source = synthetic_frame(75, (12.0, 18.0))
    original, original_metadata = load_tradingview_csv(source.to_csv(index=False).encode())
    changed_source = source.copy()
    changed_source.loc[70:, ["open", "high", "low", "close"]] += 10_000
    changed, changed_metadata = load_tradingview_csv(changed_source.to_csv(index=False).encode())
    settings = _small_analysis_settings()
    start_index = minimum_backtest_bars(settings) - 1
    first = generate_rolling_signals(original, original_metadata, settings, start_index)
    second = generate_rolling_signals(changed, changed_metadata, settings, start_index)
    columns = [
        "date", "composite", "previous_composite", "next_projected_composite",
        "projected_slope", "cycle_state", "signal", "selected_cycle_periods",
    ]
    pd.testing.assert_frame_equal(
        first.loc[first["bar_index"] < 70, columns].reset_index(drop=True),
        second.loc[second["bar_index"] < 70, columns].reset_index(drop=True),
    )


def test_projected_state_transitions_cannot_skip_between_valid_daily_models() -> None:
    raw = synthetic_frame(75, (12.0, 18.0)).to_csv(index=False).encode()
    frame, metadata = load_tradingview_csv(raw)
    settings = _small_analysis_settings()
    signals = generate_rolling_signals(
        frame, metadata, settings, minimum_backtest_bars(settings) - 1
    )
    active_state = "Neutral"
    for row in signals.itertuples(index=False):
        if not row.model_valid:
            continue
        assert row.cycle_state in {"Bullish", "Bearish"}
        expected_signal = row.cycle_state if row.cycle_state != active_state else "None"
        assert row.signal == expected_signal
        if row.signal != "None":
            active_state = row.cycle_state


def test_full_backtest_is_deterministic() -> None:
    raw = synthetic_frame(68, (12.0, 18.0)).to_csv(index=False).encode()
    frame, metadata = load_tradingview_csv(raw)
    analysis_settings = _small_analysis_settings()
    backtest_settings = BacktestSettings(commission_per_order=1.0, slippage_pct=0.05)
    start = earliest_backtest_date(frame, analysis_settings)
    first = run_rolling_backtest(frame, metadata, analysis_settings, backtest_settings, start)
    second = run_rolling_backtest(frame, metadata, analysis_settings, backtest_settings, start)
    pd.testing.assert_frame_equal(first.signals, second.signals)
    pd.testing.assert_frame_equal(first.trades, second.trades)
    pd.testing.assert_frame_equal(first.equity_curve, second.equity_curve)
    assert first.summary == second.summary


def test_existing_dashboard_tabs_are_preserved() -> None:
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    for tab in ("Overview", "Composite chart", "Spectrum", "Cycle table", "Validation", "Export"):
        assert f'"{tab}"' in app_source
    assert '"Rolling Trade Backtest"' in app_source
