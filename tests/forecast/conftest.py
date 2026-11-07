import pytest

from kiatracker.dashboard.queries import connect
from kiatracker.dashboard.source import build_demo_database


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    return build_demo_database(tmp_path_factory.mktemp("range-demo"), days=90, seed=21)


@pytest.fixture
def demo(demo_db):
    with connect(demo_db) as con:
        yield con


@pytest.fixture
def empty(tmp_path):
    from kiatracker.config import Settings
    from kiatracker.db import build_database

    settings = Settings(None, None, tmp_path, home=None)
    build_database(settings)
    with connect(settings.db_path) as con:
        yield con
