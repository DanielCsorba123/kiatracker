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


def test_drives_start_or_end_at_home(built):
    _, _, drives, _ = built
    assert all("home" in (start, end) for _, start, end in drives)


def test_charging_happens_at_home(built):
    _, counts, _, sessions = built
    assert counts["charging_sessions"] >= 2 and counts["charge_windows"] >= 1
    assert all(zone == "home" for zone, _ in sessions)


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
