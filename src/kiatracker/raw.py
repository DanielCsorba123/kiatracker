"""Append-only raw store: one JSON record per line, one file per kind and month.

Raw files are the only source of truth; everything else is rebuilt from them.
"""

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path


def append_record(raw_dir: Path, kind: str, record: dict, now: datetime) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{kind}-{now:%Y-%m}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return path


def read_records(raw_dir: Path, kind: str) -> Iterator[dict]:
    for path in sorted(raw_dir.glob(f"{kind}-*.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue  # a line cut short by a crash or power loss


def compact_isla(payload: dict) -> dict:
    """Shrink each trip's `isla` arrays (a constant value per second) to length and distinct values."""
    trips = (payload.get("data") or {}).get("trips") if isinstance(payload, dict) else None
    for trip in trips or []:
        trip["isla"] = {
            key: {"len": len(values), "distinct": sorted(set(map(str, values)))}
            for key, values in (trip.get("isla") or {}).items()
        }
    return payload
