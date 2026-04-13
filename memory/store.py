"""JSON-based memory store for persisting past failure-fix records."""

import json
import os
from models import MemoryRecord, deserialize_memory_record
from dataclasses import asdict


class MemoryStore:
    """Persists past failure-fix records to a JSON file on disk."""

    def __init__(self, filepath: str = "memory/memory.json") -> None:
        self.filepath = filepath
        if not os.path.exists(self.filepath):
            self._save([])

    def store(self, record: MemoryRecord) -> None:
        """Append a failure-fix record to the JSON file."""
        records = self._load()
        records.append(asdict(record))
        self._save(records)

    def retrieve_similar(self, error_signature: str, top_k: int = 3) -> list[MemoryRecord]:
        """Find past records with similar error signatures using substring matching."""
        records = self._load()
        matches = [
            deserialize_memory_record(r)
            for r in records
            if error_signature in r.get("error_signature", "")
        ]
        return matches[:top_k]

    def _load(self) -> list[dict]:
        """Load all records from the JSON file."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, records: list[dict]) -> None:
        """Write all records to the JSON file."""
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
