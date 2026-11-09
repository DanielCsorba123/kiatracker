from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from kiatracker.config import Settings
from kiatracker.db import build_database, stats
from rawfactory import battery, driving, location, write

T0 = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
HOME = ("47.5", "19.0")
WORK = ("47.61234", "19.21234")


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def settings(tmp_path) -> Settings:
    return Settings(None, None, tmp_path, home=(47.5, 19.0), home_radius_km=0.3)


def fixture(raw_dir):
    """Charge overnight, drive 12 km to work, charge again."""
    write(
        raw_dir,
        "snapshots",
        [
            battery(at(0), 40.0),
            battery(at(5), 41.0, charging=True),
            battery(at(60), 80.0),
            driving(at(60), 1000.0),
            location(at(60), *HOME),
            battery(at(65), 79.5),
            driving(at(65), 1003.0, ignition_on=True),
            battery(at(70), 78.0),
            driving(at(70), 1012.0),
            location(at(70), *WORK),
            battery(at(300), 78.0, charging=True),
            battery(at(400), 90.0),
        ],
    )


def counts(db_path):
    with duckdb.connect(str(db_path), read_only=True) as con:
        tables = [t for (t,) in con.execute("select table_name from information_schema.tables").fetchall()]
        return {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in tables}


def test_build_creates_all_tables(tmp_path):
    s = settings(tmp_path)
    fixture(s.raw_dir)
    result = build_database(s)
    assert counts(s.db_path) == result
    assert result["drives"] == 1 and result["charging_sessions"] == 2 and result["charge_windows"] == 1
    assert result["readings_battery"] == 7 and result["drive_weather"] == 0
    with duckdb.connect(str(s.db_path), read_only=True) as con:
        row = con.execute("select distance_km, start_zone, end_zone from drives").fetchone()
    assert row == (12.0, "home", "other")


def test_rebuild_is_deterministic(tmp_path):
    s = settings(tmp_path)
    fixture(s.raw_dir)
    first = build_database(s)
    assert build_database(s) == first


def test_build_survives_truncated_raw_line(tmp_path):
    s = settings(tmp_path)
    fixture(s.raw_dir)
    with next(s.raw_dir.glob("snapshots-*.jsonl")).open("a") as f:
        f.write('{"endpoint": "batteries", "body": {"da')
    assert build_database(s)["readings_battery"] == 7


def test_build_with_no_data(tmp_path):
    assert build_database(settings(tmp_path))["drives"] == 0


def test_stats_hides_coordinates(tmp_path):
    s = settings(tmp_path)
    fixture(s.raw_dir)
    build_database(s)
    text = stats(s)
    assert "Drives: 1" in text and "12.0 km" in text
    assert "47.61" not in text and "19.21" not in text


def test_build_retries_while_the_database_is_held_open(tmp_path, monkeypatch):
    """On Windows a dashboard reading the file blocks os.replace for a moment."""
    import kiatracker.db as db

    calls = []
    real_replace = db.os.replace

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(db.os, "replace", flaky)
    monkeypatch.setattr(db, "REPLACE_WAIT_S", 0)
    s = settings(tmp_path)
    fixture(s.raw_dir)
    assert build_database(s)["drives"] == 1
    assert len(calls) == 3


def test_build_gives_up_with_a_clear_error(tmp_path, monkeypatch):
    import kiatracker.db as db

    def locked(src, dst):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(db.os, "replace", locked)
    monkeypatch.setattr(db, "REPLACE_WAIT_S", 0)
    s = settings(tmp_path)
    with pytest.raises(RuntimeError, match="in use"):
        build_database(s)


def test_latest_forecast_becomes_an_hourly_table_without_location(tmp_path):
    from kiatracker.raw import append_record

    s = settings(tmp_path)
    fixture(s.raw_dir)
    for n, temp in enumerate((1.0, 5.0)):  # two fetches: only the latest counts
        hourly = {
            "time": ["2026-11-03T00:00", "2026-11-03T01:00"],
            "temperature_2m": [temp, temp],
            "wind_speed_10m": [10.0, 12.0],
            "wind_direction_10m": [200.0, 210.0],
        }
        record = {
            "fetched_at": at(n).isoformat(),
            "endpoint": "open-meteo-forecast",
            "key": {"lat": 47.6, "lon": 19.2},
            "http_status": 200,
            "body": {"hourly": hourly},
        }
        append_record(s.raw_dir, "forecast", record, at(n))
    assert build_database(s)["forecast_hourly"] == 2
    with duckdb.connect(str(s.db_path), read_only=True) as con:
        columns = [
            c
            for (c,) in con.execute(
                "select column_name from information_schema.columns where table_name = 'forecast_hourly'"
            ).fetchall()
        ]
        temps = {t for (t,) in con.execute("select temp_c from forecast_hourly").fetchall()}
    assert columns == ["ts", "temp_c", "wind_kph", "wind_dir_deg", "cloud_pct", "rain_prob_pct"]
    assert temps == {5.0}


def test_forecast_hours_read_cloud_and_rain_when_present(tmp_path):
    from kiatracker.db import forecast_hours
    from kiatracker.raw import append_record

    hourly = {
        "time": ["2026-11-03T00:00"],
        "temperature_2m": [1.0],
        "wind_speed_10m": [5.0],
        "wind_direction_10m": [90.0],
        "cloud_cover": [80.0],
        "precipitation_probability": [40.0],
    }
    record = {
        "fetched_at": at(0).isoformat(),
        "endpoint": "open-meteo-forecast",
        "key": {},
        "http_status": 200,
        "body": {"hourly": hourly},
    }
    append_record(tmp_path, "forecast", record, at(0))
    [row] = forecast_hours(tmp_path)
    assert (row.cloud_pct, row.rain_prob_pct) == (80.0, 40.0)
