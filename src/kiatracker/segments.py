"""Cut each recorded drive into stretches between consecutive GPS readings, each with its own weather.

A drive-level temperature is one hourly value at the drive's midpoint, which is wrong for a long day that
starts near freezing and warms up. A stretch is short (one polling interval: about 1-9 km), so its hour and
place are known: it gets that hour's temperature and wind for its ~10 km cell, the headwind along its own
direction of travel, and the climb and descent between its two ends. Coordinates are used here and dropped:
a Segment holds only derived numbers.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime

from kiatracker.elevation import tile_name
from kiatracker.geo import bearing_deg, headwind_kph
from kiatracker.gold import Drive
from kiatracker.model import LocationReading
from kiatracker.privacy import haversine_km

MIN_KM = 0.05  # GPS jitter while standing still is not a stretch


@dataclass(frozen=True)
class Segment:
    drive_id: int
    seq: int
    start_ts: datetime
    end_ts: datetime
    km: float
    speed_kph: float
    bearing_deg: float
    temp_c: float | None
    wind_kph: float | None
    wind_dir_deg: float | None
    headwind_kph: float | None
    climb_m: float | None
    descent_m: float | None


def weather_key(lat: float, lon: float, ts: datetime) -> tuple[float, float, str]:
    """The same cache key as drive weather: ~10 km cell and UTC day."""
    return round(lat, 1), round(lon, 1), ts.astimezone(UTC).date().isoformat()


def hour_values(hourly: dict | None, ts: datetime) -> dict:
    """Temperature, wind speed and direction for the hour nearest `ts`, or {} without data."""
    if not hourly or not hourly.get("time"):
        return {}
    target = ts.astimezone(UTC).replace(tzinfo=None)
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    i = min(range(len(times)), key=lambda n: abs(times[n] - target))

    def value(name):
        values = hourly.get(name) or []
        return values[i] if i < len(values) else None

    return {
        "temp": value("temperature_2m"),
        "wind": value("wind_speed_10m"),
        "dir": value("wind_direction_10m"),
    }


def path_points(drive: Drive, inner: list[LocationReading]) -> list[tuple[datetime, float, float]]:
    points = [(drive.start_ts, drive.start_lat, drive.start_lon)]
    points += [
        (p.ts, p.lat, p.lon) for p in inner if p.lat is not None and drive.start_ts < p.ts < drive.end_ts
    ]
    points.append((drive.end_ts, drive.end_lat, drive.end_lon))
    return points


def drive_segments(drive: Drive, inner: list[LocationReading], weather: dict, terrain) -> list[Segment]:
    """Stretches of one finished, trustworthy drive. `terrain` needs `.elevation(lat, lon)`, or None."""
    if not usable(drive):
        return []
    points = path_points(drive, inner)
    average_speed = drive.distance_km / max((drive.end_ts - drive.start_ts).total_seconds() / 3600, 1e-9)
    segments = []
    for (t0, lat0, lon0), (t1, lat1, lon1) in zip(points, points[1:], strict=False):
        km = haversine_km((lat0, lon0), (lat1, lon1))
        if km < MIN_KM:
            continue
        hours = (t1 - t0).total_seconds() / 3600
        mid = t0 + (t1 - t0) / 2
        bearing = bearing_deg((lat0, lon0), (lat1, lon1))
        w = hour_values(
            (weather.get(weather_key((lat0 + lat1) / 2, (lon0 + lon1) / 2, mid)) or {}).get("hourly"), mid
        )
        h0 = terrain.elevation(lat0, lon0) if terrain else None
        h1 = terrain.elevation(lat1, lon1) if terrain else None
        rise = h1 - h0 if h0 is not None and h1 is not None else None
        segments.append(
            Segment(
                drive_id=drive.drive_id,
                seq=len(segments) + 1,
                start_ts=t0,
                end_ts=t1,
                km=km,
                speed_kph=km / hours if hours > 0 else average_speed,
                bearing_deg=bearing,
                temp_c=w.get("temp"),
                wind_kph=w.get("wind"),
                wind_dir_deg=w.get("dir"),
                headwind_kph=headwind_kph(w["wind"], w["dir"], bearing)
                if w.get("wind") is not None and w.get("dir") is not None
                else None,
                climb_m=max(rise, 0.0) if rise is not None else None,
                descent_m=max(-rise, 0.0) if rise is not None else None,
            )
        )
    return segments


def usable(drive: Drive) -> bool:
    return not drive.in_progress and drive.quality == "ok" and None not in (drive.start_lat, drive.end_lat)


def inner_points(drive: Drive, location: list[LocationReading], times: list[datetime]) -> list:
    """GPS readings strictly inside the drive; `location` sorted by time and `times` its timestamps."""
    return location[bisect_left(times, drive.start_ts) : bisect_right(times, drive.end_ts)]


def all_segments(drives: list[Drive], location: list[LocationReading], weather: dict, terrain) -> list:
    located = sorted((p for p in location if p.lat is not None), key=lambda p: p.ts)
    times = [p.ts for p in located]
    return [s for d in drives for s in drive_segments(d, inner_points(d, located, times), weather, terrain)]


def needs(drives: list[Drive], location: list[LocationReading]) -> tuple[set, set]:
    """Weather keys (cell, day) and terrain tiles the stretches of these drives would use."""
    located = sorted((p for p in location if p.lat is not None), key=lambda p: p.ts)
    times = [p.ts for p in located]
    keys, tiles = set(), set()
    for d in filter(usable, drives):
        points = path_points(d, inner_points(d, located, times))
        tiles |= {tile_name(lat, lon) for _, lat, lon in points}
        for (t0, lat0, lon0), (t1, lat1, lon1) in zip(points, points[1:], strict=False):
            keys.add(weather_key((lat0 + lat1) / 2, (lon0 + lon1) / 2, t0 + (t1 - t0) / 2))
    return keys, tiles
