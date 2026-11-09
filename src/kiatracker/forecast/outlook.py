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
HOURLY = (
    "temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,cloud_cover,precipitation_probability"
)
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
    """Fetch 7 days of hourly forecast for a ~10 km cell, store it as a raw record, return the status."""
    lat, lon = round(cell[0], 1), round(cell[1], 1)
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": HOURLY,
        "wind_speed_unit": "kmh",
        "timezone": "UTC",
        "forecast_days": 7,
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


MILD_C = 20.0  # the reference day for "lost to cold": mild and calm


def sky(cloud_pct: float | None, rain_prob_pct: float | None) -> str:
    """One of rain, cloud, part, sun, for the day's icon. Missing values count as zero."""
    if (rain_prob_pct or 0) >= 50:
        return "rain"
    cloud = cloud_pct or 0
    return "cloud" if cloud >= 70 else "part" if cloud >= 30 else "sun"


def _circular_mean(degrees: list[float]) -> float | None:
    if not degrees:
        return None
    rad = np.radians(degrees)
    return float(np.degrees(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360)


def daily_outlook(
    hourly: dict,
    model: RangeModel,
    soc_today: float | None,
    usual_soc: float | None,
    capacity_kwh: float | None,
    speed_kph: float,
    today: date,
) -> list[dict]:
    """One row per local day from today: daytime weather and the range it allows.

    Today starts from the battery's latest reading; later days from `usual_soc`, the level you usually
    charge to. Each day's loss against a mild, calm day is split in a fixed order, cold first:
    A = 20 °C and calm, B = the day's temperature and calm, C = the day's temperature and wind;
    lost to cold = A − B, lost to wind = B − C, and the range is C.
    """
    days: dict[date, list[int]] = {}
    for i, stamp in enumerate(hourly.get("time") or []):
        local = datetime.fromisoformat(stamp).replace(tzinfo=UTC).astimezone(LOCAL)
        if local.hour in DAYTIME and local.date() >= today:
            days.setdefault(local.date(), []).append(i)

    def values(name: str, idx: list[int]) -> list[float]:
        column = hourly.get(name) or []
        return [column[i] for i in idx if i < len(column) and column[i] is not None]

    rows = []
    for day, idx in sorted(days.items()):
        temps, winds = values("temperature_2m", idx), values("wind_speed_10m", idx)
        if not temps or not winds:
            continue
        temp, wind = float(np.mean(temps)), float(np.mean(winds))
        soc = soc_today if day == today else usual_soc
        lo, mid, hi = range_interval(model, soc, capacity_kwh, speed_kph, temp, wind)
        mild = range_interval(model, soc, capacity_kwh, speed_kph, MILD_C, 0.0)[1]
        calm = range_interval(model, soc, capacity_kwh, speed_kph, temp, 0.0)[1]
        cold_loss = wind_loss = None
        if None not in (mid, mild, calm):
            cold_loss, wind_loss = max(0.0, mild - calm), max(0.0, calm - mid)
            mild = mid + cold_loss + wind_loss  # model noise can't make the parts disagree
        clouds, rain = values("cloud_cover", idx), values("precipitation_probability", idx)
        rows.append(
            {
                "day": day,
                "temp_c": temp,
                "temp_min": min(temps),
                "temp_max": max(temps),
                "wind_kph": wind,
                "wind_dir_deg": _circular_mean(values("wind_direction_10m", idx)),
                "sky": sky(float(np.mean(clouds)) if clouds else None, max(rain) if rain else None),
                "start_soc": soc,
                "range_lo": lo,
                "range_km": mid,
                "range_hi": hi,
                "mild_km": mild,
                "lost_cold_km": cold_loss,
                "lost_wind_km": wind_loss,
            }
        )
    return rows
