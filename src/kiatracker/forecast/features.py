"""One row of physics features per finished drive.

Coordinates are read to work out the direction of travel against the wind, but only derived numbers come out.
When a drive has stretches (see kiatracker.segments) with weather for each, the features are built from them:
each stretch with its own speed, hour's temperature, headwind and climb. Otherwise from the drive as a whole.
"""

from bisect import bisect_left, bisect_right

import duckdb

from kiatracker.geo import path_airspeed_sq, path_headwind
from kiatracker.segments import Segment

T_BASE = 18.0  # °C below which heating draws power
T_COOL = 24.0  # °C above which air conditioning draws power
MIN_KM = 5.0  # shorter drives are too coarse to measure (0.5 % SOC steps)
MIN_STRETCH_KPH = 5.0  # a 5-minute stretch spent mostly parked would make heating per km explode
COLUMNS = (
    "drive_id",
    "start_ts",
    "distance_km",
    "speed_kph",
    "temp_c",
    "wind_kph",
    "headwind_kph",
    "aero",
    "heat",
    "cold",
    "cool",
    "time",
    "climb",
    "regen",
    "kwh_per_100km",
)


def air_density_ratio(temp_c: float) -> float:
    """Air density relative to 15 °C: cold air is denser, so the same airspeed costs more drag."""
    return 288.15 / (273.15 + temp_c)


def physics(speed_kph: float, temp_c: float, airspeed_sq: float) -> dict:
    """Features for a speed, temperature and squared airspeed. Heating, cooling and the time-based load
    (electronics, pumps, and the stop-and-go losses that come with a low average speed) draw power per hour,
    so per km they scale with 1 / speed."""
    return {
        "aero": airspeed_sq * air_density_ratio(temp_c),
        "heat": max(0.0, T_BASE - temp_c) / speed_kph,
        "cold": max(0.0, T_BASE - temp_c),  # per km: a cold battery, tyres and drivetrain lose more
        "cool": max(0.0, temp_c - T_COOL) / speed_kph,
        "time": 1.0 / speed_kph,
    }


def segment_features(segments: list[Segment], distance_km: float) -> dict | None:
    """Distance-weighted features over a drive's stretches, or None unless every stretch has weather.

    Climb and regen are metres per 100 km of the drive (regen negative: descents give energy back).
    Unknown terrain counts as flat. Stretches are straight lines between GPS readings, shorter than the road,
    so each one's speed is scaled by the road factor: odometer distance / straight-line total.
    """
    if not segments or any(s.temp_c is None or s.headwind_kph is None for s in segments):
        return None
    total = sum(s.km for s in segments)
    road_factor = distance_km / total if total > 0 else 1.0  # the odometer is the trusted distance
    sums = dict.fromkeys(("aero", "heat", "cold", "cool", "time"), 0.0)
    temp = headwind = 0.0
    for s in segments:
        speed = max(s.speed_kph * road_factor, MIN_STRETCH_KPH)
        x = physics(speed, s.temp_c, (speed + s.headwind_kph) ** 2)
        for name in sums:
            sums[name] += s.km * x[name]
        temp += s.km * s.temp_c
        headwind += s.km * s.headwind_kph
    per_100km = 100 / distance_km
    return {
        "temp_c": temp / total,
        "headwind_kph": headwind / total,
        **{name: value / total for name, value in sums.items()},
        "climb": sum(s.climb_m or 0.0 for s in segments) * per_100km,
        "regen": -sum(s.descent_m or 0.0 for s in segments) * per_100km,
    }


def load_segments(con: duckdb.DuckDBPyConnection) -> dict[int, list[Segment]]:
    try:
        rows = con.execute("select * from drive_segments order by drive_id, seq").fetchall()
    except duckdb.CatalogException:  # a database built before stretches existed
        return {}
    by_drive: dict[int, list[Segment]] = {}
    for values in rows:
        s = Segment(*values)
        by_drive.setdefault(s.drive_id, []).append(s)
    return by_drive


def drive_features(con: duckdb.DuckDBPyConnection) -> list[dict]:
    drives = con.execute(
        """select d.drive_id, d.start_ts, d.end_ts, d.distance_km, d.kwh_per_100km,
                  d.start_lat, d.start_lon, d.end_lat, d.end_lon, w.temp_c, w.wind_kph, w.wind_dir_deg
           from drives d join drive_weather w using (drive_id)
           where not d.in_progress and d.kwh_per_100km is not null and d.distance_km >= ?
             and w.temp_c is not null and w.wind_kph is not null and w.wind_dir_deg is not null
           order by d.start_ts""",
        [MIN_KM],
    ).fetchall()
    located = con.execute(
        "select ts, lat, lon from readings_location where lat is not null order by ts"
    ).fetchall()
    times = [ts for ts, _, _ in located]
    stretches = load_segments(con)

    rows = []
    for drive_id, start, end, km, kwh100, slat, slon, elat, elon, temp, wind, wind_from in drives:
        hours = (end - start).total_seconds() / 3600
        if hours <= 0:
            continue
        inside = located[bisect_left(times, start) : bisect_right(times, end)]
        points = [(slat, slon)] if slat is not None else []
        points += [(lat, lon) for _, lat, lon in inside]
        points += [(elat, elon)] if elat is not None else []
        speed = km / hours
        whole = {
            "temp_c": temp,
            "headwind_kph": path_headwind(points, wind, wind_from),
            **physics(speed, temp, path_airspeed_sq(points, speed, wind, wind_from)),
            "climb": 0.0,
            "regen": 0.0,
        }
        rows.append(
            {
                "drive_id": drive_id,
                "start_ts": start,
                "distance_km": km,
                "speed_kph": speed,
                "wind_kph": wind,
                **(segment_features(stretches.get(drive_id, []), km) or whole),
                "kwh_per_100km": kwh100,
            }
        )
    return rows
