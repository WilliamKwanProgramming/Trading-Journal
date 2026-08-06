"""Download serializers for cycle tables, charts, settings, and reports."""

from __future__ import annotations

from io import BytesIO
import json

import matplotlib.pyplot as plt
import pandas as pd

from .models import AnalysisResult


def selected_cycles_csv(result: AnalysisResult) -> bytes:
    return result.selected_cycles.to_csv(index=False).encode("utf-8")


def composite_csv(result: AnalysisResult) -> bytes:
    return result.composite.values.to_csv(index=False).encode("utf-8")


def settings_json(result: AnalysisResult) -> bytes:
    payload = {
        "as_of": result.as_of.isoformat(),
        "file_name": result.metadata.file_name,
        "settings": result.settings.to_dict(),
        "detected_cycle_periods": result.selected_cycles["period"].round(4).tolist(),
        "approximations": list(result.methodology_notes),
    }
    return json.dumps(payload, indent=2).encode("utf-8")


def pine_ready_settings(result: AnalysisResult) -> bytes:
    settings = result.settings
    periods = ", ".join(f"{period:g}" for period in result.selected_cycles["period"])
    text = f"""// Cycle Analysis Workbench settings
// Pine-ready values only; this is not a complete indicator.
minimum_cycle_length = {settings.min_period:g}
maximum_cycle_length = {settings.max_period:g}
detection_window = {settings.detection_window}
detrending_method = \"{settings.detrending_method}\"
detrending_length = {settings.detrend_length}
number_of_cycles = {settings.num_cycles}
phase_window = {settings.phase_window}
minimum_fit = {settings.min_fit:.4f}
minimum_stability = {settings.min_stability:.4f}
minimum_separation = {settings.min_separation:g}
bartels_enabled = {str(settings.bartels_enabled).lower()}
genuineness_threshold = {settings.bartels_threshold:.2f}
forecast_horizon = {settings.forecast_horizon}
detected_cycle_periods = [{periods}]
"""
    return text.encode("utf-8")


def figure_png(figure: plt.Figure) -> bytes:
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    return buffer.getvalue()


def markdown_report(result: AnalysisResult) -> bytes:
    settings_table = pd.DataFrame(
        [(key, value) for key, value in result.settings.to_dict().items()], columns=["Setting", "Value"]
    ).to_markdown(index=False)
    cycles = result.selected_cycles[
        ["selected_rank", "period", "fitted_amplitude", "fit", "stability", "bartels_genuineness", "strength", "current_phase_deg"]
    ].to_markdown(index=False, floatfmt=".4f")
    notes = "\n".join(f"- {note}" for note in result.methodology_notes)
    next_peak = "None within horizon" if result.composite.peaks.empty else str(result.composite.peaks["timestamp"].iloc[0])
    next_trough = "None within horizon" if result.composite.troughs.empty else str(result.composite.troughs["timestamp"].iloc[0])
    report = f"""# Cycle analysis report

- File: {result.metadata.file_name}
- Symbol: {result.metadata.symbol}
- Model as-of: {result.as_of}
- Data range: {result.metadata.start} to {result.metadata.end}
- Bars: {result.metadata.bars}
- Estimated timeframe: {result.metadata.timeframe}
- Next projected peak: {next_peak}
- Next projected trough: {next_trough}

## Selected cycles

{cycles}

## Settings

{settings_table}

## Method notes and approximations

{notes}

The composite is a detrended oscillator/scenario, not a price target. This implementation is inspired by the public FSC Cycle Scanner whitepaper and is not identical to Cycles.org or its proprietary code.
"""
    return report.encode("utf-8")

