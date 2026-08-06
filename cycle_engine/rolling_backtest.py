"""Strictly rolling, prefix-only trade simulation for the cycle dashboard.

This module consumes the public cycle-engine API but does not alter it. Every
model is fitted to a fresh historical prefix ending at the signal date.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .analysis import AnalysisError, run_cycle_analysis
from .models import AnalysisSettings, DataMetadata


@dataclass(frozen=True)
class BacktestSettings:
    initial_capital: float = 100_000.0
    position_size_pct: float = 100.0
    allow_shorting: bool = True
    commission_per_order: float = 0.0
    slippage_pct: float = 0.0
    leverage: float = 1.0
    execution_timing: str = "Next bar open"
    signal_mode: str = "Bullish / bearish projected state"
    one_bar_confirmation: bool = False
    turn_tolerance_bars: int = 3

    def validate(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("Initial capital must be positive.")
        if not 0 < self.position_size_pct <= 100:
            raise ValueError("Position size must be greater than 0% and no more than 100%.")
        if self.commission_per_order < 0 or self.slippage_pct < 0:
            raise ValueError("Commission and slippage cannot be negative.")
        if self.leverage < 1:
            raise ValueError("Leverage must be at least 1x.")
        if self.execution_timing not in {"Next bar open", "Next bar close"}:
            raise ValueError("Execution timing must be next-bar open or next-bar close.")
        if self.signal_mode not in {
            "Bullish / bearish projected state",
            "Exact projected turn (legacy)",
        }:
            raise ValueError("Unknown rolling signal mode.")
        if self.turn_tolerance_bars < 0:
            raise ValueError("Turn tolerance cannot be negative.")


@dataclass
class RollingBacktestResult:
    signals: pd.DataFrame
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    summary: dict[str, Any]
    cycle_diagnostics: dict[str, Any]
    turn_diagnostics: pd.DataFrame
    earliest_start_date: pd.Timestamp
    requested_start_date: pd.Timestamp
    analysis_settings: AnalysisSettings
    backtest_settings: BacktestSettings


TRADE_COLUMNS = [
    "trade_number", "direction", "signal_date", "entry_date", "entry_price",
    "exit_signal_date", "exit_date", "exit_price", "holding_period_bars",
    "gross_pnl", "fees_slippage", "net_pnl", "return_pct",
    "entry_signal_type", "exit_signal_type", "selected_cycles_at_entry",
    "selected_cycles_at_exit",
]


def minimum_backtest_bars(settings: AnalysisSettings) -> int:
    """Bars needed before a rolling fit can use every configured window fully."""
    return max(
        64,
        int(np.ceil(2.0 * settings.max_period)),
        int(settings.detection_window),
        int(settings.detrend_length),
        int(settings.phase_window),
    )


def earliest_backtest_date(frame: pd.DataFrame, settings: AnalysisSettings) -> pd.Timestamp:
    required = minimum_backtest_bars(settings)
    if len(frame) < required:
        raise ValueError(
            f"Rolling backtest unavailable: the current configuration needs {required} valid bars "
            f"before its first fit, but the CSV contains {len(frame)}. Upload more history or reduce "
            "the relevant analysis windows."
        )
    return pd.Timestamp(frame["timestamp"].iloc[required - 1])


def resolve_start_index(
    frame: pd.DataFrame,
    settings: AnalysisSettings,
    requested_start: pd.Timestamp | str,
) -> int:
    earliest = earliest_backtest_date(frame, settings)
    requested = pd.Timestamp(requested_start)
    if requested < earliest:
        raise ValueError(
            f"The selected start date {requested.date()} is too early. The earliest valid date for "
            f"the current configuration is {earliest.date()} ({minimum_backtest_bars(settings)} bars)."
        )
    candidates = np.flatnonzero(pd.to_datetime(frame["timestamp"]).to_numpy() >= requested.to_datetime64())
    if not len(candidates):
        raise ValueError("The selected start date is later than the final CSV date.")
    return int(candidates[0])


def _prefix_metadata(metadata: DataMetadata, prefix: pd.DataFrame) -> DataMetadata:
    return replace(
        metadata,
        start=pd.Timestamp(prefix["timestamp"].iloc[0]),
        end=pd.Timestamp(prefix["timestamp"].iloc[-1]),
        bars=len(prefix),
    )


def _raw_turn_signal(previous: float, current: float, next_value: float) -> str:
    if previous < current and next_value <= current:
        return "Peak"
    if previous > current and next_value >= current:
        return "Trough"
    return "None"


def _projected_cycle_state(current: float, next_value: float) -> str:
    projected_slope = next_value - current
    if projected_slope > 0:
        return "Bullish"
    if projected_slope < 0:
        return "Bearish"
    return "Neutral"


def generate_rolling_signals(
    frame: pd.DataFrame,
    metadata: DataMetadata,
    settings: AnalysisSettings,
    start_index: int,
    one_bar_confirmation: bool = False,
    signal_mode: str = "Bullish / bearish projected state",
) -> pd.DataFrame:
    """Recalculate the complete existing model on each available prefix."""
    rows: list[dict[str, Any]] = []
    pending_confirmation = "None"
    active_state = "Neutral"
    pending_state = "Neutral"
    pending_state_count = 0
    for index in range(start_index, len(frame)):
        prefix = frame.iloc[: index + 1].copy().reset_index(drop=True)
        try:
            model = run_cycle_analysis(prefix, _prefix_metadata(metadata, prefix), settings)
            historical = model.composite.values[model.composite.values["segment"] == "historical"]
            forecast = model.composite.values[model.composite.values["segment"] == "forecast"]
            if len(historical) < 2 or forecast.empty:
                raise AnalysisError("The rolling model did not produce adjacent composite values.")
            previous = float(historical["composite"].iloc[-2])
            current = float(historical["composite"].iloc[-1])
            next_value = float(forecast["composite"].iloc[0])
            projected_slope = next_value - current
            cycle_state = _projected_cycle_state(current, next_value)
            if signal_mode == "Bullish / bearish projected state":
                raw_signal = cycle_state
                signal = "None"
                if one_bar_confirmation:
                    if cycle_state in {"Bullish", "Bearish"} and cycle_state != active_state:
                        if cycle_state == pending_state:
                            pending_state_count += 1
                        else:
                            pending_state = cycle_state
                            pending_state_count = 1
                        if pending_state_count >= 2:
                            signal = cycle_state
                            active_state = cycle_state
                            pending_state = "Neutral"
                            pending_state_count = 0
                    else:
                        pending_state = "Neutral"
                        pending_state_count = 0
                elif cycle_state in {"Bullish", "Bearish"} and cycle_state != active_state:
                    signal = cycle_state
                    active_state = cycle_state
            else:
                raw_signal = _raw_turn_signal(previous, current, next_value)
                signal = raw_signal
                if one_bar_confirmation:
                    signal = "None"
                    if pending_confirmation == "Peak" and current <= previous:
                        signal = "Peak"
                    elif pending_confirmation == "Trough" and current >= previous:
                        signal = "Trough"
                    pending_confirmation = raw_signal
            selected = model.selected_cycles.sort_values("selected_rank")
            periods = tuple(float(value) for value in selected["period"])
            amplitudes = tuple(float(value) for value in selected["fitted_amplitude"])
            fits = tuple(float(value) for value in selected["fit"])
            stabilities = tuple(float(value) for value in selected["stability"])
            model_valid = True
            model_message = ""
        except (AnalysisError, ValueError, np.linalg.LinAlgError) as exc:
            previous = current = next_value = np.nan
            projected_slope = np.nan
            cycle_state = "Unavailable"
            raw_signal = signal = "None"
            periods = amplitudes = fits = stabilities = ()
            model_valid = False
            model_message = str(exc)
            pending_confirmation = "None"
            pending_state = "Neutral"
            pending_state_count = 0

        # Legacy exact-turn mode preserves the original wait-for-a-turn behavior.
        # State mode remains flat on this row but may schedule its first next-bar order.
        if index == start_index and signal_mode == "Exact projected turn (legacy)":
            signal = "None"
        rows.append(
            {
                "date": pd.Timestamp(frame["timestamp"].iloc[index]),
                "bar_index": index,
                "close": float(frame["close"].iloc[index]),
                "composite": current,
                "previous_composite": previous,
                "next_projected_composite": next_value,
                "projected_slope": projected_slope,
                "cycle_state": cycle_state,
                "raw_signal": raw_signal,
                "signal": signal,
                "selected_cycle_periods": periods,
                "cycle_amplitudes": amplitudes,
                "fit_correlations": fits,
                "stabilities": stabilities,
                "model_valid": model_valid,
                "model_message": model_message,
            }
        )
    return pd.DataFrame(rows)


def _position_name(direction: int) -> str:
    return "Long" if direction > 0 else "Short" if direction < 0 else "Flat"


def _signal_target(signal: str, allow_shorting: bool, current_direction: int) -> int:
    if signal in {"Trough", "Bullish"}:
        return 1
    if signal in {"Peak", "Bearish"}:
        return -1 if allow_shorting else 0
    return current_direction


def _longest_streak(values: pd.Series, winning: bool) -> int:
    longest = current = 0
    for value in values.fillna(0.0):
        matches = value > 0 if winning else value < 0
        current = current + 1 if matches else 0
        longest = max(longest, current)
    return longest


def simulate_trades(
    frame: pd.DataFrame,
    signals: pd.DataFrame,
    settings: BacktestSettings,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Execute signals sequentially, with signals generated before the next bar."""
    settings.validate()
    if signals.empty:
        raise ValueError("No rolling signal dates are available for simulation.")
    start_index = int(signals["bar_index"].iloc[0])
    signal_by_index = {int(row.bar_index): row for row in signals.itertuples(index=False)}
    cash = float(settings.initial_capital)
    direction = 0
    quantity = 0.0
    open_trade: dict[str, Any] | None = None
    pending_signal: Any | None = None
    trades: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    fallback_executions = 0
    bars_in_market = 0

    def raw_execution_price(index: int) -> tuple[float, str]:
        nonlocal fallback_executions
        if settings.execution_timing == "Next bar open":
            value = frame["open"].iloc[index]
            if pd.notna(value) and np.isfinite(float(value)):
                return float(value), "open"
            fallback_executions += 1
            return float(frame["close"].iloc[index]), "close fallback"
        return float(frame["close"].iloc[index]), "close"

    def close_position(index: int, raw_price: float, exit_signal: Any, exit_type: str) -> None:
        nonlocal cash, direction, quantity, open_trade
        if direction == 0 or open_trade is None:
            return
        slippage = settings.slippage_pct / 100.0
        fill = raw_price * (1.0 - slippage if direction > 0 else 1.0 + slippage)
        commission = settings.commission_per_order
        if direction > 0:
            cash += quantity * fill - commission
        else:
            cash -= quantity * fill + commission
        gross = direction * (raw_price - open_trade["entry_raw_price"]) * quantity
        exit_slippage = abs(fill - raw_price) * quantity
        total_costs = open_trade["entry_commission"] + commission + open_trade["entry_slippage"] + exit_slippage
        net = direction * (fill - open_trade["entry_fill_price"]) * quantity - open_trade["entry_commission"] - commission
        entry_notional = open_trade["entry_fill_price"] * quantity
        trades.append(
            {
                "trade_number": len(trades) + 1,
                "direction": _position_name(direction),
                "signal_date": open_trade["signal_date"],
                "entry_date": pd.Timestamp(frame["timestamp"].iloc[open_trade["entry_index"]]),
                "entry_price": open_trade["entry_fill_price"],
                "exit_signal_date": pd.Timestamp(exit_signal.date) if exit_signal is not None else pd.Timestamp(frame["timestamp"].iloc[index]),
                "exit_date": pd.Timestamp(frame["timestamp"].iloc[index]),
                "exit_price": fill,
                "holding_period_bars": index - open_trade["entry_index"],
                "gross_pnl": gross,
                "fees_slippage": total_costs,
                "net_pnl": net,
                "return_pct": 100.0 * net / entry_notional if entry_notional else np.nan,
                "entry_signal_type": open_trade["entry_signal_type"],
                "exit_signal_type": exit_type,
                "selected_cycles_at_entry": open_trade["selected_cycles"],
                "selected_cycles_at_exit": tuple(exit_signal.selected_cycle_periods) if exit_signal is not None else (),
            }
        )
        direction = 0
        quantity = 0.0
        open_trade = None

    def open_position(index: int, target: int, raw_price: float, entry_signal: Any) -> None:
        nonlocal cash, direction, quantity, open_trade
        if target == 0 or cash <= 0:
            return
        slippage = settings.slippage_pct / 100.0
        fill = raw_price * (1.0 + slippage if target > 0 else 1.0 - slippage)
        notional = cash * (settings.position_size_pct / 100.0) * settings.leverage
        quantity = notional / fill if fill > 0 else 0.0
        if quantity <= 0:
            return
        commission = settings.commission_per_order
        if target > 0:
            cash -= quantity * fill + commission
        else:
            cash += quantity * fill - commission
        direction = target
        open_trade = {
            "signal_date": pd.Timestamp(entry_signal.date),
            "entry_index": index,
            "entry_raw_price": raw_price,
            "entry_fill_price": fill,
            "entry_commission": commission,
            "entry_slippage": abs(fill - raw_price) * quantity,
            "entry_signal_type": str(entry_signal.signal),
            "selected_cycles": tuple(entry_signal.selected_cycle_periods),
        }

    for index in range(start_index, len(frame)):
        row = signal_by_index[index]
        if pending_signal is not None:
            target = _signal_target(str(pending_signal.signal), settings.allow_shorting, direction)
            if target != direction:
                execution_price, _ = raw_execution_price(index)
                close_position(index, execution_price, pending_signal, str(pending_signal.signal))
                open_position(index, target, execution_price, pending_signal)
            pending_signal = None

        had_position = direction != 0
        if had_position:
            bars_in_market += 1

        if index == len(frame) - 1 and direction != 0:
            close_position(index, float(frame["close"].iloc[index]), row, "end of data")

        close = float(frame["close"].iloc[index])
        position_value = direction * quantity * close
        equity = cash + position_value
        unrealized = direction * (close - open_trade["entry_fill_price"]) * quantity if open_trade is not None else 0.0
        target_after_signal = _signal_target(str(row.signal), settings.allow_shorting, direction)
        daily.append(
            {
                "date": pd.Timestamp(frame["timestamp"].iloc[index]),
                "bar_index": index,
                "cash": cash,
                "position_value": position_value,
                "realized_pnl": float(sum(trade["net_pnl"] for trade in trades)),
                "unrealized_pnl": unrealized,
                "equity": equity,
                "position": _position_name(direction),
                "position_after_signal": _position_name(target_after_signal),
            }
        )
        if index < len(frame) - 1 and str(row.signal) in {"Peak", "Trough", "Bullish", "Bearish"}:
            pending_signal = row

    trade_frame = pd.DataFrame(trades, columns=TRADE_COLUMNS)
    equity_curve = pd.DataFrame(daily)
    close_series = frame.loc[start_index:, "close"].to_numpy(dtype=float)
    equity_curve["buy_and_hold_equity"] = settings.initial_capital * close_series / close_series[0]
    equity_curve["drawdown"] = equity_curve["equity"] / equity_curve["equity"].cummax() - 1.0

    net_values = trade_frame["net_pnl"] if not trade_frame.empty else pd.Series(dtype=float)
    winners = net_values[net_values > 0]
    losers = net_values[net_values < 0]
    initial = settings.initial_capital
    final = float(equity_curve["equity"].iloc[-1])
    elapsed_days = (equity_curve["date"].iloc[-1] - equity_curve["date"].iloc[0]).days
    years = elapsed_days / 365.25
    annualized = (final / initial) ** (1.0 / years) - 1.0 if years >= 0.25 and final > 0 else np.nan
    gross_profit = float(winners.sum())
    gross_loss = float(-losers.sum())
    summary = {
        "initial_capital": initial,
        "final_equity": final,
        "net_profit": final - initial,
        "total_return_pct": 100.0 * (final / initial - 1.0),
        "annualized_return_pct": 100.0 * annualized if np.isfinite(annualized) else np.nan,
        "maximum_drawdown_pct": 100.0 * float(equity_curve["drawdown"].min()),
        "completed_trades": len(trade_frame),
        "long_trades": int((trade_frame["direction"] == "Long").sum()) if not trade_frame.empty else 0,
        "short_trades": int((trade_frame["direction"] == "Short").sum()) if not trade_frame.empty else 0,
        "win_rate_pct": 100.0 * len(winners) / len(trade_frame) if len(trade_frame) else np.nan,
        "average_winner": float(winners.mean()) if len(winners) else np.nan,
        "average_loser": float(losers.mean()) if len(losers) else np.nan,
        "profit_factor": gross_profit / gross_loss if gross_loss else (np.inf if gross_profit else np.nan),
        "expectancy_per_trade": float(net_values.mean()) if len(net_values) else np.nan,
        "long_only_net_pnl": float(trade_frame.loc[trade_frame["direction"] == "Long", "net_pnl"].sum()) if not trade_frame.empty else 0.0,
        "short_only_net_pnl": float(trade_frame.loc[trade_frame["direction"] == "Short", "net_pnl"].sum()) if not trade_frame.empty else 0.0,
        "buy_and_hold_return_pct": 100.0 * (float(equity_curve["buy_and_hold_equity"].iloc[-1]) / initial - 1.0),
        "time_in_market_pct": 100.0 * bars_in_market / len(equity_curve),
        "longest_losing_streak": _longest_streak(net_values, winning=False),
        "longest_winning_streak": _longest_streak(net_values, winning=True),
        "open_to_close_fallbacks": fallback_executions,
    }
    return equity_curve, trade_frame, summary


