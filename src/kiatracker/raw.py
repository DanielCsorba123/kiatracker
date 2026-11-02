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
    with path.open("ab") as f:
        if f.tell() and not ends_with_newline(path):
            f.write(b"\n")  # the previous write was cut short; start this record on a fresh line
        f.write((json.dumps(record) + "\n").encode("utf-8"))
    return path


def append_records(raw_dir: Path, kind: str, records: list[tuple[datetime, dict]]) -> None:
    """Append many (time, record) pairs, opening each monthly file once."""
    by_month: dict[str, list[dict]] = {}
    for now, record in records:
        by_month.setdefault(f"{now:%Y-%m}", []).append(record)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for month, batch in by_month.items():
        path = raw_dir / f"{kind}-{month}.jsonl"
        with path.open("ab") as f:
            if f.tell() and not ends_with_newline(path):
                f.write(b"\n")
            f.write("".join(json.dumps(r) + "\n" for r in batch).encode("utf-8"))


def ends_with_newline(path: Path) -> bool:
    with path.open("rb") as f:
        f.seek(-1, 2)
        return f.read(1) == b"\n"


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
