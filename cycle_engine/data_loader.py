"""TradingView CSV parsing and timeframe inference."""

from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
from typing import BinaryIO, TextIO

import numpy as np
import pandas as pd

from .models import DataMetadata


class CSVValidationError(ValueError):
    """Raised when an uploaded CSV cannot be used safely."""


class InsufficientHistoryError(ValueError):
    """Raised when the requested scan cannot be supported by the data."""


PRICE_COLUMNS = ("open", "high", "low", "close")


def _read_csv(source: bytes | str | Path | BinaryIO | TextIO) -> pd.DataFrame:
    try:
        if isinstance(source, bytes):
            return pd.read_csv(BytesIO(source))
        if isinstance(source, Path):
            return pd.read_csv(source)
        if isinstance(source, str):
            if "\n" in source or "," in source:
                return pd.read_csv(StringIO(source))
            return pd.read_csv(source)
        return pd.read_csv(source)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, OSError) as exc:
        raise CSVValidationError(f"Could not read the CSV: {exc}") from exc


def _parse_timestamps(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric_share = float(numeric.notna().mean())
    if numeric_share >= 0.8 and numeric.notna().any():
        magnitude = float(numeric.dropna().abs().median())
        unit = "ns" if magnitude >= 1e17 else "us" if magnitude >= 1e14 else "ms" if magnitude >= 1e11 else "s"
        parsed = pd.to_datetime(numeric, unit=unit, errors="coerce", utc=True)
    else:
        try:
            parsed = pd.to_datetime(values, errors="coerce", utc=True, format="mixed")
        except (TypeError, ValueError):
            parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.tz_convert(None)


def estimate_timeframe(timestamps: pd.Series | pd.DatetimeIndex) -> tuple[str, pd.Timedelta]:
    index = pd.DatetimeIndex(timestamps).sort_values().unique()
    if len(index) < 2:
        return "Unknown", pd.Timedelta(0)
    deltas = pd.Series(index[1:] - index[:-1])
    median = pd.Timedelta(deltas.median())
    seconds = median.total_seconds()
    known = [
        (60, "1m"), (300, "5m"), (900, "15m"), (1800, "30m"),
        (3600, "1H"), (7200, "2H"), (14400, "4H"),
        (86400, "1D"), (604800, "1W"), (2592000, "1M"),
    ]
    value, label = min(known, key=lambda item: abs(np.log(max(seconds, 1) / item[0])))
    if abs(seconds - value) / value <= 0.35:
        return label, median
    if seconds < 86400:
        return f"~{seconds / 3600:.1f}H", median
    return f"~{seconds / 86400:.1f}D", median


def _symbol_from_filename(file_name: str) -> str:
    stem = Path(file_name).stem
    # TradingView commonly exports names such as "NASDAQ_QQQ, 1D.csv".
    instrument = stem.split(",", maxsplit=1)[0].strip()
    parts = [part.strip() for part in instrument.split("_") if part.strip()]
    exchanges = {"NASDAQ", "NYSE", "AMEX", "TSX", "CBOE", "OTC"}
    if len(parts) > 1 and parts[0].upper() in exchanges:
        return parts[1]
    return instrument


def load_tradingview_csv(
    source: bytes | str | Path | BinaryIO | TextIO,
    file_name: str = "uploaded.csv",
    price_source: str = "close",
) -> tuple[pd.DataFrame, DataMetadata]:
    """Parse a TradingView export while ignoring unrelated indicator columns."""
    if price_source not in PRICE_COLUMNS:
        raise CSVValidationError(f"Unsupported source '{price_source}'.")
    frame = _read_csv(source)
    if frame.empty:
        raise CSVValidationError("The CSV is empty.")

    normalized: dict[str, str] = {}
    for column in frame.columns:
        key = str(column).strip().lower()
        if key == "date" or key == "datetime" or key == "timestamp":
            key = "time"
        normalized.setdefault(key, column)

    missing = [column for column in ("time", *PRICE_COLUMNS) if column not in normalized]
    if missing:
        raise CSVValidationError(
            "Missing required TradingView column(s): " + ", ".join(missing) +
            ". Expected time, open, high, low, and close (Volume is optional)."
        )

    output = pd.DataFrame({"timestamp": _parse_timestamps(frame[normalized["time"]])})
    for column in PRICE_COLUMNS:
        output[column] = pd.to_numeric(frame[normalized[column]], errors="coerce")
    if "volume" in normalized:
        output["volume"] = pd.to_numeric(frame[normalized["volume"]], errors="coerce")

    original_rows = len(output)
    output = output.dropna(subset=["timestamp", price_source])
    dropped_rows = original_rows - len(output)
    output = output.sort_values("timestamp", kind="mergesort")
    duplicate_rows = int(output.duplicated("timestamp", keep="last").sum())
    output = output.drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    if output.empty:
        raise CSVValidationError(f"No valid timestamp/{price_source} rows remain after cleaning.")
    if not np.isfinite(output[price_source].to_numpy(dtype=float)).all():
        raise CSVValidationError(f"The {price_source} column contains non-finite values.")

    timeframe, median_interval = estimate_timeframe(output["timestamp"])
    warnings: list[str] = []
    if "volume" not in normalized:
        warnings.append("Volume was not present; it is not required by the cycle engine.")
    if dropped_rows:
        warnings.append(f"Dropped {dropped_rows} row(s) with invalid timestamps or {price_source} values.")
    if duplicate_rows:
        warnings.append(f"Kept the last value for {duplicate_rows} duplicate timestamp row(s).")
    metadata = DataMetadata(
        file_name=file_name,
        symbol=_symbol_from_filename(file_name),
        start=pd.Timestamp(output["timestamp"].iloc[0]),
        end=pd.Timestamp(output["timestamp"].iloc[-1]),
        bars=len(output),
        timeframe=timeframe,
        median_interval=median_interval,
        dropped_rows=dropped_rows,
        duplicate_rows=duplicate_rows,
        warnings=tuple(warnings),
    )
    return output, metadata


def require_history(frame: pd.DataFrame, max_period: float) -> None:
    minimum = max(64, int(np.ceil(2.0 * max_period)))
    if len(frame) < minimum:
        raise InsufficientHistoryError(
            f"Insufficient history: {len(frame)} valid bars are available, but at least {minimum} "
            f"bars are required to evaluate a {max_period:g}-bar maximum cycle twice. "
            "Upload more history or reduce the maximum period."
        )


def future_timestamps(metadata: DataMetadata, horizon: int) -> pd.DatetimeIndex:
    start = metadata.end
    if metadata.timeframe == "1D":
        return pd.bdate_range(start=start, periods=horizon + 1, inclusive="right")
    if metadata.timeframe == "1W":
        return pd.date_range(start=start, periods=horizon + 1, freq="7D", inclusive="right")
    if metadata.timeframe == "1M":
        return pd.date_range(start=start, periods=horizon + 1, freq="ME", inclusive="right")
    delta = metadata.median_interval
    if delta <= pd.Timedelta(0):
        delta = pd.Timedelta(days=1)
    return pd.DatetimeIndex([start + delta * step for step in range(1, horizon + 1)])
