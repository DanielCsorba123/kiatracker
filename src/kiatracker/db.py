"""Rebuild the DuckDB database from raw files, and summarise it.

Every build starts from scratch: raw files are the source of truth, so there is no incremental state to
corrupt. Timestamps are stored as naive UTC (`TIMESTAMP`); columns ending in `_ts` are UTC.
"""

import dataclasses
import os
import time
import types
import typing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from kiatracker.config import Settings
from kiatracker.elevation import Terrain
from kiatracker.forecast.outlook import latest_forecast
from kiatracker.forecast.specs import usable_kwh
from kiatracker.gold import (
    ChargeWindow,
    ChargingSession,
    Drive,
    derive_charge_windows,
    derive_charging_sessions,
    derive_drives,
)
from kiatracker.model import (
    ApiTrip,
    BatteryReading,
    DrivingReading,
    LocationReading,
    RangeReading,
    Readings,
    StatusReading,
)
from kiatracker.prices import load_fuel_prices
from kiatracker.segments import Segment, all_segments
from kiatracker.silver import load_readings
from kiatracker.weather import DriveWeather, load_weather, weather_for_drive

DEFAULT_CAPACITY_KWH = 81.4  # EV3 Long Range gross, used only if no reading reports it
INSERT_BATCH = 500
REPLACE_TRIES = 20
REPLACE_WAIT_S = 0.5  # on Windows a reader (e.g. the dashboard) blocks replacing the file for a moment
LOCAL_TZ = ZoneInfo("Europe/Budapest")
SQL_TYPES = {datetime: "TIMESTAMP", float: "DOUBLE", int: "BIGINT", bool: "BOOLEAN", str: "VARCHAR"}


@dataclass(frozen=True)
class ForecastHour:
    ts: datetime
    temp_c: float | None
    wind_kph: float | None
    wind_dir_deg: float | None


@dataclass(frozen=True)
class FuelWeek:
    week: str
    at_petrol_eur: float
    at_diesel_eur: float
    hu_petrol_eur: float
    hu_diesel_eur: float
    huf_per_eur: float
    hu_petrol_huf: float
    hu_diesel_huf: float


def forecast_hours(raw_dir: Path) -> list[ForecastHour]:
    """The latest fetched forecast as rows; the grid cell it was fetched for is deliberately left out."""
    hourly = latest_forecast(raw_dir) or {}

    def column(name: str) -> list:
        return hourly.get(name) or [None] * len(hourly.get("time") or [])

    return [
        ForecastHour(datetime.fromisoformat(t).replace(tzinfo=UTC), temp, wind, direction)
        for t, temp, wind, direction in zip(
            hourly.get("time") or [],
            column("temperature_2m"),
            column("wind_speed_10m"),
            column("wind_direction_10m"),
            strict=True,
        )
    ]


def sql_type(annotation) -> str:
    if isinstance(annotation, types.UnionType):  # e.g. float | None
        annotation = next(a for a in typing.get_args(annotation) if a is not type(None))
    return SQL_TYPES[annotation]


