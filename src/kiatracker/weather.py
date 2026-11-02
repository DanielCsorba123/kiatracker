"""Hourly weather for each drive from Open-Meteo (free, no key), cached as raw records.

One request covers a whole UTC day at a ~10 km grid cell, so nearby drives on the same day share it.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from kiatracker.gold import Drive
from kiatracker.raw import append_record, read_records

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_DELAY_DAYS = 5  # the reanalysis archive lags real time by a few days
HOURLY = "temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m"

Key = tuple[float, float, str]


@dataclass(frozen=True)
class DriveWeather:
    drive_id: int
    temp_c: float | None
    wind_kph: float | None
    wind_dir_deg: float | None
    gust_kph: float | None


def key_for(drive: Drive) -> Key | None:
    if drive.mid_lat is None or drive.mid_lon is None:
        return None
    return round(drive.mid_lat, 1), round(drive.mid_lon, 1), drive.mid_ts.astimezone(UTC).date().isoformat()


def source_for(day: date, today: date) -> str:
    return ARCHIVE_URL if (today - day).days > ARCHIVE_DELAY_DAYS else FORECAST_URL


def load_weather(raw_dir: Path) -> dict[Key, dict]:
    weather = {}
    for record in read_records(raw_dir, "weather"):
        if record.get("http_status") == 200 and record.get("key"):
            k = record["key"]
            weather[(k["lat"], k["lon"], k["date"])] = record["body"]
    return weather


def fetch_weather(drives: list[Drive], raw_dir: Path, http: httpx.Client | None, today: date) -> int:
    """Fetch every (cell, day) the drives need that is not cached yet. Returns the number of requests made."""
    have = set(load_weather(raw_dir))
    needed = sorted({k for d in drives if (k := key_for(d)) and k not in have})
    for lat, lon, day in needed:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": day,
            "end_date": day,
            "hourly": HOURLY,
            "wind_speed_unit": "kmh",
            "timezone": "UTC",
        }
        response = http.get(source_for(date.fromisoformat(day), today), params=params, timeout=30)
        try:
            body = response.json()
        except ValueError:
            body = {"non_json_body": response.text[:500]}
        now = datetime.now(UTC)
        append_record(
            raw_dir,
            "weather",
            {
                "fetched_at": now.isoformat(),
                "endpoint": "open-meteo",
                "key": {"lat": lat, "lon": lon, "date": day},
                "http_status": response.status_code,
                "body": body,
            },
            now,
        )
    return len(needed)


def weather_for_drive(drive: Drive, weather: dict[Key, dict]) -> DriveWeather | None:
    k = key_for(drive)
    hourly = (weather.get(k) or {}).get("hourly") if k else None
    if not hourly or not hourly.get("time"):
        return None
    target = drive.mid_ts.astimezone(UTC).replace(tzinfo=None)
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    i = min(range(len(times)), key=lambda n: abs(times[n] - target))

    def value(name: str) -> float | None:
        values = hourly.get(name) or []
        return values[i] if i < len(values) else None

    return DriveWeather(
        drive.drive_id,
        value("temperature_2m"),
        value("wind_speed_10m"),
        value("wind_direction_10m"),
        value("wind_gusts_10m"),
    )
