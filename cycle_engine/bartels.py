"""A documented Bartels-style persistence approximation.

The FSC whitepaper states that its implementation is a more sophisticated
Bartels test but does not publish the complete formula.  This module therefore
uses cycle-by-cycle harmonic vectors, Rayleigh phase coherence, and amplitude
consistency.  It is intentionally labelled an approximation in the UI.
"""

from __future__ import annotations

import numpy as np


def _harmonic_vector(values: np.ndarray, times: np.ndarray, period: float) -> complex:
    omega = 2.0 * np.pi / period
    design = np.column_stack((np.sin(omega * times), np.cos(omega * times), np.ones(len(times))))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    sine, cosine = coefficients[:2]
    amplitude = float(np.hypot(sine, cosine))
    phase = float(np.arctan2(cosine, sine))
    return amplitude * np.exp(1j * phase)


def bartels_style_genuineness(values: np.ndarray, period: float) -> tuple[float, float]:
    """Return (genuineness percent, approximate chance probability)."""
    y = np.asarray(values, dtype=float)
    segment_length = max(4, int(round(period)))
    segments = len(y) // segment_length
    if segments < 3:
        return 0.0, 1.0
    y = y[-segments * segment_length :]
    offset = len(values) - len(y)
    vectors = []
    for segment in range(segments):
        start = segment * segment_length
        stop = start + segment_length
        times = np.arange(offset + start, offset + stop, dtype=float)
        vectors.append(_harmonic_vector(y[start:stop], times, period))
    vector_array = np.asarray(vectors, dtype=complex)
    amplitudes = np.abs(vector_array)
    total_amplitude = float(amplitudes.sum())
    if total_amplitude <= np.finfo(float).eps:
        return 0.0, 1.0
    coherence = float(np.abs(vector_array.sum()) / total_amplitude)
    rayleigh_z = segments * coherence**2
    chance_probability = float(np.clip(np.exp(-rayleigh_z), 0.0, 1.0))
    amplitude_cv = float(np.std(amplitudes) / max(np.mean(amplitudes), np.finfo(float).eps))
    amplitude_consistency = 1.0 / (1.0 + amplitude_cv)
    genuineness = 100.0 * (1.0 - chance_probability) * np.sqrt(amplitude_consistency)
    return float(np.clip(genuineness, 0.0, 100.0)), chance_probability
