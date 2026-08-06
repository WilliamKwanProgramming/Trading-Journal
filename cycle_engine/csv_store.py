"""Small local store for CSV files uploaded to the Streamlit workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile


_FILE_ID = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StoredCSV:
    file_id: str
    file_name: str
    size_bytes: int
    uploaded_at: str


class CSVStore:
    """Persist uploaded CSV bytes and their display metadata on local disk."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[1] / "data" / "csvs"

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _data_path(self, file_id: str) -> Path:
        self._validate_id(file_id)
        return self.root / f"{file_id}.csv"

    def _metadata_path(self, file_id: str) -> Path:
        self._validate_id(file_id)
        return self.root / f"{file_id}.json"

    @staticmethod
    def _validate_id(file_id: str) -> None:
        if not _FILE_ID.fullmatch(file_id):
            raise ValueError("Invalid stored CSV id.")

    @staticmethod
    def _display_name(file_name: str) -> str:
        name = Path(file_name).name.strip()
        return name or "uploaded.csv"

    @staticmethod
    def _atomic_write(path: Path, contents: bytes) -> None:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(contents)
        temporary_path.replace(path)

    def save(self, raw: bytes, file_name: str) -> StoredCSV:
        self._ensure_root()
        display_name = self._display_name(file_name)
        file_id = hashlib.sha256(display_name.encode("utf-8") + b"\0" + raw).hexdigest()
        data_path = self._data_path(file_id)
        metadata_path = self._metadata_path(file_id)

        if not data_path.exists():
            self._atomic_write(data_path, raw)
        if not metadata_path.exists():
            metadata = {
                "file_id": file_id,
                "file_name": display_name,
                "size_bytes": len(raw),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._atomic_write(metadata_path, json.dumps(metadata, indent=2).encode("utf-8"))
        stored = self.get(file_id)
        if stored is None:
            raise RuntimeError("The uploaded CSV could not be saved.")
        return stored

    def list(self) -> list[StoredCSV]:
        self._ensure_root()
        stored: list[StoredCSV] = []
        for metadata_path in self.root.glob("*.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                file_id = str(metadata["file_id"])
                file_name = str(metadata["file_name"])
                size_bytes = int(metadata["size_bytes"])
                uploaded_at = str(metadata["uploaded_at"])
                self._validate_id(file_id)
                if not self._data_path(file_id).is_file():
                    continue
                stored.append(StoredCSV(file_id, file_name, size_bytes, uploaded_at))
            except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(stored, key=lambda item: item.uploaded_at, reverse=True)

    def get(self, file_id: str) -> StoredCSV | None:
        self._ensure_root()
        try:
            metadata = json.loads(self._metadata_path(file_id).read_text(encoding="utf-8"))
            stored = StoredCSV(
                file_id=str(metadata["file_id"]),
                file_name=str(metadata["file_name"]),
                size_bytes=int(metadata["size_bytes"]),
                uploaded_at=str(metadata["uploaded_at"]),
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None
        if stored.file_id != file_id or not self._data_path(file_id).is_file():
            return None
        return stored

    def read(self, file_id: str) -> tuple[bytes, str]:
        stored = self.get(file_id)
        if stored is None:
            raise FileNotFoundError("The saved CSV no longer exists.")
        return self._data_path(file_id).read_bytes(), stored.file_name

    def delete(self, file_id: str) -> bool:
        stored = self.get(file_id)
        if stored is None:
            return False
        self._metadata_path(file_id).unlink(missing_ok=True)
        self._data_path(file_id).unlink(missing_ok=True)
        return True
