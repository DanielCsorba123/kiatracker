"""One row of physics features per finished drive.

Coordinates are read to work out the direction of travel against the wind, but only derived numbers come out.
"""

from bisect import bisect_left, bisect_right

import duckdb

from kiatracker.geo import path_airspeed_sq, path_headwind

T_BASE = 18.0  # °C below which heating draws power
MIN_KM = 5.0  # shorter drives are too coarse to measure (0.5 % SOC steps)
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
    "kwh_per_100km",
)


def physics(speed_kph: float, temp_c: float, airspeed_sq: float) -> dict:
    """The model's two weather features for a speed, temperature and squared airspeed."""
    return {"aero": airspeed_sq, "heat": max(0.0, T_BASE - temp_c) / speed_kph}


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

    rows = []
    for drive_id, start, end, km, kwh100, slat, slon, elat, elon, temp, wind, wind_from in drives:
        hours = (end - start).total_seconds() / 3600
        if hours <= 0:
            continue
        inside = located[bisect_left(times, start) : bisect_right(times, end)]
        points = [(slat, slon)] if slat is not None else []
        points += [(lat, lon) for _, lat, lon in inside]
        points += [(elat, elon)] if elat is not None else []
        headwind = path_headwind(points, wind, wind_from)
        speed = km / hours
        rows.append(
            {
                "drive_id": drive_id,
                "start_ts": start,
                "distance_km": km,
                "speed_kph": speed,
                "temp_c": temp,
                "wind_kph": wind,
                "headwind_kph": headwind,
                **physics(speed, temp, path_airspeed_sq(points, speed, wind, wind_from)),
                "kwh_per_100km": kwh100,
            }
        )
    return rows
