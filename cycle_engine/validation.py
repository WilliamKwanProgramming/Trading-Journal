"""Leakage-controlled walk-forward comparison of cycle configurations."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .analysis import run_cycle_analysis
from .models import AnalysisSettings, DataMetadata, ValidationResult


def _safe_correlation(actual: np.ndarray, forecast: np.ndarray) -> float:
    if len(actual) < 3 or np.std(actual) <= 1e-12 or np.std(forecast) <= 1e-12:
        return np.nan
    return float(np.corrcoef(actual, forecast)[0, 1])


def _turns(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(values) < 5:
        return np.array([], dtype=int), np.array([], dtype=int)
    prominence = max(float(np.std(values)) * 0.10, 1e-12)
    distance = max(2, len(values) // 12)
    peaks, _ = find_peaks(values, prominence=prominence, distance=distance)
    troughs, _ = find_peaks(-values, prominence=prominence, distance=distance)
    return peaks, troughs


def _turn_metrics(actual: np.ndarray, forecast: np.ndarray, tolerance: int) -> tuple[float, float]:
    actual_turns = _turns(actual)
    forecast_turns = _turns(forecast)
    errors: list[int] = []
    for actual_kind, forecast_kind in zip(actual_turns, forecast_turns):
        for turn in actual_kind:
            if len(forecast_kind):
                errors.append(int(np.min(np.abs(forecast_kind - turn))))
    if not errors:
        return np.nan, np.nan
    return float(np.mean(errors)), float(100.0 * np.mean(np.asarray(errors) <= tolerance))


def _linear_residual_target(train: np.ndarray, future: np.ndarray, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    size = min(len(train), max(20, lookback))
    x_train = np.arange(size, dtype=float)
    slope, intercept = np.polyfit(x_train, train[-size:], deg=1)
    fitted_train = slope * x_train + intercept
    future_x = np.arange(size, size + len(future), dtype=float)
    future_trend = slope * future_x + intercept
    return train[-size:] - fitted_train, future - future_trend


def _metrics(actual: np.ndarray, forecast: np.ndarray, tolerance: int) -> dict[str, float]:
    correlation = _safe_correlation(actual, forecast)
    if len(actual) >= 2:
        actual_direction = np.sign(np.diff(actual))
        forecast_direction = np.sign(np.diff(forecast))
        directional = float(100.0 * np.mean(actual_direction == forecast_direction))
    else:
        directional = np.nan
    timing_error, within = _turn_metrics(actual, forecast, tolerance)
    return {
        "forecast_correlation": correlation,
        "directional_accuracy_pct": directional,
        "turning_point_error_bars": timing_error,
        "turns_within_tolerance_pct": within,
    }


def _training_metadata(metadata: DataMetadata, frame: pd.DataFrame) -> DataMetadata:
    return replace(
        metadata,
        start=pd.Timestamp(frame["timestamp"].iloc[0]),
        end=pd.Timestamp(frame["timestamp"].iloc[-1]),
        bars=len(frame),
    )


def walk_forward_validate(
    frame: pd.DataFrame,
    metadata: DataMetadata,
    settings: AnalysisSettings,
    horizon: int | None = None,
    tolerance: int = 5,
    max_splits: int = 8,
) -> ValidationResult:
    """Fit only on each training prefix and score its next unseen horizon."""
    forecast_horizon = int(horizon or settings.forecast_horizon)
    minimum_train = max(
        int(np.ceil(2.0 * settings.max_period)),
        settings.phase_window,
        min(settings.detection_window, max(len(frame) // 2, 64)),
    )
    latest_origin = len(frame) - forecast_horizon
    if latest_origin < minimum_train:
        raise ValueError(
            f"Walk-forward validation needs at least {minimum_train + forecast_horizon} bars for the current settings; "
            f"only {len(frame)} are available."
        )
    all_origins = np.arange(minimum_train, latest_origin + 1, forecast_horizon, dtype=int)
    if all_origins[-1] != latest_origin:
        all_origins = np.append(all_origins, latest_origin)
    if len(all_origins) > max_splits:
        positions = np.linspace(0, len(all_origins) - 1, max_splits, dtype=int)
        origins = np.unique(all_origins[positions])
    else:
        origins = all_origins

    rows: list[dict[str, object]] = []
    price_values = frame[settings.source].to_numpy(dtype=float)
    for origin_number, origin in enumerate(origins):
        train_frame = frame.iloc[:origin].copy().reset_index(drop=True)
        actual_prices = price_values[origin : origin + forecast_horizon]
        recent_residuals, actual_target = _linear_residual_target(
            price_values[:origin], actual_prices, settings.detrend_length
        )
        segment = "early" if origin_number < len(origins) / 3 else "middle" if origin_number < 2 * len(origins) / 3 else "recent"
        common = {
            "origin": pd.Timestamp(frame["timestamp"].iloc[origin - 1]),
            "test_end": pd.Timestamp(frame["timestamp"].iloc[origin + forecast_horizon - 1]),
            "historical_segment": segment,
            "train_bars": origin,
            "test_bars": forecast_horizon,
        }

        season = max(1, min(int(round(settings.min_period)), len(recent_residuals)))
        seasonal_forecast = np.resize(recent_residuals[-season:], forecast_horizon)
        rows.append({**common, "model": "Seasonal naive", **_metrics(actual_target, seasonal_forecast, tolerance)})

        for method in ("EMA", "HP"):
            for count in (1, 3, 5):
                model_settings = replace(
                    settings,
                    detrending_method=method,
                    num_cycles=count,
                    forecast_horizon=forecast_horizon,
                )
                try:
                    result = run_cycle_analysis(
                        train_frame, _training_metadata(metadata, train_frame), model_settings
                    )
                    forecast = result.composite.values.query("segment == 'forecast'")["composite"].to_numpy()[:forecast_horizon]
                    scores = _metrics(actual_target, forecast, tolerance)
                except ValueError:
                    scores = {
                        "forecast_correlation": np.nan,
                        "directional_accuracy_pct": np.nan,
                        "turning_point_error_bars": np.nan,
                        "turns_within_tolerance_pct": np.nan,
                    }
                rows.append({**common, "model": f"{method} · {count}-cycle", **scores})

    segments = pd.DataFrame(rows)
    metric_columns = [
        "forecast_correlation",
        "directional_accuracy_pct",
        "turning_point_error_bars",
        "turns_within_tolerance_pct",
    ]
    summary = segments.groupby("model", as_index=False)[metric_columns].mean(numeric_only=True)
    summary["segments_scored"] = segments.groupby("model")["forecast_correlation"].count().to_numpy()
    summary = summary.sort_values(["forecast_correlation", "directional_accuracy_pct"], ascending=False).reset_index(drop=True)
    return ValidationResult(summary=summary, segments=segments)

