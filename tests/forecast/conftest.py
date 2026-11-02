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
