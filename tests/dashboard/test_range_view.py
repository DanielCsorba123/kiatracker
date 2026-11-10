from datetime import UTC, datetime

import duckdb

from kiatracker.dashboard.views.range import forecast_hourly, has_range, weather_now


def hourly_now(temp, wind):
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:00")
    return {"time": [stamp], "temperature_2m": [temp], "wind_speed_10m": [wind]}


def test_weather_now_is_none_when_the_hour_has_a_gap():
    assert weather_now(hourly_now(None, 12.0)) is None
    assert weather_now(hourly_now(5.0, None)) is None
    assert weather_now(hourly_now(5.0, 12.0)) == (5.0, 12.0)


def test_has_range_when_only_later_days_have_one():
    assert has_range([{"range_km": None}, {"range_km": 420.0}])
    assert not has_range([{"range_km": None}]) and not has_range([])


def test_forecast_from_a_database_built_before_cloud_and_rain(tmp_path):
    con = duckdb.connect(str(tmp_path / "old.duckdb"))
    con.execute(
        "create table forecast_hourly (ts timestamp, temp_c double, wind_kph double, wind_dir_deg double)"
    )
    con.execute("insert into forecast_hourly values ('2026-11-09 10:00', 5, 12, 270)")
    h = forecast_hourly(con)
    assert h["temperature_2m"] == [5.0] and h["cloud_cover"] == [None]
