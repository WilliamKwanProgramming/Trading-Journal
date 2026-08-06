from __future__ import annotations

import pandas as pd
import pytest

from cycle_engine.data_loader import CSVValidationError, load_tradingview_csv
from conftest import synthetic_frame


def test_tradingview_parser_sorts_deduplicates_and_ignores_extra_columns() -> None:
    frame = synthetic_frame(80)
    duplicated = pd.concat([frame.iloc[::-1], frame.iloc[[20]]], ignore_index=True)
    duplicated["close"] = duplicated["close"].astype(object)
    duplicated.loc[0, "close"] = "bad"
    parsed, metadata = load_tradingview_csv(
        duplicated.to_csv(index=False).encode(), "NASDAQ_QQQ, 1D.csv", "close"
    )
    assert parsed["timestamp"].is_monotonic_increasing
    assert parsed["timestamp"].is_unique
    assert "Ignored indicator" not in parsed.columns
    assert metadata.timeframe == "1D"
    assert metadata.symbol == "QQQ"
    assert metadata.duplicate_rows == 1
    assert metadata.dropped_rows == 1


def test_unix_timestamp_parser() -> None:
    frame = synthetic_frame(20)
    frame["time"] = frame["time"].map(lambda value: int(pd.Timestamp(value).timestamp()))
    parsed, metadata = load_tradingview_csv(frame.to_csv(index=False).encode(), "SOXX.csv")
    assert len(parsed) == 20
    assert metadata.start == pd.Timestamp("2020-01-01")


@pytest.mark.parametrize(
    "payload, expected",
    [
        (b"", "Could not read"),
        (b"time,open,high,low\n2024-01-01,1,2,0\n", "close"),
        (b"nonsense\nvalue\n", "time"),
    ],
)
def test_malformed_or_missing_columns(payload: bytes, expected: str) -> None:
    with pytest.raises(CSVValidationError, match=expected):
        load_tradingview_csv(payload)


def test_bad_rows_produce_readable_error() -> None:
    payload = b"time,open,high,low,close\nnot-a-date,1,2,0,bad\n"
    with pytest.raises(CSVValidationError, match="No valid timestamp/close rows"):
        load_tradingview_csv(payload)
