from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from kiatracker.forecast.features import drive_features
from kiatracker.forecast.model import fit
from kiatracker.forecast.outlook import (
    FORECAST_URL,
    daily_outlook,
    fetch_forecast,
    latest_forecast,
    range_km,
)
from kiatracker.raw import read_records


def test_range_arithmetic():
    assert range_km(50, 80.0, 16.0) == pytest.approx(250)
    assert range_km(None, 80.0, 16.0) is None
    assert range_km(50, None, 16.0) is None
    assert range_km(50, 80.0, 0) is None


def hourly(days=("2026-11-03", "2026-11-04")):
    times = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
    return {
        "time": times,
        "temperature_2m": [2.0] * len(times),
        "wind_speed_10m": [20.0] * len(times),
        "wind_direction_10m": [270.0] * len(times),
        "wind_gusts_10m": [30.0] * len(times),
    }


def test_daily_outlook(demo):
    model = fit(drive_features(demo))
    days = daily_outlook(hourly(), model, soc=80, capacity_kwh=81.4, speed_kph=50, today=date(2026, 11, 3))
    assert [d["day"] for d in days] == [date(2026, 11, 3), date(2026, 11, 4)]
    d = days[0]
    assert d["temp_c"] == 2.0 and d["wind_kph"] == 20.0
    assert d["range_lo"] < d["range_km"] < d["range_hi"]
    consumption = model.predict(50, 2.0, 50**2 + 20**2 / 2)  # unknown route: wind averages to w²/2
    assert d["range_km"] == pytest.approx(range_km(80, 81.4, consumption))


def test_outlook_skips_past_days(demo):
    model = fit(drive_features(demo))
    days = daily_outlook(hourly(), model, 80, 81.4, 50, today=date(2026, 11, 4))
    assert [d["day"] for d in days] == [date(2026, 11, 4)]


def test_no_forecast_no_outlook(tmp_path):
    assert latest_forecast(tmp_path) is None


@respx.mock
def test_fetch_forecast_stores_a_raw_record(tmp_path):
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json={"hourly": hourly()}))
    assert (
        fetch_forecast((47.5, 19.1), tmp_path, httpx.Client(), now=datetime(2026, 11, 3, tzinfo=UTC)) == 200
    )
    params = route.calls.last.request.url.params
    assert (params["latitude"], params["longitude"], params["forecast_days"]) == ("47.5", "19.1", "3")
    [record] = read_records(tmp_path, "forecast")
    assert record["key"] == {"lat": 47.5, "lon": 19.1}
    assert latest_forecast(tmp_path)["time"][0] == "2026-11-03T00:00"