def cycle_selection_diagnostics(signals: pd.DataFrame) -> dict[str, Any]:
    selections = [set(values) for values in signals["selected_cycle_periods"]]
    valid = [selection for selection in selections if selection]
    similarities: list[float] = []
    changes = 0
    for previous, current in zip(selections, selections[1:]):
        union = previous | current
        similarity = len(previous & current) / len(union) if union else 1.0
        similarities.append(similarity)
        if previous != current:
            changes += 1
    combinations = {tuple(sorted(selection)) for selection in valid}
    return {
        "selection_change_pct": 100.0 * changes / max(len(selections) - 1, 1),
        "mean_consecutive_overlap_pct": 100.0 * float(np.mean(similarities)) if similarities else np.nan,
        "unique_cycle_combinations": len(combinations),
        "dates_with_valid_model_pct": 100.0 * float(signals["model_valid"].mean()) if len(signals) else 0.0,
        "bullish_state_pct": 100.0 * float((signals["cycle_state"] == "Bullish").mean()) if len(signals) else 0.0,
        "bearish_state_pct": 100.0 * float((signals["cycle_state"] == "Bearish").mean()) if len(signals) else 0.0,
    }


def hindsight_turn_diagnostics(
    frame: pd.DataFrame,
    signals: pd.DataFrame,
    tolerance: int,
) -> pd.DataFrame:
    """Oracle-only comparison; never used by the strategy or its returns."""
    close = frame["close"].to_numpy(dtype=float)
    prominence = max(float(np.std(close)) * 0.05, np.finfo(float).eps)
    actual_peaks, _ = find_peaks(close, distance=2, prominence=prominence)
    actual_troughs, _ = find_peaks(-close, distance=2, prominence=prominence)
    rows = []
    state_mode = bool(signals["signal"].isin(["Bullish", "Bearish"]).any())
    comparisons = (
        (("Bearish", actual_peaks), ("Bullish", actual_troughs))
        if state_mode
        else (("Peak", actual_peaks), ("Trough", actual_troughs))
    )
    for signal_type, actual in comparisons:
        predicted = signals.loc[signals["signal"] == signal_type, "bar_index"].to_numpy(dtype=int)
        matched = sum(bool(len(actual) and np.min(np.abs(actual - index)) <= tolerance) for index in predicted)
        rows.append(
            {
                "signal_type": signal_type,
                "signals": len(predicted),
                "matched_actual_turns": matched,
                "match_rate_pct": 100.0 * matched / len(predicted) if len(predicted) else np.nan,
                "tolerance_bars": tolerance,
            }
        )
    return pd.DataFrame(rows)


