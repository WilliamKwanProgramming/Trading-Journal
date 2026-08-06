from pathlib import Path

from cycle_engine.csv_store import CSVStore


def test_csv_store_round_trip_and_persistence(tmp_path: Path) -> None:
    raw = b"time,open,high,low,close\n2024-01-01,1,2,0.5,1.5\n"
    first_store = CSVStore(tmp_path / "csvs")

    saved = first_store.save(raw, "NASDAQ_QQQ, 1D.csv")

    second_store = CSVStore(tmp_path / "csvs")
    assert second_store.list() == [saved]
    assert second_store.read(saved.file_id) == (raw, "NASDAQ_QQQ, 1D.csv")


def test_csv_store_delete_removes_saved_file(tmp_path: Path) -> None:
    store = CSVStore(tmp_path / "csvs")
    saved = store.save(b"a,b\n1,2\n", "example.csv")

    assert store.delete(saved.file_id) is True
    assert store.list() == []
    assert store.delete(saved.file_id) is False
