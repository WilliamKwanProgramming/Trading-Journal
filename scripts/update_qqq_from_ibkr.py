#!/usr/bin/env python3
"""Update a TradingView-style QQQ daily CSV with daily bars from IBKR.

The Trade Ledger workbench expects columns named ``time,open,high,low,close,Volume``.
This script preserves the existing rows and formatting, merges recent IBKR bars,
and writes atomically only when ``--write`` is supplied.

Examples:

    # Inspect the selected QQQ file and the bars IBKR would add:
    python scripts/update_qqq_from_ibkr.py --port 4001

    # Write the update after IB Gateway is open:
    python scripts/update_qqq_from_ibkr.py --port 4001 --client-id 83 --write

    # Explicitly select a file if the repository contains multiple snapshots:
    python scripts/update_qqq_from_ibkr.py --csv data/csvs/FILE_ID.csv --write
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time as time_module
from zoneinfo import ZoneInfo


def _load_ibapi() -> None:
    """Make the official IBKR Python client importable without installation."""
    candidates = [
        Path.home() / "IBJts" / "source" / "pythonclient",
        Path.home() / "ibkr" / "tws-api" / "source" / "pythonclient",
    ]
    for candidate in candidates:
        if (candidate / "ibapi").is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_load_ibapi()

try:
    from ibapi.client import EClient  # noqa: E402
    from ibapi.contract import Contract  # noqa: E402
    from ibapi.wrapper import EWrapper  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - depends on the local Python environment
    raise SystemExit(
        "The IBKR Python client could not be imported. Activate the environment "
        "that has ibapi and protobuf installed, for example "
        "~/Downloads/backtesting/.venv/bin/python, or install protobuf in your environment."
    ) from exc


CSV_COLUMNS = ("time", "open", "high", "low", "close", "Volume")
EASTERN = ZoneInfo("America/New_York")
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "csvs"


class IBKRRequestError(RuntimeError):
    pass


class IBKRClient(EWrapper, EClient):
    def __init__(self, timeout: float) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.timeout = timeout
        self.connected_event = threading.Event()
        self.next_id_event = threading.Event()
        self.next_order_id: int | None = None
        self._lock = threading.Lock()
        self._historical: dict[int, list[dict[str, object]]] = {}
        self._historical_done: dict[int, threading.Event] = {}
        self._historical_errors: dict[int, list[str]] = {}
        self._details: dict[int, list[object]] = {}
        self._details_done: dict[int, threading.Event] = {}
        self._details_errors: dict[int, list[str]] = {}

    def nextValidId(self, orderId: int) -> None:
        self.next_order_id = orderId
        self.next_id_event.set()
        self.connected_event.set()

    def error(
        self,
        reqId: int,
        errorTime: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        message = f"IBKR error {errorCode} (request {reqId}): {errorString}"
        print(message, file=sys.stderr)
        if reqId in self._historical_done:
            if errorCode not in {162, 2106, 2107}:
                self._historical_errors.setdefault(reqId, []).append(message)
            if errorCode == 162:
                self._historical_done[reqId].set()
        if reqId in self._details_done:
            if errorCode != 2106:
                self._details_errors.setdefault(reqId, []).append(message)
            if errorCode == 200:
                self._details_done[reqId].set()

    def contractDetails(self, reqId: int, contractDetails: object) -> None:
        self._details.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId: int) -> None:
        if reqId in self._details_done:
            self._details_done[reqId].set()

    def historicalData(self, reqId: int, bar: object) -> None:
        raw_date = str(getattr(bar, "date", ""))[:8]
        try:
            bar_date = datetime.strptime(raw_date, "%Y%m%d").date()
        except ValueError:
            return
        self._historical.setdefault(reqId, []).append({
            "date": bar_date,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": getattr(bar, "volume", ""),
        })

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        if reqId in self._historical_done:
            self._historical_done[reqId].set()

    def resolve_qqq(self, req_id: int) -> Contract:
        request = Contract()
        request.symbol = "QQQ"
        request.secType = "STK"
        request.exchange = "SMART"
        request.currency = "USD"
        self._details[req_id] = []
        self._details_done[req_id] = threading.Event()
        self._details_errors[req_id] = []
        self.reqContractDetails(req_id, request)
        if not self._details_done[req_id].wait(self.timeout):
            raise TimeoutError("Timed out resolving QQQ's contract details.")
        errors = self._details_errors.pop(req_id)
        details = self._details.pop(req_id)
        self._details_done.pop(req_id, None)
        if errors and not details:
            raise IBKRRequestError("; ".join(errors))
        matching = [
            item for item in details
            if getattr(item.contract, "secType", "") == "STK"
            and getattr(item.contract, "currency", "") == "USD"
        ]
        if not matching:
            raise IBKRRequestError("IBKR did not return a USD common-stock contract for QQQ.")
        chosen = next(
            (item for item in matching if getattr(item.contract, "primaryExchange", "") == "NASDAQ"),
            matching[0],
        )
        contract = chosen.contract
        contract.exchange = "SMART"
        return contract

    def daily_bars(self, req_id: int, contract: Contract, end_date: date, duration: str) -> list[dict[str, object]]:
        self._historical[req_id] = []
        self._historical_done[req_id] = threading.Event()
        self._historical_errors[req_id] = []
        end = f"{end_date:%Y%m%d} 23:59:59 US/Eastern"
        self.reqHistoricalData(
            req_id,
            contract,
            end,
            duration,
            "1 day",
            "TRADES",
            1,
            1,
            False,
            [],
        )
        if not self._historical_done[req_id].wait(self.timeout):
            self.cancelHistoricalData(req_id)
            raise TimeoutError(f"Timed out waiting for historical request {req_id}.")
        errors = self._historical_errors.pop(req_id)
        bars = self._historical.pop(req_id)
        self._historical_done.pop(req_id, None)
        if errors:
            raise IBKRRequestError("; ".join(errors))
        return bars


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="QQQ CSV to update; default selects the longest daily QQQ snapshot")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4001)
    parser.add_argument("--client-id", type=int, default=83)
    parser.add_argument("--duration", default="2 Y", help="IBKR lookback for the update request (default: 2 Y)")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--include-partial", action="store_true", help="Include today's in-progress bar when available")
    parser.add_argument("--write", action="store_true", help="Atomically write the merged CSV")
    parser.add_argument("--backup", action="store_true", help="Create <csv>.before-ibkr-update before writing")
    return parser.parse_args()


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing = [column for column in CSV_COLUMNS if column not in fields]
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        return list(reader), fields


def select_csv(data_dir: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    candidates: list[tuple[int, Path]] = []
    for path in data_dir.glob("*.csv"):
        metadata_path = path.with_suffix(".json")
        try:
            display_name = str(json.loads(metadata_path.read_text(encoding="utf-8"))["file_name"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            display_name = path.name
        name = display_name.upper()
        if "QQQ" not in name or "1D" not in name:
            continue
        try:
            rows, _ = read_csv(path)
        except ValueError:
            continue
        candidates.append((len(rows), path))
    if not candidates:
        raise FileNotFoundError(f"No daily QQQ CSV was found in {data_dir}")
    candidates.sort(reverse=True)
    selected = candidates[0][1]
    print(f"Auto-selected longest daily QQQ snapshot: {selected} ({candidates[0][0]} rows)")
    if len(candidates) > 1:
        print("Other daily QQQ snapshots were left untouched:")
        for rows, path in candidates[1:]:
            print(f"  {path} ({rows} rows)")
    return selected


def parse_epoch(value: str) -> int:
    return int(float(value))


def epoch_for_market_date(value: date) -> int:
    market_open = datetime.combine(value, time(9, 30), tzinfo=EASTERN)
    return int(market_open.timestamp())


def completed_cutoff(include_partial: bool) -> date:
    now = datetime.now(EASTERN)
    if include_partial:
        return now.date()
    # Avoid replacing the prior close with an in-progress daily bar during RTH.
    cutoff = now.date() if now.time() >= time(16, 0) else now.date() - timedelta(days=1)
    while cutoff.weekday() >= 5:
        cutoff -= timedelta(days=1)
    return cutoff


def format_volume(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number != number or number < 0:
        return ""
    return str(int(number)) if number.is_integer() else str(number)


def merge_rows(existing: list[dict[str, str]], fetched: list[dict[str, object]], cutoff: date) -> list[dict[str, str]]:
    merged: dict[int, dict[str, str]] = {}
    for row in existing:
        timestamp = parse_epoch(row["time"])
        merged[timestamp] = {column: row.get(column, "") for column in CSV_COLUMNS}
    for bar in fetched:
        bar_date = bar["date"]
        assert isinstance(bar_date, date)
        if bar_date > cutoff:
            continue
        timestamp = epoch_for_market_date(bar_date)
        merged[timestamp] = {
            "time": str(timestamp),
            "open": str(bar["open"]),
            "high": str(bar["high"]),
            "low": str(bar["low"]),
            "close": str(bar["close"]),
            "Volume": format_volume(bar["volume"]),
        }
    return [merged[key] for key in sorted(merged)]


def atomic_write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False, newline="", encoding="utf-8") as handle:
        temporary = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def update_metadata(path: Path, byte_count: int) -> None:
    metadata_path = path.with_suffix(".json")
    if not metadata_path.exists():
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["size_bytes"] = byte_count
    metadata["uploaded_at"] = datetime.now(timezone.utc).isoformat()
    atomic_path = metadata_path.with_suffix(".json.tmp")
    atomic_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    atomic_path.replace(metadata_path)


def main() -> int:
    args = parse_args()
    path = select_csv(args.data_dir.expanduser().resolve(), args.csv)
    existing, fields = read_csv(path)
    existing_timestamps = {parse_epoch(row["time"]) for row in existing}
    cutoff = completed_cutoff(args.include_partial)
    print(f"Target: {path}")
    print(f"Existing rows: {len(existing)}; latest timestamp: {max(existing_timestamps)}")
    print(f"IBKR cutoff date: {cutoff}; mode: {'WRITE' if args.write else 'DRY RUN'}")

    client = IBKRClient(args.timeout)
    reader: threading.Thread | None = None
    try:
        client.setConnectOptions("+PACEAPI")
        print(f"Connecting to IB Gateway at {args.host}:{args.port} (clientId={args.client_id})...")
        client.connect(args.host, args.port, args.client_id)
        reader = threading.Thread(target=client.run, daemon=True)
        reader.start()
        if not client.connected_event.wait(args.timeout):
            raise TimeoutError("Timed out waiting for the IBKR handshake.")
        contract = client.resolve_qqq(9000)
        if args.request_delay:
            time_module.sleep(args.request_delay)
        fetched = client.daily_bars(9001, contract, cutoff, args.duration)
        merged = merge_rows(existing, fetched, cutoff)
    finally:
        if client.isConnected():
            client.disconnect()
        if reader is not None:
            reader.join(timeout=5)

    old_keys = {parse_epoch(row["time"]) for row in existing}
    new_keys = {parse_epoch(row["time"]) for row in merged}
    added = len(new_keys - old_keys)
    print(f"IBKR returned {len(fetched)} daily bars; merged rows: {len(merged)}; new timestamps: {added}")
    if not args.write:
        print("Dry run only. Re-run with --write to update the CSV.")
        return 0
    if args.backup:
        backup = path.with_name(path.name + ".before-ibkr-update")
        backup.write_bytes(path.read_bytes())
        print(f"Backup: {backup}")
    atomic_write(path, merged)
    update_metadata(path, path.stat().st_size)
    print(f"Updated {path} atomically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
