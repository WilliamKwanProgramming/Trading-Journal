"""Shared data models for the cycle-analysis engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class AnalysisSettings:
    source: str = "close"
    min_period: float = 30.0
    max_period: float = 200.0
    detection_window: int = 750
    detrending_method: str = "EMA"
    detrend_length: int = 400
    spectrum_method: str = "Harmonic DFT (baseline)"
    fractional_periods: bool = False
    fractional_step: float = 0.5
    num_cycles: int = 3
    phase_window: int = 250
    min_fit: float = 0.10
    min_stability: float = 0.35
    min_separation: float = 10.0
    bartels_enabled: bool = False
    bartels_threshold: float = 49.0
    forecast_horizon: int = 120

    def validate(self) -> None:
        if self.source not in {"open", "high", "low", "close"}:
            raise ValueError("Source must be close, open, high, or low.")
        if self.min_period < 4:
            raise ValueError("Minimum period must be at least 4 bars.")
        if self.max_period <= self.min_period:
            raise ValueError("Maximum period must be greater than minimum period.")
        if self.detection_window < 32:
            raise ValueError("Detection window must contain at least 32 bars.")
        if self.detrend_length < 3:
            raise ValueError("Detrending length must be at least 3 bars.")
        if self.num_cycles < 1:
            raise ValueError("At least one composite cycle is required.")
        if self.phase_window < 16:
            raise ValueError("Phase-estimation window must contain at least 16 bars.")
        if not 0 <= self.min_fit <= 1 or not 0 <= self.min_stability <= 1:
            raise ValueError("Fit and stability thresholds must be between 0 and 1.")
        if not 0 <= self.bartels_threshold <= 100:
            raise ValueError("Genuineness threshold must be between 0 and 100.")
        if self.forecast_horizon < 1:
            raise ValueError("Forecast horizon must be positive.")
        if self.fractional_periods and not 0.05 <= self.fractional_step <= 1:
            raise ValueError("Fractional period step must be between 0.05 and 1 bar.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataMetadata:
    file_name: str
    symbol: str
    start: pd.Timestamp
    end: pd.Timestamp
    bars: int
    timeframe: str
    median_interval: pd.Timedelta
    dropped_rows: int = 0
    duplicate_rows: int = 0
    warnings: tuple[str, ...] = ()


@dataclass
class CompositeResult:
    values: pd.DataFrame
    components: pd.DataFrame
    peaks: pd.DataFrame
    troughs: pd.DataFrame
    historical_peaks: pd.DataFrame
    historical_troughs: pd.DataFrame
    current_phase_deg: float


@dataclass
class AnalysisResult:
    settings: AnalysisSettings
    metadata: DataMetadata
    raw_data: pd.DataFrame
    trend: pd.Series
    detrended: pd.Series
    spectrum: pd.DataFrame
    selected_cycles: pd.DataFrame
    composite: CompositeResult
    as_of: pd.Timestamp
    created_at: datetime
    methodology_notes: tuple[str, ...]


@dataclass
class ValidationResult:
    summary: pd.DataFrame
    segments: pd.DataFrame
