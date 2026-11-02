"""Parse raw records into typed, deduplicated readings."""

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from kiatracker.model import (
    ApiTrip,
    BatteryReading,
    DrivingReading,
    LocationReading,
    RangeReading,
    Readings,
    StatusReading,
)
from kiatracker.raw import read_records


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def on(value) -> bool | None:
    return None if value is None else value == "on"


def battery(ts: datetime, d: dict) -> BatteryReading:
    c = d.get("charge") or {}
    target = c.get("targetStateOfCharge") or {}
    capacity_kj = number(c.get("batteryCapacity"))
    return BatteryReading(
        ts,
        number(c.get("stateOfCharge")),
        c.get("plugin"),
        c.get("status"),
        c.get("charging"),
        capacity_kj / 3600 if capacity_kj else None,
        target.get("standard"),
        target.get("quick"),
        c.get("remainTime"),
    )


def driving(ts: datetime, d: dict) -> DrivingReading:
    ignition = (d.get("ignition") or {}).get("status")
    return DrivingReading(
        ts,
        on(ignition),
        d.get("sleepMode"),
        number((d.get("odometer") or {}).get("value")),
        (d.get("transmission") or {}).get("parkingPosition"),
    )


def location(ts: datetime, d: dict) -> LocationReading:
    loc = d.get("location") or {}
    return LocationReading(
        ts,
        number(loc.get("latitude")),
        number(loc.get("longitude")),
        number(loc.get("heading")),
        number((loc.get("speed") or {}).get("value")),
    )


def status(ts: datetime, d: dict) -> StatusReading:
    climate = d.get("climateControl") or {}
    seats = [
        side.get("heat") for row in d.get("seats") or [] for side in row.values() if isinstance(side, dict)
    ]
    return StatusReading(
        ts,
        on(climate.get("status")),
        climate.get("mode"),
        on((d.get("windshield") or {}).get("defrost")),
        on(d.get("steeringWheelHeat")),
        any(s == "on" for s in seats) if seats else None,
    )


def range_(ts: datetime, d: dict) -> RangeReading:
    entries = [e for e in d.get("distanceToEmpties") or [] if e.get("type") == "EV"]
    return RangeReading(ts, number(entries[0].get("value")) if entries else None)


PARSERS: dict[str, tuple[str, Callable]] = {
    "batteries": ("battery", battery),
    "driving": ("driving", driving),
    "locations": ("location", location),
    "status": ("status", status),
    "powertrains": ("range", range_),
}


def merge_trip_fragments(trips: list[ApiTrip], max_gap_s: float = 60) -> list[ApiTrip]:
    merged: list[ApiTrip] = []
    for trip in sorted(trips, key=lambda t: t.start):
        if merged and (trip.start - merged[-1].end) <= timedelta(seconds=max_gap_s):
            merged[-1] = ApiTrip(merged[-1].start, max(merged[-1].end, trip.end))
        else:
            merged.append(trip)
    return merged


def load_readings(raw_dir: Path) -> Readings:
    readings = Readings()
    seen: set[tuple[str, str]] = set()
    for record in read_records(raw_dir, "snapshots"):
        group = record.get("endpoint")
        data = (record.get("body") or {}).get("data")
        if record.get("http_status") != 200 or group not in PARSERS or not isinstance(data, dict):
            continue
        stamp = data.get("timestamp")
        if not stamp or (group, stamp) in seen:
            continue
        seen.add((group, stamp))
        attr, parse = PARSERS[group]
        getattr(readings, attr).append(parse(parse_ts(stamp), data))
    for attr, _ in PARSERS.values():
        getattr(readings, attr).sort(key=lambda r: r.ts)

    trips: dict[datetime, ApiTrip] = {}
    for record in read_records(raw_dir, "trips"):
        for t in (((record.get("body") or {}).get("data") or {}).get("trips")) or []:
            if t.get("triggerStartTime") and t.get("tripLength") is not None:
                start = parse_ts(t["triggerStartTime"])
                trips[start] = ApiTrip(start, start + timedelta(milliseconds=t["tripLength"]))
    readings.api_trips = merge_trip_fragments(list(trips.values()))
    return readings
