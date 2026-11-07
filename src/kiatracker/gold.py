"""Derive drives, charging sessions and charge-to-charge windows from readings (the gold layer).

The car is polled every few minutes, so every boundary here is approximate: a drive starts somewhere
between the last parked reading and the first moving one. API trips (exact start and duration) tighten it.
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta

from kiatracker.model import BatteryReading, DrivingReading, LocationReading, Readings
from kiatracker.privacy import zone_of

MOVE_THRESHOLD_KM = 0.05
MIN_KM_FOR_CONSUMPTION = 5.0  # below this, 0.5 % SOC steps make kWh/100 km meaningless
UNSEEN_AFTER = timedelta(hours=1)  # a drive seen only as an odometer jump across this much silence
PLAUSIBLE_KWH_100KM = (6.0, 45.0)  # outside this an EV3's measured consumption is a data problem


@dataclass(frozen=True)
class Drive:
    drive_id: int
    start_ts: datetime
    end_ts: datetime
    odo_start: float | None
    odo_end: float | None
    distance_km: float | None
    soc_start: float | None
    soc_end: float | None
    energy_kwh: float | None
    kwh_per_100km: float | None
    start_lat: float | None
    start_lon: float | None
    end_lat: float | None
    end_lon: float | None
    mid_ts: datetime
    mid_lat: float | None
    mid_lon: float | None
    start_zone: str | None
    end_zone: str | None
    api_trips: int
    location_points: int
    in_progress: bool
    quality: str = "ok"  # "gap": energy unknown (unseen period); "implausible": energy impossible


@dataclass(frozen=True)
class ChargingSession:
    session_id: int
    start_ts: datetime
    end_ts: datetime
    soc_start: float | None
    soc_end: float | None
    energy_kwh: float | None
    hours: float
    avg_kw: float | None
    zone: str | None
    in_progress: bool


@dataclass(frozen=True)
class ChargeWindow:
    window_id: int
    start_ts: datetime
    end_ts: datetime
    soc_used: float | None
    energy_kwh: float | None
    distance_km: float
    drives: int
    kwh_per_100km: float | None


class Timeline:
    """Readings sorted by ts, with fast lookup of the latest reading at or before a time."""

    def __init__(self, readings: list):
        self.readings = readings
        self.times = [r.ts for r in readings]

    def latest_at(self, ts: datetime):
        i = bisect_right(self.times, ts)
        return self.readings[i - 1] if i else None


def kwh(soc_delta: float | None, capacity_kwh: float) -> float | None:
    return None if soc_delta is None else soc_delta / 100 * capacity_kwh


def per_100km(energy: float | None, distance: float | None) -> float | None:
    if energy is None or distance is None or distance < MIN_KM_FOR_CONSUMPTION:
        return None
    return energy / distance * 100


def diff(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def is_moving(reading: DrivingReading, previous: DrivingReading | None) -> bool:
    if reading.ignition_on:
        return True
    if previous is None or reading.odometer_km is None or previous.odometer_km is None:
        return False
    return reading.odometer_km - previous.odometer_km > MOVE_THRESHOLD_KM


def drive_runs(driving: list[DrivingReading]):
    """Yield (start_reading, moving_readings, end_reading or None)."""
    run: list[DrivingReading] = []
    start = None
    for i, reading in enumerate(driving):
        previous = driving[i - 1] if i else None
        if is_moving(reading, previous):
            if not run:
                start = previous or reading
            run.append(reading)
            if not reading.ignition_on:  # odometer jumped while parked: a drive the polling missed ended here
                yield start, run, reading
                run = []
        elif run:
            yield start, run, reading
            run = []
    if run:
        yield start, run, None


def split_by_trips(start, run, end, api_trips):
    """Split one polled run into the car's own trips.

    Short stops between trips often fall between two polls, so polling sees one long drive. The API's
    trip list knows better: readings are cut at the midpoint between one trip's end and the next one's
    start. A trip with no reading of its own can't be measured, so it stays with a neighbour.
    Yields (start reading, first moving reading, last reading, end reading or None while driving, trips).
    """
    last = end or run[-1]
    trips = [t for t in api_trips if start.ts < t.start <= last.ts]
    if len(trips) < 2:
        yield start, run[0], last, end, trips
        return
    cuts = [a.end + (b.start - a.end) / 2 for a, b in zip(trips, trips[1:], strict=False)]
    groups: list[tuple[list, list]] = [([], [trip]) for trip in trips]
    for reading in run:
        groups[bisect_right(cuts, reading.ts)][0].append(reading)
    merged: list[tuple[list, list]] = []
    for readings, group_trips in groups:
        if merged and not merged[-1][0]:  # previous trip had no reading: join it to this one
            merged[-1] = (readings, merged[-1][1] + group_trips)
        else:
            merged.append((readings, group_trips))
    if len(merged) > 1 and not merged[-1][0]:
        _, tail_trips = merged.pop()
        merged[-1] = (merged[-1][0], merged[-1][1] + tail_trips)

    segment_start = start
    for i, (readings, group_trips) in enumerate(merged):
        if i == len(merged) - 1:
            yield segment_start, readings[0], end or readings[-1], end, group_trips
        else:
            yield segment_start, readings[0], readings[-1], readings[-1], group_trips
            segment_start = readings[-1]


def derive_drives(
    r: Readings, capacity_kwh: float, home: tuple[float, float] | None, radius_km: float
) -> list[Drive]:
    drives = []
    battery, locations = Timeline(r.battery), Timeline(r.location)
    segments = (
        segment
        for start, run, end in drive_runs(r.driving)
        for segment in split_by_trips(start, run, end, r.api_trips)
    )
    for start, first, last, end, trips in segments:
        if trips:
            start_ts, end_ts = trips[0].start, max(t.end for t in trips)
        else:
            start_ts = first.ts if first.ignition_on else start.ts
            end_ts = last.ts
        mid_ts = start_ts + (end_ts - start_ts) / 2

        soc_start = getattr(battery.latest_at(start.ts), "soc", None)
        soc_end = getattr(battery.latest_at(last.ts), "soc", None)
        energy = kwh(diff(soc_start, soc_end), capacity_kwh)
        distance = diff(last.odometer_km, start.odometer_km)
        quality = drive_quality(start, first, energy, distance)
        if quality != "ok":
            energy = None  # the distance (odometer) is still exact; the energy is not
        loc_start: LocationReading | None = locations.latest_at(start.ts)
        loc_end: LocationReading | None = locations.latest_at(last.ts)
        inside = [p for p in r.location if start_ts <= p.ts <= end_ts]
        loc_mid = min(inside, key=lambda p: abs(p.ts - mid_ts)) if inside else loc_start

        drives.append(
            Drive(
                drive_id=len(drives) + 1,
                start_ts=start_ts,
                end_ts=end_ts,
                odo_start=start.odometer_km,
                odo_end=last.odometer_km,
                distance_km=distance,
                soc_start=soc_start,
                soc_end=soc_end,
                energy_kwh=energy,
                kwh_per_100km=per_100km(energy, distance),
                start_lat=getattr(loc_start, "lat", None),
                start_lon=getattr(loc_start, "lon", None),
                end_lat=getattr(loc_end, "lat", None),
                end_lon=getattr(loc_end, "lon", None),
                mid_ts=mid_ts,
                mid_lat=getattr(loc_mid, "lat", None),
                mid_lon=getattr(loc_mid, "lon", None),
                start_zone=zone_of(
                    getattr(loc_start, "lat", None), getattr(loc_start, "lon", None), home, radius_km
                ),
                end_zone=zone_of(
                    getattr(loc_end, "lat", None), getattr(loc_end, "lon", None), home, radius_km
                ),
                api_trips=len(trips),
                location_points=len(inside),
                in_progress=end is None,
                quality=quality,
            )
        )
    return drives


def drive_quality(start: DrivingReading, first: DrivingReading, energy, distance) -> str:
    """Guardrails against energy figures that can't be right.

    "gap": the drive was only seen as an odometer jump across more than an hour without readings (the
    collector was off). Charging may hide in that time, as it did when the car left fully charged but the
    last reading said 59.5 %. "implausible": consumption outside what an EV3 can use, or charge rising.
    """
    if not first.ignition_on and first.ts - start.ts > UNSEEN_AFTER:
        return "gap"
    if energy is not None and energy < 0:
        return "implausible"
    measured = per_100km(energy, distance)
    if measured is not None and not PLAUSIBLE_KWH_100KM[0] <= measured <= PLAUSIBLE_KWH_100KM[1]:
        return "implausible"
    return "ok"


def derive_charging_sessions(
    r: Readings, capacity_kwh: float, home: tuple[float, float] | None, radius_km: float
) -> list[ChargingSession]:
    sessions = []
    battery, locations = r.battery, Timeline(r.location)
    i = 0
    while i < len(battery):
        if not battery[i].charging:
            i += 1
            continue
        j = i
        while j + 1 < len(battery) and battery[j + 1].charging:
            j += 1
        first, before = battery[i], battery[i - 1] if i else None
        end: BatteryReading | None = battery[j + 1] if j + 1 < len(battery) else None
        last = end or battery[j]
        soc_start = first.soc
        if before and before.soc is not None and (soc_start is None or before.soc < soc_start):
            soc_start = before.soc
        energy = kwh(diff(last.soc, soc_start), capacity_kwh)
        hours = (last.ts - first.ts).total_seconds() / 3600
        loc = locations.latest_at(first.ts)
        sessions.append(
            ChargingSession(
                session_id=len(sessions) + 1,
                start_ts=first.ts,
                end_ts=last.ts,
                soc_start=soc_start,
                soc_end=last.soc,
                energy_kwh=energy,
                hours=hours,
                avg_kw=energy / hours if energy is not None and hours > 0 else None,
                zone=zone_of(getattr(loc, "lat", None), getattr(loc, "lon", None), home, radius_km),
                in_progress=end is None,
            )
        )
        i = j + 1
    return sessions


def derive_charge_windows(
    sessions: list[ChargingSession], drives: list[Drive], capacity_kwh: float
) -> list[ChargeWindow]:
    finished = [s for s in sessions if not s.in_progress]
    windows = []
    for before, after in zip(finished, finished[1:], strict=False):
        inside = [d for d in drives if not d.in_progress and before.end_ts < d.end_ts <= after.start_ts]
        distance = sum(d.distance_km or 0 for d in inside)
        soc_used = diff(before.soc_end, after.soc_start)
        energy = kwh(soc_used, capacity_kwh)
        windows.append(
            ChargeWindow(
                window_id=len(windows) + 1,
                start_ts=before.end_ts,
                end_ts=after.start_ts,
                soc_used=soc_used,
                energy_kwh=energy,
                distance_km=distance,
                drives=len(inside),
                kwh_per_100km=per_100km(energy, distance),
            )
        )
    return windows