def to_sql(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def write_table(con: duckdb.DuckDBPyConnection, name: str, cls: type, rows: list) -> int:
    hints = typing.get_type_hints(cls)
    fields = [f.name for f in dataclasses.fields(cls)]
    con.execute(f"create table {name} ({', '.join(f'"{f}" {sql_type(hints[f])}' for f in fields)})")
    row_sql = "(" + ", ".join("?" for _ in fields) + ")"
    for i in range(0, len(rows), INSERT_BATCH):  # multi-row inserts: executemany is row by row
        batch = rows[i : i + INSERT_BATCH]
        params = [to_sql(getattr(row, f)) for row in batch for f in fields]
        con.execute(f"insert into {name} values {', '.join([row_sql] * len(batch))}", params)
    return len(rows)


def derive_all(settings: Settings) -> tuple[Readings, list[Drive], list[ChargingSession], list[ChargeWindow]]:
    r = load_readings(settings.raw_dir)
    capacities = [b.capacity_kwh for b in r.battery if b.capacity_kwh]
    capacity = usable_kwh(capacities[-1] if capacities else DEFAULT_CAPACITY_KWH)  # 0-100 % spans usable
    drives = derive_drives(r, capacity, settings.home, settings.home_radius_km)
    sessions = derive_charging_sessions(r, capacity, settings.home, settings.home_radius_km)
    return r, drives, sessions, derive_charge_windows(sessions, drives, capacity)


def replace_when_free(src: Path, dst: Path) -> None:
    for _ in range(REPLACE_TRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            time.sleep(REPLACE_WAIT_S)
    raise RuntimeError(f"{dst} is in use by another program; the new build is left in {src}")


def build_database(settings: Settings, terrain=None) -> dict[str, int]:
    """Rebuild every table from raw files. `terrain` defaults to the SRTM tiles in the data folder."""
    r, drives, sessions, windows = derive_all(settings)
    weather = load_weather(settings.raw_dir)
    drive_weather = [w for d in drives if (w := weather_for_drive(d, weather))]
    segments = all_segments(drives, r.location, weather, terrain or Terrain(settings.dem_dir, download=None))

    tables = [
        ("readings_battery", BatteryReading, r.battery),
        ("readings_driving", DrivingReading, r.driving),
        ("readings_location", LocationReading, r.location),
        ("readings_status", StatusReading, r.status),
        ("readings_range", RangeReading, r.range),
        ("api_trips", ApiTrip, r.api_trips),
        ("drives", Drive, drives),
        ("charging_sessions", ChargingSession, sessions),
        ("charge_windows", ChargeWindow, windows),
        ("drive_weather", DriveWeather, drive_weather),
        ("drive_segments", Segment, segments),
        ("forecast_hourly", ForecastHour, forecast_hours(settings.raw_dir)),
        ("fuel_prices", FuelWeek, [FuelWeek(**w) for w in load_fuel_prices(settings.raw_dir)]),
    ]
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    tmp = settings.db_path.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    with duckdb.connect(str(tmp)) as con:
        result = {name: write_table(con, name, cls, rows) for name, cls, rows in tables}
    replace_when_free(tmp, settings.db_path)
    return result


def local(ts: datetime) -> str:
    return ts.replace(tzinfo=UTC).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def fmt(value, spec: str = ".1f", missing: str = "-") -> str:
    return missing if value is None else format(value, spec)


def stats(settings: Settings) -> str:
    """A plain-text summary with zones instead of coordinates, safe to paste anywhere."""
    if not Path(settings.db_path).exists():
        return "No database yet: run `kiatracker build`."
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        one = lambda sql: con.execute(sql).fetchone()  # noqa: E731
        n, km, first, last = one("select count(*), sum(distance_km), min(start_ts), max(end_ts) from drives")
        energy, km_measured = one(
            "select sum(energy_kwh), sum(distance_km) from drives where kwh_per_100km is not null"
        )
        sessions, charged = one(
            "select count(*), sum(energy_kwh) from charging_sessions where not in_progress"
        )
        soc, soc_ts = one("select soc, ts from readings_battery order by ts desc limit 1") or (None, None)
        recent = con.execute(
            """select d.start_ts, d.distance_km, d.kwh_per_100km, d.start_zone, d.end_zone,
                      w.temp_c, w.wind_kph
               from drives d left join drive_weather w using (drive_id)
               order by d.start_ts desc limit 5"""
        ).fetchall()

    lines = [f"Drives: {n}, {fmt(km)} km" + (f" ({local(first)} to {local(last)})" if first else "")]
    if km_measured:
        lines.append(
            f"Average consumption (drives of 5 km or more): {energy / km_measured * 100:.1f} kWh/100 km"
        )
    lines.append(f"Charging sessions: {sessions}, {fmt(charged)} kWh into the battery")
    if soc_ts:
        lines.append(f"Latest charge: {fmt(soc)}% at {local(soc_ts)}")
    if recent:
        lines.append("Recent drives (local time, km, kWh/100 km, from -> to, temp C, wind km/h):")
        for start, dist, cons, z1, z2, temp, wind in recent:
            lines.append(
                f"  {local(start)}  {fmt(dist)} km  {fmt(cons)}  {z1 or '?'} -> {z2 or '?'}  "
                f"{fmt(temp)}  {fmt(wind, '.0f')}"
            )
    return "\n".join(lines)
