from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from kiatracker.gold import Drive
from kiatracker.raw import read_records
from kiatracker.weather import (
    ARCHIVE_URL,
    FORECAST_URL,
    fetch_weather,
    load_weather,
    source_for,
    weather_for_drive,
)

TODAY = date(2026, 11, 2)


def drive(mid_ts: datetime, lat: float | None = 47.53, lon: float | None = 19.07, drive_id: int = 1) -> Drive:
    return Drive(
        drive_id,
        mid_ts,
        mid_ts,
        0,
        10,
        10,
        80,
        78,
        1.6,
        16,
        lat,
        lon,
        lat,
        lon,
        mid_ts,
        lat,
        lon,
        "home",
        "other",
        0,
        2,
        False,
    )


def hourly(day: str) -> dict:
    hours = [f"{day}T{h:02d}:00" for h in range(24)]
    return {
        "hourly": {
            "time": hours,
            "temperature_2m": [float(h) for h in range(24)],
            "wind_speed_10m": [10.0 + h for h in range(24)],
            "wind_direction_10m": [270.0] * 24,
            "wind_gusts_10m": [30.0] * 24,
        }
    }


@respx.mock
def test_old_drive_uses_archive_recent_uses_forecast(tmp_path):
    archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=hourly("2026-10-20")))
    forecast = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=hourly("2026-11-01")))
    drives = [drive(datetime(2026, 10, 20, 9, tzinfo=UTC)), drive(datetime(2026, 11, 1, 9, tzinfo=UTC))]
    assert fetch_weather(drives, tmp_path, httpx.Client(), TODAY) == 2
    params = archive.calls.last.request.url.params
    assert (params["latitude"], params["longitude"], params["start_date"]) == ("47.5", "19.1", "2026-10-20")
    assert params["wind_speed_unit"] == "kmh" and params["timezone"] == "UTC"
    assert forecast.calls.last.request.url.params["start_date"] == "2026-11-01"


@respx.mock
def test_cached_location_and_day_not_fetched_again(tmp_path):
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=hourly("2026-10-20")))
    d = [drive(datetime(2026, 10, 20, 9, tzinfo=UTC))]
    fetch_weather(d, tmp_path, httpx.Client(), TODAY)
    same_area = [drive(datetime(2026, 10, 20, 17, tzinfo=UTC), lat=47.54, lon=19.08)]
    assert fetch_weather(same_area, tmp_path, httpx.Client(), TODAY) == 0


@respx.mock
def test_failed_fetch_is_retried_next_time(tmp_path):
    respx.get(ARCHIVE_URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=hourly("2026-10-20"))]
    )
    d = [drive(datetime(2026, 10, 20, 9, tzinfo=UTC))]
    fetch_weather(d, tmp_path, httpx.Client(), TODAY)
    assert fetch_weather(d, tmp_path, httpx.Client(), TODAY) == 1
    assert len(list(read_records(tmp_path, "weather"))) == 2


def test_drive_without_position_is_skipped(tmp_path):
    assert fetch_weather([drive(datetime(2026, 10, 20, tzinfo=UTC), None, None)], tmp_path, None, TODAY) == 0


@respx.mock
def test_nearest_hour_is_used(tmp_path):
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=hourly("2026-10-20")))
    d = drive(datetime(2026, 10, 20, 9, 40, tzinfo=UTC))
    fetch_weather([d], tmp_path, httpx.Client(), TODAY)
    w = weather_for_drive(d, load_weather(tmp_path))
    assert (w.temp_c, w.wind_kph, w.wind_dir_deg, w.gust_kph) == (10.0, 20.0, 270.0, 30.0)
    assert w.drive_id == 1


def test_no_weather_returns_none():
    assert weather_for_drive(drive(datetime(2026, 10, 20, tzinfo=UTC)), {}) is None


@pytest.mark.parametrize("day,url", [(date(2026, 10, 27), ARCHIVE_URL), (date(2026, 10, 28), FORECAST_URL)])
def test_archive_only_for_days_more_than_five_days_ago(day, url):
    assert source_for(day, TODAY) == url
