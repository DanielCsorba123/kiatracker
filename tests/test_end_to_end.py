from datetime import UTC, datetime

import duckdb
import pytest

from kiatracker.config import Settings
from kiatracker.db import build_database
from kiatracker.synthetic import FAKE_HOME, generate

START = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("demo")
    settings = Settings(None, None, data_dir, home=FAKE_HOME, home_radius_km=0.3)
    truth = generate(settings.raw_dir, START, days=14, seed=7)
    counts = build_database(settings)
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        drives = con.execute(
            "select distance_km, start_zone, end_zone from drives where not in_progress order by start_ts"
        ).fetchall()
        sessions = con.execute("select zone, soc_end from charging_sessions").fetchall()
    return truth, counts, drives, sessions


def test_every_generated_drive_is_found_with_its_distance(built):
    truth, _, drives, _ = built
    assert len(drives) == len(truth) > 14
    for found, expected in zip(drives, truth, strict=True):
        assert found[0] == pytest.approx(expected["distance_km"], abs=0.2)


def test_everyday_drives_start_or_end_at_home(built):
    _, _, drives, _ = built
    touching_home = [d for d in drives if "home" in (d[1], d[2])]
    assert len(touching_home) >= 0.8 * len(drives)  # road-trip stages are the exception


def test_charging_happens_mostly_at_home(built):
    _, counts, _, sessions = built
    assert counts["charging_sessions"] >= 2 and counts["charge_windows"] >= 1
    assert sum(zone == "home" for zone, _ in sessions) >= 0.6 * len(sessions)


def test_a_year_has_seasons_road_trips_fast_charging_and_hills(tmp_path):
    from kiatracker.synthetic import FakeTerrain

    settings = Settings(None, None, tmp_path, home=FAKE_HOME, home_radius_km=0.3)
    generate(settings.raw_dir, datetime(2025, 11, 1, tzinfo=UTC), days=365, seed=7)
    build_database(settings, FakeTerrain())
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        coldest, warmest = con.execute("select min(temp_c), max(temp_c) from drive_weather").fetchone()
        longest = con.execute("select max(distance_km) from drives").fetchone()[0]
        fastest_charge = con.execute(
            "select max(avg_kw) from charging_sessions where zone = 'other'"
        ).fetchone()[0]
        climb = con.execute("select sum(climb_m) from drive_segments").fetchone()[0]
    assert coldest < 0 < 20 < warmest
    assert longest > 80 and fastest_charge > 50 and climb > 10_000


def test_generation_is_reproducible(tmp_path):
    a = generate(tmp_path / "a", START, days=3, seed=1)
    b = generate(tmp_path / "b", START, days=3, seed=1)
    assert a == b


def test_demo_drives_have_weather(tmp_path):
    settings = Settings(None, None, tmp_path, home=FAKE_HOME, home_radius_km=0.3)
    generate(settings.raw_dir, START, days=10, seed=3)
    counts = build_database(settings)
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        located = con.execute("select count(*) from drives where mid_lat is not null").fetchone()[0]
        winds = con.execute("select min(wind_kph), max(wind_kph) from drive_weather").fetchone()
    assert counts["drive_weather"] == located > 0
    assert winds[0] < winds[1]  # wind varies from day to day


def test_demo_charging_habits_vary(tmp_path):
    settings = Settings(None, None, tmp_path, home=FAKE_HOME, home_radius_km=0.3)
    generate(settings.raw_dir, START, days=60, seed=5)
    build_database(settings)
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        ends = {round(e) for (e,) in con.execute("select soc_end from charging_sessions").fetchall()}
        starts = [s for (s,) in con.execute("select soc_start from charging_sessions").fetchall()]
    assert len(ends) >= 2  # owners don't always charge to the same limit
    assert max(starts) - min(starts) > 15


def test_demo_writes_forecast_and_varying_wind_direction(tmp_path):
    from kiatracker.raw import read_records

    generate(tmp_path, START, days=10, seed=2)
    forecasts = list(read_records(tmp_path, "forecast"))
    assert len(forecasts) == 1
    hours = forecasts[0]["body"]["hourly"]["time"]
    assert len(hours) == 72 and hours[0] == "2026-01-15T00:00"  # the 3 days after the simulated ones
    directions = {r["body"]["hourly"]["wind_direction_10m"][0] for r in read_records(tmp_path, "weather")}
    assert len(directions) > 3