def run_rolling_backtest(
    frame: pd.DataFrame,
    metadata: DataMetadata,
    analysis_settings: AnalysisSettings,
    backtest_settings: BacktestSettings,
    start_date: pd.Timestamp | str,
) -> RollingBacktestResult:
    analysis_settings.validate()
    backtest_settings.validate()
    if frame["close"].isna().any() or not np.isfinite(frame["close"].to_numpy(dtype=float)).all():
        raise ValueError("The rolling trade backtest requires a valid close price on every cleaned row.")
    start_index = resolve_start_index(frame, analysis_settings, start_date)
    signals = generate_rolling_signals(
        frame,
        metadata,
        analysis_settings,
        start_index,
        one_bar_confirmation=backtest_settings.one_bar_confirmation,
        signal_mode=backtest_settings.signal_mode,
    )
    equity, trades, summary = simulate_trades(frame, signals, backtest_settings)
    signals = signals.merge(
        equity[["bar_index", "position_after_signal", "equity", "drawdown"]],
        on="bar_index",
        how="left",
    )
    return RollingBacktestResult(
        signals=signals,
        equity_curve=equity,
        trades=trades,
        summary=summary,
        cycle_diagnostics=cycle_selection_diagnostics(signals),
        turn_diagnostics=hindsight_turn_diagnostics(frame, signals, backtest_settings.turn_tolerance_bars),
        earliest_start_date=earliest_backtest_date(frame, analysis_settings),
        requested_start_date=pd.Timestamp(start_date),
        analysis_settings=analysis_settings,
        backtest_settings=backtest_settings,
    )
