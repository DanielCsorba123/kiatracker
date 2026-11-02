"""Range outlook: how far the current charge goes in the coming days' weather.

The route is unknown, so wind is averaged over all directions: (v + w·cos φ)² averages to v² + w²/2.
Wind therefore always costs range on a round trip, even though a tailwind helps one way.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import numpy as np

from kiatracker.forecast.model import RangeModel
from kiatracker.raw import append_record, read_records

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
LOCAL = ZoneInfo("Europe/Budapest")
DAYTIME = range(8, 20)  # local hours that represent a day's driving


def range_km(soc: float | None, capacity_kwh: float | None, kwh_per_100km: float | None) -> float | None:
    if soc is None or capacity_kwh is None or not kwh_per_100km or kwh_per_100km <= 0:
        return None
    return soc / 100 * capacity_kwh / kwh_per_100km * 100


def round_trip_airspeed_sq(speed_kph: float, wind_kph: float) -> float:
    return speed_kph**2 + wind_kph**2 / 2


def range_interval(model: RangeModel, soc, capacity_kwh, speed_kph, temp_c, wind_kph) -> tuple:
    """(low, expected, high) range in km; low range comes from high consumption."""
    lo, mid, hi = model.interval(speed_kph, temp_c, round_trip_airspeed_sq(speed_kph, wind_kph))
    return range_km(soc, capacity_kwh, hi), range_km(soc, capacity_kwh, mid), range_km(soc, capacity_kwh, lo)


def fetch_forecast(cell: tuple[float, float], raw_dir: Path, http: httpx.Client, now: datetime) -> int:
    """Fetch 3 days of hourly forecast for a ~10 km cell, store it as a raw record, return the status."""
    lat, lon = round(cell[0], 1), round(cell[1], 1)
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": HOURLY,
        "wind_speed_unit": "kmh",
        "timezone": "UTC",
        "forecast_days": 3,
    }
    response = http.get(FORECAST_URL, params=params, timeout=30)
    try:
        body = response.json()
    except ValueError:
        body = {"non_json_body": response.text[:500]}
    record = {
        "fetched_at": now.isoformat(),
        "endpoint": "open-meteo-forecast",
        "key": {"lat": lat, "lon": lon},
        "http_status": response.status_code,
        "body": body,
    }
    append_record(raw_dir, "forecast", record, now)
    return response.status_code


def latest_forecast(raw_dir: Path) -> dict | None:
    """Hourly forecast arrays from the most recent successful fetch."""
    latest = None
    for record in read_records(raw_dir, "forecast"):
        if record.get("http_status") == 200 and (record.get("body") or {}).get("hourly"):
            latest = record
    return latest["body"]["hourly"] if latest else None


def daily_outlook(
    hourly: dict,
    model: RangeModel,
    soc: float | None,
    capacity_kwh: float | None,
    speed_kph: float,
    today: date,
) -> list[dict]:
    """One row per local day from today: daytime mean temperature and wind, and the range they allow."""
    days: dict[date, list[int]] = {}
    for i, stamp in enumerate(hourly.get("time") or []):
        local = datetime.fromisoformat(stamp).replace(tzinfo=UTC).astimezone(LOCAL)
        if local.hour in DAYTIME and local.date() >= today:
            days.setdefault(local.date(), []).append(i)
    rows = []
    for day, idx in sorted(days.items()):
        temps = [hourly["temperature_2m"][i] for i in idx if hourly["temperature_2m"][i] is not None]
        winds = [hourly["wind_speed_10m"][i] for i in idx if hourly["wind_speed_10m"][i] is not None]
        if not temps or not winds:
            continue
        temp, wind = float(np.mean(temps)), float(np.mean(winds))
        lo, mid, hi = range_interval(model, soc, capacity_kwh, speed_kph, temp, wind)
        rows.append(
            {"day": day, "temp_c": temp, "wind_kph": wind, "range_lo": lo, "range_km": mid, "range_hi": hi}
        )
    return rows
