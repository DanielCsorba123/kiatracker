import tomllib
from pathlib import Path

from kiatracker.dashboard import charts

CONFIG = Path(__file__).parents[2] / ".streamlit" / "config.toml"


def test_both_light_and_dark_themes_are_defined():
    theme = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]
    assert "base" not in theme  # a fixed base would force one theme; without it the viewer's choice wins
    assert theme["light"]["primaryColor"] and theme["dark"]["primaryColor"]


def test_chart_ink_is_readable_on_light_and_dark_surfaces():
    for color in (charts.INK, charts.REFERENCE):
        assert color not in ("#000000", "#0b0b0b", "#ffffff", "white", "black")


def test_no_folder_named_pages_next_to_the_app():
    """Streamlit treats a pages/ folder beside the entry script as legacy pages, bypassing navigation."""
    app_dir = Path(__file__).parents[2] / "src" / "kiatracker" / "dashboard"
    assert not (app_dir / "pages").exists()
