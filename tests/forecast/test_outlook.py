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
    sky,
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
        "cloud_cover": [50.0] * len(times),
        "precipitation_probability": [10.0] * len(times),
    }


TODAY = date(2026, 11, 3)
WEEK = tuple(f"2026-11-{d:02d}" for d in range(3, 10))


@pytest.fixture
def model(demo):
    return fit(drive_features(demo))


def test_daily_outlook(model):
    days = daily_outlook(hourly(), model, 80, 80, capacity_kwh=81.4, speed_kph=50, today=TODAY)
    assert [d["day"] for d in days] == [date(2026, 11, 3), date(2026, 11, 4)]
    d = days[0]
    assert d["temp_c"] == 2.0 and d["wind_kph"] == 20.0
    assert d["range_lo"] < d["range_km"] < d["range_hi"]
    consumption = model.predict(50, 2.0, 50**2 + 20**2 / 2)  # unknown route: wind averages to w²/2
    assert d["range_km"] == pytest.approx(range_km(80, 81.4, consumption))


def test_outlook_skips_past_days(model):
    days = daily_outlook(hourly(), model, 80, 80, 81.4, 50, today=date(2026, 11, 4))
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
    assert (params["latitude"], params["longitude"], params["forecast_days"]) == ("47.5", "19.1", "7")
    [record] = read_records(tmp_path, "forecast")
    assert record["key"] == {"lat": 47.5, "lon": 19.1}
    assert latest_forecast(tmp_path)["time"][0] == "2026-11-03T00:00"


def test_today_uses_live_soc_later_days_the_usual(model):
    rows = daily_outlook(hourly(WEEK), model, 76, 80, 78.0, 62, TODAY)
    assert len(rows) == 7
    assert rows[0]["start_soc"] == 76 and {r["start_soc"] for r in rows[1:]} == {80}
    assert rows[1]["range_km"] > rows[0]["range_km"]  # same weather, more charge


def test_cold_and_wind_split_adds_up(model):
    for r in daily_outlook(hourly(WEEK), model, 76, 80, 78.0, 62, TODAY):
        assert r["lost_cold_km"] >= 0 and r["lost_wind_km"] >= 0
        assert r["mild_km"] == pytest.approx(r["range_km"] + r["lost_cold_km"] + r["lost_wind_km"])
        assert r["lost_cold_km"] > 0  # 2 °C is well below the mild reference


def test_daily_rows_carry_min_max_direction_and_sky(model):
    h = hourly(WEEK)
    h["temperature_2m"] = [float(i % 24) for i in range(len(h["time"]))]
    r = daily_outlook(h, model, 76, 80, 78.0, 62, TODAY)[0]
    assert (r["temp_min"], r["temp_max"]) == (7.0, 18.0)  # daytime 08-19 local = 07-18 UTC in November
    assert r["wind_dir_deg"] == pytest.approx(270) and r["sky"] == "part"


def test_short_patchy_forecast_gives_the_days_it_can(model):
    patchy = {k: v[: 3 * 24] for k, v in hourly(WEEK).items()}
    patchy["wind_direction_10m"] = [None] * len(patchy["time"])
    del patchy["cloud_cover"]
    rows = daily_outlook(patchy, model, 76, 80, 78.0, 62, TODAY)
    assert 1 <= len(rows) <= 3 and all(r["wind_dir_deg"] is None for r in rows)
    assert all(r["sky"] in ("sun", "part", "cloud", "rain") for r in rows)


def test_sky_rules():
    assert sky(10, 60) == "rain" and sky(80, 0) == "cloud" and sky(40, None) == "part"
    assert sky(None, None) == "sun"
