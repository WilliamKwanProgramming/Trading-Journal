"""Thresholding, separation, and ranking of scanned cycles."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .models import AnalysisSettings


def select_cycles(spectrum: pd.DataFrame, settings: AnalysisSettings) -> tuple[pd.DataFrame, pd.DataFrame]:
    table = spectrum.copy()
    eligible = (table["fit"] >= settings.min_fit) & (table["stability"] >= settings.min_stability)
    if settings.bartels_enabled:
        eligible &= table["bartels_genuineness"] >= settings.bartels_threshold
    table["eligible"] = eligible

    # Favor actual spectral/rank peaks over shoulders. Boundaries remain eligible.
    peak_indices, _ = find_peaks(table["rank_score"].to_numpy())
    peak_mask = np.zeros(len(table), dtype=bool)
    peak_mask[peak_indices] = True
    if len(table):
        peak_mask[0] = table["rank_score"].iloc[0] >= table["rank_score"].iloc[min(1, len(table) - 1)]
        peak_mask[-1] = table["rank_score"].iloc[-1] >= table["rank_score"].iloc[max(0, len(table) - 2)]
    candidates = table[eligible & peak_mask].sort_values(
        ["rank_score", "strength", "fit"], ascending=False
    )
    # If thresholds leave too few local maxima, use eligible candidates as a transparent fallback.
    if len(candidates) < settings.num_cycles:
        candidates = table[eligible].sort_values(["rank_score", "strength", "fit"], ascending=False)

    selected_indices: list[int] = []
    selected_periods: list[float] = []
    for index, row in candidates.iterrows():
        period = float(row["period"])
        if any(abs(period - existing) < settings.min_separation for existing in selected_periods):
            continue
        selected_indices.append(index)
        selected_periods.append(period)
        if len(selected_indices) >= settings.num_cycles:
            break

    table["selected"] = False
    if selected_indices:
        table.loc[selected_indices, "selected"] = True
    ordering = table.sort_values(["rank_score", "strength"], ascending=False).index
    rank_map = {index: rank for rank, index in enumerate(ordering, start=1)}
    table["rank"] = table.index.map(rank_map).astype(int)
    selected = table.loc[selected_indices].copy() if selected_indices else table.iloc[0:0].copy()
    if not selected.empty:
        selected = selected.sort_values("rank_score", ascending=False).reset_index(drop=True)
        selected["selected_rank"] = np.arange(1, len(selected) + 1)
    return table, selected

