from __future__ import annotations

from dataclasses import replace

from cycle_engine import AnalysisSettings, load_tradingview_csv
from cycle_engine.validation import walk_forward_validate
from conftest import synthetic_frame


def test_walk_forward_comparison_runs_on_small_dataset() -> None:
    csv = synthetic_frame(560).to_csv(index=False).encode()
    frame, metadata = load_tradingview_csv(csv)
    settings = replace(
        AnalysisSettings(),
        min_period=25,
        max_period=100,
        detection_window=280,
        detrend_length=180,
        phase_window=120,
        forecast_horizon=30,
        min_fit=0.0,
        min_stability=0.0,
    )
    result = walk_forward_validate(frame, metadata, settings, max_splits=2)
    assert {"EMA · 1-cycle", "HP · 3-cycle", "Seasonal naive"}.issubset(set(result.summary["model"]))
    assert len(result.segments) == 14

