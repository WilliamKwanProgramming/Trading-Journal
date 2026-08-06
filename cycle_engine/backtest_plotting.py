"""Plots used only by the Rolling Trade Backtest tab."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .rolling_backtest import RollingBacktestResult


GREEN = "#1e694f"
LIME = "#9bc447"
RED = "#bd5548"
INK = "#15211d"
MUTED = "#6d7d74"
GRID = "#dfe7df"


def _style(axis: plt.Axes) -> None:
    axis.grid(True, color=GRID, linewidth=0.7, alpha=0.65)
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(colors=MUTED, labelsize=8)


def backtest_equity_figure(result: RollingBacktestResult) -> plt.Figure:
    curve = result.equity_curve
    trades = result.trades
    figure, axes = plt.subplots(
        3, 1, figsize=(13, 9), sharex=True,
        gridspec_kw={"height_ratios": [1.7, 0.8, 0.8]},
    )
    equity_axis, cash_axis, drawdown_axis = axes
    equity_axis.plot(curve["date"], curve["equity"], color=GREEN, linewidth=1.6, label="Strategy equity")
    equity_axis.plot(curve["date"], curve["buy_and_hold_equity"], color=MUTED, linewidth=1.1, linestyle="--", label="Buy and hold")

    if not trades.empty:
        equity_lookup = curve.set_index("date")["equity"]
        for direction, color, marker, label in (
            ("Long", GREEN, "^", "Long entry / bullish state"),
            ("Short", RED, "v", "Short entry / bearish state"),
        ):
            selected = trades[trades["direction"] == direction]
            dates = pd.to_datetime(selected["entry_date"])
            values = equity_lookup.reindex(dates).to_numpy()
            equity_axis.scatter(dates, values, color=color, marker=marker, s=48, zorder=5, label=label)
            for date in dates:
                equity_axis.axvline(date, color=color, linewidth=0.55, alpha=0.25)
        exit_dates = pd.to_datetime(trades["exit_date"])
        exit_values = equity_lookup.reindex(exit_dates).to_numpy()
        equity_axis.scatter(exit_dates, exit_values, color=INK, marker="x", s=32, zorder=5, label="Exit")
        for date in exit_dates:
            equity_axis.axvline(date, color=INK, linewidth=0.45, alpha=0.18)

    equity_axis.set_ylabel("Equity")
    equity_axis.set_title("Rolling strategy equity versus buy and hold")
    equity_axis.legend(loc="upper left", frameon=False, ncol=2, fontsize=8)
    _style(equity_axis)

    cash_axis.plot(curve["date"], curve["cash"], color=INK, linewidth=1.1, label="Cash")
    cash_axis.plot(curve["date"], curve["equity"], color=GREEN, linewidth=0.9, alpha=0.7, label="Equity")
    cash_axis.set_ylabel("Cash / equity")
    cash_axis.legend(loc="upper left", frameon=False, ncol=2, fontsize=8)
    _style(cash_axis)

    drawdown = 100.0 * curve["drawdown"].to_numpy(dtype=float)
    drawdown_axis.fill_between(curve["date"], drawdown, 0, color=RED, alpha=0.28)
    drawdown_axis.plot(curve["date"], drawdown, color=RED, linewidth=0.9)
    drawdown_axis.set_ylabel("Drawdown %")
    drawdown_axis.set_title("Equity drawdown")
    drawdown_axis.xaxis.set_major_locator(mdates.AutoDateLocator())
    drawdown_axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(drawdown_axis.xaxis.get_major_locator()))
    _style(drawdown_axis)
    figure.tight_layout()
    return figure


def cycle_selection_heatmap(result: RollingBacktestResult) -> plt.Figure:
    signals = result.signals
    period_values = sorted(
        {round(float(period), 4) for periods in signals["selected_cycle_periods"] for period in periods}
    )
    figure, axis = plt.subplots(figsize=(13, max(4.2, 1.8 + len(period_values) * 0.18)))
    if not period_values:
        axis.text(0.5, 0.5, "No rolling dates produced eligible cycles.", ha="center", va="center", transform=axis.transAxes)
        axis.set_axis_off()
        return figure

    lookup = {period: row for row, period in enumerate(period_values)}
    matrix = np.zeros((len(period_values), len(signals)), dtype=float)
    for column, periods in enumerate(signals["selected_cycle_periods"]):
        for period in periods:
            matrix[lookup[round(float(period), 4)], column] = 1.0
    dates = mdates.date2num(pd.to_datetime(signals["date"]))
    left = dates[0] if len(dates) == 1 else dates[0] - (dates[1] - dates[0]) / 2
    right = dates[-1] if len(dates) == 1 else dates[-1] + (dates[-1] - dates[-2]) / 2
    axis.imshow(
        matrix,
        aspect="auto",
        interpolation="nearest",
        origin="lower",
        cmap=matplotlib.colors.ListedColormap(["#f4f7f2", GREEN]),
        extent=[left, right, -0.5, len(period_values) - 0.5],
        vmin=0,
        vmax=1,
    )
    max_labels = 18
    label_step = max(1, int(np.ceil(len(period_values) / max_labels)))
    ticks = np.arange(0, len(period_values), label_step)
    axis.set_yticks(ticks)
    axis.set_yticklabels([f"{period_values[index]:g}" for index in ticks])
    axis.set_ylabel("Selected period (bars)")
    axis.set_title("Rolling selected-cycle heatmap")
    axis.xaxis_date()
    axis.xaxis.set_major_locator(mdates.AutoDateLocator())
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(axis.xaxis.get_major_locator()))
    axis.tick_params(colors=MUTED, labelsize=8)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    return figure
