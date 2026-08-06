"""Candidate-period scanning with harmonic DFT and Goertzel alternatives."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .bartels import bartels_style_genuineness
from .models import AnalysisSettings


def harmonic_fit(values: np.ndarray, times: np.ndarray, period: float) -> tuple[float, float, float, np.ndarray]:
    """Fit one sinusoid and return amplitude, phase offset, fit, component."""
    omega = 2.0 * np.pi / period
    design = np.column_stack((np.sin(omega * times), np.cos(omega * times), np.ones(len(times))))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    sine, cosine = coefficients[:2]
    component = design[:, :2] @ coefficients[:2]
    amplitude = float(np.hypot(sine, cosine))
    phase = float(np.arctan2(cosine, sine))
    if np.std(values) <= np.finfo(float).eps or np.std(component) <= np.finfo(float).eps:
        fit = 0.0
    else:
        fit = float(abs(np.corrcoef(values, component)[0, 1]))
    return amplitude, phase, fit, component


def goertzel_amplitude(values: np.ndarray, period: float) -> float:
    """Evaluate one arbitrary DFT frequency with the Goertzel recurrence."""
    centered = np.asarray(values, dtype=float) - float(np.mean(values))
    omega = 2.0 * np.pi / period
    coefficient = 2.0 * np.cos(omega)
    previous = 0.0
    previous_two = 0.0
    for sample in centered:
        state = sample + coefficient * previous - previous_two
        previous_two = previous
        previous = state
    power = previous_two**2 + previous**2 - coefficient * previous * previous_two
    return float(2.0 * np.sqrt(max(power, 0.0)) / max(len(centered), 1))


def _stability(values: np.ndarray, times: np.ndarray, period: float) -> float:
    n = len(values)
    window = min(n, max(int(np.ceil(2.0 * period)), n // 3))
    if window < 12 or n < window:
        return 0.0
    endpoints = np.unique(np.linspace(window, n, num=4, dtype=int))
    vectors: list[complex] = []
    for endpoint in endpoints:
        start = endpoint - window
        amplitude, phase, _, _ = harmonic_fit(values[start:endpoint], times[start:endpoint], period)
        vectors.append(amplitude * np.exp(1j * phase))
    if len(vectors) < 3:
        return 0.0
    vector_array = np.asarray(vectors)
    amplitudes = np.abs(vector_array)
    amplitude_cv = float(np.std(amplitudes) / max(np.mean(amplitudes), np.finfo(float).eps))
    amplitude_consistency = 1.0 / (1.0 + amplitude_cv)
    phase_coherence = float(np.abs(np.mean(np.exp(1j * np.angle(vector_array)))))
    return float(np.clip(0.5 * amplitude_consistency + 0.5 * phase_coherence, 0.0, 1.0))


def _period_grid(settings: AnalysisSettings) -> np.ndarray:
    step = settings.fractional_step if settings.fractional_periods else 1.0
    count = int(np.floor((settings.max_period - settings.min_period) / step)) + 1
    periods = settings.min_period + np.arange(count, dtype=float) * step
    if periods[-1] < settings.max_period - step * 0.25:
        periods = np.append(periods, settings.max_period)
    return periods


def scan_spectrum(detrended: pd.Series, settings: AnalysisSettings) -> pd.DataFrame:
    """Inspect every candidate period on the latest detection window."""
    full = np.asarray(detrended, dtype=float)
    window_size = min(len(full), settings.detection_window)
    values = full[-window_size:]
    times = np.arange(len(full) - window_size, len(full), dtype=float)
    phase_size = min(len(full), settings.phase_window)
    recent_values = full[-phase_size:]
    recent_times = np.arange(len(full) - phase_size, len(full), dtype=float)

    rows: list[dict[str, float]] = []
    use_goertzel = settings.spectrum_method.lower().startswith("goertzel")
    for period in _period_grid(settings):
        harmonic_amplitude, _, fit, _ = harmonic_fit(values, times, float(period))
        spectral_amplitude = goertzel_amplitude(values, float(period)) if use_goertzel else harmonic_amplitude
        current_amplitude, current_offset, _, _ = harmonic_fit(recent_values, recent_times, float(period))
        current_phase = (2.0 * np.pi * (len(full) - 1) / period + current_offset) % (2.0 * np.pi)
        stability = _stability(values, times, float(period))
        genuineness, chance_probability = bartels_style_genuineness(values, float(period))
        rows.append(
            {
                "period": float(period),
                "amplitude": current_amplitude,
                "spectral_amplitude": spectral_amplitude,
                "fit": fit,
                "phase_offset": current_offset,
                "current_phase_deg": float(np.degrees(current_phase)),
                "stability": stability,
                "bartels_genuineness": genuineness,
                "bartels_chance_probability": chance_probability,
                "strength": spectral_amplitude / float(period),
            }
        )
    spectrum = pd.DataFrame(rows)
    strength_rank = spectrum["strength"].rank(pct=True)
    fit_rank = spectrum["fit"].rank(pct=True)
    stability_rank = spectrum["stability"].rank(pct=True)
    spectrum["rank_score"] = 0.50 * strength_rank + 0.30 * fit_rank + 0.20 * stability_rank
    return spectrum

