"""Matplotlib views used by both Streamlit and downloadable reports."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .models import AnalysisResult, ValidationResult


GREEN = "#1e694f"
LIME = "#9bc447"
RED = "#bd5548"
INK = "#15211d"
MUTED = "#6d7d74"
GRID = "#dfe7df"


def _finish_axis(axis: plt.Axes) -> None:
    axis.grid(True, color=GRID, linewidth=0.7, alpha=0.65)
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(colors=MUTED, labelsize=8)
    axis.title.set_color(INK)


def composite_figure(result: AnalysisResult, actual_data: pd.DataFrame | None = None) -> plt.Figure:
    figure, (price_axis, cycle_axis) = plt.subplots(
        2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [1.15, 1]}
    )
    raw = result.raw_data
    price_axis.plot(raw["timestamp"], raw[result.settings.source], color=INK, linewidth=1.15, label=result.settings.source.title())
    if actual_data is not None and len(actual_data):
        later = actual_data[pd.to_datetime(actual_data["timestamp"]) > result.as_of]
        if len(later):
            bridge = pd.concat([raw.tail(1), later], ignore_index=True)
            price_axis.plot(
                bridge["timestamp"], bridge[result.settings.source], color=MUTED, linewidth=1.1,
                linestyle="--", label="Observed after lock"
            )
    price_axis.axvline(result.as_of, color=RED, linewidth=1.1, linestyle=":", label="Model as-of")
    all_peaks = pd.concat(
        [result.composite.historical_peaks, result.composite.peaks], ignore_index=True
    )
    all_troughs = pd.concat(
        [result.composite.historical_troughs, result.composite.troughs], ignore_index=True
    )
    for position, timestamp in enumerate(all_peaks["timestamp"]):
        price_axis.axvline(
            timestamp, color=GREEN, linewidth=0.9, linestyle="--", alpha=0.65,
            label="Peak" if position == 0 else None,
        )
    for position, timestamp in enumerate(all_troughs["timestamp"]):
        price_axis.axvline(
            timestamp, color=RED, linewidth=0.9, linestyle="--", alpha=0.65,
            label="Trough" if position == 0 else None,
        )
    price_axis.set_ylabel("Price")
    price_axis.set_title("Uploaded price series")
    price_axis.legend(loc="upper left", frameon=False, fontsize=8)
    _finish_axis(price_axis)

    values = result.composite.values
    historical = values[values["segment"] == "historical"]
    forecast = values[values["segment"] == "forecast"]
    cycle_axis.plot(historical["timestamp"], historical["composite"], color=GREEN, linewidth=1.35, label="Fixed historical composite")
    if len(forecast):
        bridge = pd.concat([historical.tail(1), forecast], ignore_index=True)
        cycle_axis.plot(bridge["timestamp"], bridge["composite"], color=LIME, linewidth=1.8, linestyle="--", label="Fixed projection")
    if len(result.composite.peaks):
        cycle_axis.scatter(result.composite.peaks["timestamp"], result.composite.peaks["composite"], marker="^", color=GREEN, s=45, label="Projected peaks", zorder=5)
    if len(result.composite.troughs):
        cycle_axis.scatter(result.composite.troughs["timestamp"], result.composite.troughs["composite"], marker="v", color=RED, s=45, label="Projected troughs", zorder=5)
    cycle_axis.axhline(0, color=GRID, linewidth=1)
    cycle_axis.axvline(result.as_of, color=RED, linewidth=1.1, linestyle=":")
    for timestamp in all_peaks["timestamp"]:
        cycle_axis.axvline(timestamp, color=GREEN, linewidth=0.9, linestyle="--", alpha=0.65)
    for timestamp in all_troughs["timestamp"]:
        cycle_axis.axvline(timestamp, color=RED, linewidth=0.9, linestyle="--", alpha=0.65)
    cycle_axis.set_ylabel("Detrended oscillator")
    cycle_axis.set_title("Composite oscillator/scenario — not a price target")
    cycle_axis.legend(loc="upper left", frameon=False, ncol=2, fontsize=8)
    cycle_axis.xaxis.set_major_locator(mdates.AutoDateLocator())
    cycle_axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(cycle_axis.xaxis.get_major_locator()))
    _finish_axis(cycle_axis)
    figure.tight_layout()
    return figure


def spectrum_figure(result: AnalysisResult) -> plt.Figure:
    table = result.spectrum.sort_values("period")
    figure, axis = plt.subplots(figsize=(13, 5.5))
    metrics = {
        "Amplitude (normalized)": table["spectral_amplitude"] / max(float(table["spectral_amplitude"].max()), 1e-12),
        "Fit / correlation": table["fit"],
        "Strength (normalized)": table["strength"] / max(float(table["strength"].max()), 1e-12),
        "Stability": table["stability"],
    }
    colors = [INK, GREEN, LIME, "#718ea4"]
    for (label, values), color in zip(metrics.items(), colors):
        axis.plot(table["period"], values, label=label, color=color, linewidth=1.25)
    selected = table[table["selected"]]
    if len(selected):
        selected_strength = selected["strength"] / max(float(table["strength"].max()), 1e-12)
        axis.scatter(selected["period"], selected_strength, color=RED, s=55, zorder=6, label="Selected")
        for _, row in selected.iterrows():
            axis.axvline(row["period"], color=RED, linewidth=0.65, alpha=0.4)
    axis.set_xlabel("Candidate period (bars)")
    axis.set_ylabel("Normalized spectrum metrics")
    axis.set_ylim(bottom=0)
    axis.set_title(f"Cycle spectrum · {result.settings.spectrum_method}")
    axis.legend(loc="upper right", frameon=False, ncol=2, fontsize=8)
    _finish_axis(axis)
    figure.tight_layout()
    return figure


def validation_figure(validation: ValidationResult) -> plt.Figure:
    table = validation.summary.sort_values("forecast_correlation", ascending=True)
    figure, axes = plt.subplots(1, 2, figsize=(13, max(4.5, len(table) * 0.55)))
    axes[0].barh(table["model"], table["forecast_correlation"], color=GREEN)
    axes[0].axvline(0, color=GRID, linewidth=1)
    axes[0].set_title("Mean forecast correlation")
    axes[0].set_xlabel("Correlation")
    axes[1].barh(table["model"], table["directional_accuracy_pct"], color=LIME)
    axes[1].axvline(50, color=RED, linewidth=1, linestyle=":")
    axes[1].set_title("Mean directional accuracy")
    axes[1].set_xlabel("Percent")
    for axis in axes:
        _finish_axis(axis)
    figure.tight_layout()
    return figure
