from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[2] / "src" / "kiatracker" / "dashboard" / "app.py")
PAGES = ["overview", "drives", "charging", "costs", "range"]


def render_page(page: str, db: str):
    import importlib
    from datetime import date, timedelta

    from kiatracker.dashboard.queries import Period, connect

    module = importlib.import_module(f"kiatracker.dashboard.views.{page}")
    with connect(db) as con:
        module.render(con, Period(date.today() - timedelta(days=400), date.today()))


def run_page(page: str, db) -> AppTest:
    return AppTest.from_function(render_page, kwargs={"page": page, "db": str(db)}, default_timeout=30).run()


@pytest.fixture
def listen(monkeypatch):
    """Set the server address the app sees, as `--server.address` would."""
    import streamlit

    def set_address(address):
        monkeypatch.setattr(
            streamlit,
            "get_option",
            lambda key, real=streamlit.get_option: address if key == "server.address" else real(key),
        )

    return set_address


def test_without_opt_in_the_app_shows_demo(monkeypatch):
    monkeypatch.delenv("KIATRACKER_PERSONAL", raising=False)
    monkeypatch.delenv("KIATRACKER_DEMO", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Simulated data" in info.value for info in at.info)
    assert at.title[0].value == "Overview"


def test_personal_mode_refuses_when_reachable_from_the_network(monkeypatch, tmp_path, listen):
    monkeypatch.setenv("KIATRACKER_PERSONAL", "1")
    monkeypatch.delenv("KIATRACKER_DEMO", raising=False)
    monkeypatch.setenv("KIATRACKER_DATA_DIR", str(tmp_path))
    listen("0.0.0.0")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert any("127.0.0.1" in error.value for error in at.error)
    assert not at.title


def test_personal_mode_without_database_shows_build_hint(monkeypatch, tmp_path, listen):
    monkeypatch.setenv("KIATRACKER_PERSONAL", "1")
    monkeypatch.delenv("KIATRACKER_DEMO", raising=False)
    monkeypatch.setenv("KIATRACKER_DATA_DIR", str(tmp_path))
    listen("127.0.0.1")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("kiatracker build" in warning.value for warning in at.warning)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_demo_data(page, demo_db):
    at = run_page(page, demo_db)
    assert not at.exception
    assert at.title[0].value == page.capitalize()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_empty_database(page, empty_db_path):
    at = run_page(page, empty_db_path)
    assert not at.exception
    assert at.info, "an empty-state message is shown"


def test_range_page_with_too_few_drives_says_how_many_more(tmp_path):
    from kiatracker.dashboard.source import build_demo_database

    at = run_page("range", build_demo_database(tmp_path, days=3))
    assert not at.exception
    assert any("more drives" in info.value for info in at.info)


def test_range_training_fingerprint_tracks_the_data(demo_db, empty_db_path):
    from kiatracker.dashboard.queries import connect
    from kiatracker.dashboard.views.range import fingerprint

    with connect(demo_db) as a, connect(demo_db) as b, connect(empty_db_path) as c:
        assert fingerprint(a) == fingerprint(b) != fingerprint(c)


def test_cloud_entry_point_always_shows_demo(monkeypatch):
    monkeypatch.setenv("KIATRACKER_PERSONAL", "1")  # even if someone sets it on the host
    monkeypatch.delenv("KIATRACKER_DEMO", raising=False)  # the entry point sets it; restored afterwards
    entry = str(Path(APP).parent / "streamlit_app.py")
    at = AppTest.from_file(entry, default_timeout=120).run()
    assert not at.exception
    assert any("Simulated data" in info.value for info in at.info)
