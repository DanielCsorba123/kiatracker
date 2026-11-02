from datetime import UTC, datetime, timedelta

import duckdb

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
    write(raw_dir, "snapshots", [
        battery(at(0), 40.0), battery(at(5), 41.0, charging=True), battery(at(60), 80.0),
        driving(at(60), 1000.0), location(at(60), *HOME),
        battery(at(65), 79.5), driving(at(65), 1003.0, ignition_on=True),
        battery(at(70), 78.0), driving(at(70), 1012.0), location(at(70), *WORK),
        battery(at(300), 78.0, charging=True), battery(at(400), 90.0),
    ])  # fmt: skip


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
