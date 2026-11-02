from datetime import date, timedelta

import duckdb
import pytest

from kiatracker.config import Settings
from kiatracker.dashboard.queries import Period, connect
from kiatracker.dashboard.source import build_demo_database
from kiatracker.db import build_database


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    return build_demo_database(tmp_path_factory.mktemp("demo"), days=60, seed=11)


@pytest.fixture
def demo(demo_db):
    with connect(demo_db) as con:
        yield con


@pytest.fixture
def empty(tmp_path):
    settings = Settings(None, None, tmp_path, home=None)
    build_database(settings)
    with connect(settings.db_path) as con:
        yield con


@pytest.fixture
def all_time():
    return Period(date.today() - timedelta(days=400), date.today())


@pytest.fixture
def tiny(tmp_path):
    """Factory: a hand-made database with two November drives (100 km, 15 kWh) and one 20 kWh charge."""

    def make(consumption: float | None = 15.0):
        path = tmp_path / "tiny.duckdb"
        with duckdb.connect(str(path)) as con:
            con.execute(
                "create table drives (start_ts timestamp, end_ts timestamp, distance_km double, "
                "energy_kwh double, kwh_per_100km double, start_zone varchar, end_zone varchar, "
                "in_progress boolean)"
            )
            for day, km, kwh in ((3, 60, 9), (10, 40, 6)):
                con.execute(
                    "insert into drives values (?, ?, ?, ?, ?, 'home', 'other', false)",
                    [f"2026-11-{day:02d} 08:00", f"2026-11-{day:02d} 09:00", km, kwh, consumption],
                )
            con.execute(
                "create table charging_sessions (start_ts timestamp, zone varchar, soc_start double, "
                "soc_end double, energy_kwh double, hours double, avg_kw double, in_progress boolean)"
            )
            con.execute(
                "insert into charging_sessions values ('2026-11-05 20:00', 'home', 40, 65, 20, 3, 6.7, false)"
            )
        return connect(path)

    return make


@pytest.fixture
def empty_db_path(tmp_path):
    settings = Settings(None, None, tmp_path / "empty", home=None)
    build_database(settings)
    return settings.db_path
