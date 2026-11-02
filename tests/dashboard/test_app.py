from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[2] / "src" / "kiatracker" / "dashboard" / "app.py")
PAGES = ["overview", "drives", "charging", "costs"]


def render_page(page: str, db: str):
    import importlib
    from datetime import date, timedelta

    from kiatracker.dashboard.queries import Period, connect

    module = importlib.import_module(f"kiatracker.dashboard.pages.{page}")
    with connect(db) as con:
        module.render(con, Period(date.today() - timedelta(days=400), date.today()))


def run_page(page: str, db) -> AppTest:
    return AppTest.from_function(render_page, kwargs={"page": page, "db": str(db)}, default_timeout=30).run()


def test_demo_mode_shows_banner_and_overview(monkeypatch):
    monkeypatch.setenv("KIATRACKER_DEMO", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Demo data" in info.value for info in at.info)
    assert at.title[0].value == "Overview"


def test_personal_mode_without_database_shows_build_hint(monkeypatch, tmp_path):
    monkeypatch.delenv("KIATRACKER_DEMO", raising=False)
    monkeypatch.setenv("KIATRACKER_DATA_DIR", str(tmp_path))
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
