import tomllib
from pathlib import Path

from kiatracker.dashboard import charts, theme

CONFIG = Path(__file__).parents[2] / ".streamlit" / "config.toml"


def test_light_theme_only():
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]
    assert config["base"] == "light" and "dark" not in config
    assert config["font"] == "Hanken Grotesk" and config["headingFont"] == "Young Serif"


def test_contrast_matches_wcag_reference():
    assert round(theme.contrast("#000000", "#FFFFFF"), 1) == 21.0
    assert round(theme.contrast("#777777", "#FFFFFF"), 2) == 4.48


def test_text_inks_pass_aa_and_fills_pass_large_text():
    for ink in (theme.INK, theme.INK_SOFT, theme.MUTED, theme.CORAL_INK, theme.SKY_INK):
        for bg in (theme.CARD, theme.PAPER):
            assert theme.contrast(ink, bg) >= 4.5, ink
    for fill in (theme.CORAL, theme.SKY):
        assert theme.contrast(fill, theme.CARD) >= 3.0  # fills and ≥24 px numbers only; see spec 2.1


def test_fonts_are_self_hosted():
    text = CONFIG.read_text(encoding="utf-8")
    assert "googleapis" not in text and "app/static/young-serif.woff2" in text
    static = Path(charts.__file__).parent / "static"
    assert (static / "young-serif.woff2").exists() and (static / "hanken-grotesk-var.woff2").exists()


def test_charts_use_theme_tokens():
    assert charts.MUTED == theme.MUTED


def test_no_folder_named_pages_next_to_the_app():
    """Streamlit treats a pages/ folder beside the entry script as legacy pages, bypassing navigation."""
    app_dir = Path(__file__).parents[2] / "src" / "kiatracker" / "dashboard"
    assert not (app_dir / "pages").exists()
