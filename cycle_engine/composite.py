"""Latest-bar fixed harmonic superposition and turning-point projection."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .data_loader import future_timestamps
from .models import AnalysisSettings, CompositeResult, DataMetadata


def _phase_label_angle(value: float) -> float:
    return float(np.degrees(value % (2.0 * np.pi)))


def build_composite(
    detrended: pd.Series,
    timestamps: pd.Series,
    selected_cycles: pd.DataFrame,
    metadata: DataMetadata,
    settings: AnalysisSettings,
) -> tuple[CompositeResult, pd.DataFrame]:
    periods = selected_cycles["period"].to_numpy(dtype=float)
    if not len(periods):
        raise ValueError("No cycles passed the current selection thresholds.")
    values = np.asarray(detrended, dtype=float)
    n = len(values)
    fit_window = min(n, settings.phase_window)
    fit_times = np.arange(n - fit_window, n, dtype=float)
    columns = []
    for period in periods:
        omega = 2.0 * np.pi / period
        columns.extend((np.sin(omega * fit_times), np.cos(omega * fit_times)))
    design = np.column_stack(columns)
    coefficients, *_ = np.linalg.lstsq(design, values[-fit_window:], rcond=None)

    all_times = np.arange(n + settings.forecast_horizon, dtype=float)
    components: list[np.ndarray] = []
    component_rows: list[dict[str, float]] = []
    for position, period in enumerate(periods):
        sine = float(coefficients[position * 2])
        cosine = float(coefficients[position * 2 + 1])
        omega = 2.0 * np.pi / period
        component = sine * np.sin(omega * all_times) + cosine * np.cos(omega * all_times)
        components.append(component)
        amplitude = float(np.hypot(sine, cosine))
        phase_offset = float(np.arctan2(cosine, sine))
        current_phase = _phase_label_angle(omega * (n - 1) + phase_offset)
        component_rows.append(
            {
                "period": period,
                "fitted_amplitude": amplitude,
                "fitted_phase_offset": phase_offset,
                "current_phase_deg": current_phase,
            }
        )
    matrix = np.vstack(components)
    composite = matrix.sum(axis=0)
    future_index = future_timestamps(metadata, settings.forecast_horizon)
    combined_index = pd.DatetimeIndex(list(pd.to_datetime(timestamps)) + list(future_index))
    segments = np.where(np.arange(len(composite)) < n, "historical", "forecast")
    value_frame = pd.DataFrame(
        {"timestamp": combined_index, "composite": composite, "segment": segments, "bar": all_times.astype(int)}
    )

    min_distance = max(2, int(round(float(np.min(periods)) / 4.0)))
    scale = float(np.std(composite))
    prominence = max(scale * 0.08, np.finfo(float).eps)
    peak_positions, _ = find_peaks(composite, distance=min_distance, prominence=prominence)
    trough_positions, _ = find_peaks(-composite, distance=min_distance, prominence=prominence)

    def turn_frame(positions: np.ndarray, kind: str, future_only: bool = True) -> pd.DataFrame:
        selected_positions = positions[positions >= n] if future_only else positions[positions < n]
        return pd.DataFrame(
            {
                "timestamp": combined_index[selected_positions],
                "bar": selected_positions,
                "composite": composite[selected_positions],
                "type": kind,
            }
        )

    derivative = sum(
        (2.0 * np.pi / periods[i])
        * (float(coefficients[i * 2]) * np.cos(2.0 * np.pi * (n - 1) / periods[i])
           - float(coefficients[i * 2 + 1]) * np.sin(2.0 * np.pi * (n - 1) / periods[i]))
        for i in range(len(periods))
    )
    reference_omega = float(np.average(2.0 * np.pi / periods, weights=np.maximum(np.abs(matrix[:, n - 1]), 1e-9)))
    current_phase = _phase_label_angle(np.arctan2(composite[n - 1], derivative / max(reference_omega, 1e-9)))
    component_frame = pd.DataFrame(component_rows)
    updated_selected = selected_cycles.drop(columns=["current_phase_deg"], errors="ignore").merge(
        component_frame, on="period", how="left"
    )
    result = CompositeResult(
        values=value_frame,
        components=component_frame,
        peaks=turn_frame(peak_positions, "peak"),
        troughs=turn_frame(trough_positions, "trough"),
        historical_peaks=turn_frame(peak_positions, "peak", future_only=False),
        historical_troughs=turn_frame(trough_positions, "trough", future_only=False),
        current_phase_deg=current_phase,
    )
    return result, updated_selected


def phase_description(degrees: float) -> str:
    phase = degrees % 360.0
    if 45 <= phase < 135:
        return "near peak" if 75 <= phase <= 105 else "rising"
    if 135 <= phase < 225:
        return "falling through mid-cycle"
    if 225 <= phase < 315:
        return "near trough" if 255 <= phase <= 285 else "falling"
    return "rising through mid-cycle"


def projected_turns_table(result: CompositeResult, historical_bars: int) -> pd.DataFrame:
    """Return all projected peaks and troughs in chronological order."""
    turns = pd.concat([result.peaks, result.troughs], ignore_index=True)
    if turns.empty:
        return pd.DataFrame(columns=["date", "turn", "bars_ahead", "composite"])
    turns = turns.sort_values(["timestamp", "type"]).reset_index(drop=True)
    turns["bars_ahead"] = turns["bar"].astype(int) - (historical_bars - 1)
    turns["date"] = pd.to_datetime(turns["timestamp"])
    turns["turn"] = turns["type"].str.title()
    return turns[["date", "turn", "bars_ahead", "composite"]]
