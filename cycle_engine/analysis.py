"""High-level orchestration for final-bar and locked cycle models."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd

from .composite import build_composite
from .cycle_selection import select_cycles
from .data_loader import require_history
from .detrending import detrend
from .models import AnalysisResult, AnalysisSettings, DataMetadata
from .spectrum import scan_spectrum


class AnalysisError(ValueError):
    """Readable cycle-analysis failure."""


METHODOLOGY_NOTES = (
    "Harmonic regression and Goertzel both evaluate one DFT frequency at a time; least-squares normalization makes the baseline more stable for non-bin periods.",
    "The HP cutoff-to-lambda mapping is a public frequency-response approximation; the whitepaper does not publish its tuned lambda.",
    "Bartels-style genuineness uses phase coherence and amplitude persistence across full-cycle blocks; it is not the proprietary FSC test.",
    "All historical and forecast composite values use one coefficient set fitted at the model as-of bar.",
)


def _metadata_for_slice(metadata: DataMetadata, frame: pd.DataFrame) -> DataMetadata:
    return replace(
        metadata,
        start=pd.Timestamp(frame["timestamp"].iloc[0]),
        end=pd.Timestamp(frame["timestamp"].iloc[-1]),
        bars=len(frame),
    )


def run_cycle_analysis(
    frame: pd.DataFrame,
    metadata: DataMetadata,
    settings: AnalysisSettings,
) -> AnalysisResult:
    settings.validate()
    require_history(frame, settings.max_period)
    price = pd.Series(frame[settings.source].to_numpy(dtype=float), name=settings.source)
    cyclical, trend = detrend(price, settings.detrending_method, settings.detrend_length)
    spectrum = scan_spectrum(cyclical, settings)
    ranked_spectrum, selected = select_cycles(spectrum, settings)
    if selected.empty:
        raise AnalysisError(
            "No cycles passed the current fit, stability, separation, and genuineness rules. "
            "Lower a threshold, disable the Bartels-style filter, or widen the period range."
        )
    composite, selected = build_composite(
        cyclical, frame["timestamp"], selected, metadata, settings
    )
    return AnalysisResult(
        settings=settings,
        metadata=metadata,
        raw_data=frame.reset_index(drop=True).copy(),
        trend=trend,
        detrended=cyclical,
        spectrum=ranked_spectrum,
        selected_cycles=selected,
        composite=composite,
        as_of=pd.Timestamp(frame["timestamp"].iloc[-1]),
        created_at=datetime.now(timezone.utc),
        methodology_notes=METHODOLOGY_NOTES,
    )


def run_locked_analysis(
    frame: pd.DataFrame,
    metadata: DataMetadata,
    settings: AnalysisSettings,
    as_of: pd.Timestamp | str,
) -> AnalysisResult:
    cutoff = pd.Timestamp(as_of)
    locked = frame[pd.to_datetime(frame["timestamp"]) <= cutoff].copy().reset_index(drop=True)
    if locked.empty:
        raise AnalysisError("The locked as-of date is earlier than the first valid CSV row.")
    return run_cycle_analysis(locked, _metadata_for_slice(metadata, locked), settings)
