"""Display helpers shared by the pages: the Windrose identity, page headers and stat cards."""

from pathlib import Path

import streamlit as st

MISSING = "–"
BRAND = "Windrose"
TAGLINE = "How far an EV3 really goes, in real weather."
LOGO = Path(__file__).parent / "static" / "windrose.svg"

# Colours here are either the brand blue or opacity on the theme's own text colour, so the same CSS
# reads well in the light and the dark theme.
STYLE = """
<style>
.wr-eyebrow { color: #2a78d6; font-weight: 600; font-size: 0.72rem; letter-spacing: 0.16em;
              text-transform: uppercase; margin-bottom: -0.6rem; }
.wr-lede { opacity: 0.68; font-size: 1.05rem; margin-top: -0.4rem; margin-bottom: 1.2rem; }
h1 { letter-spacing: -0.025em; }
h2, h3 { letter-spacing: -0.015em; }
[data-testid="stMetricLabel"] { opacity: 0.72; }
[data-testid="stMetricValue"] { letter-spacing: -0.02em; font-family: "Space Grotesk", sans-serif; }
.wr-brand { font-family: "Space Grotesk", sans-serif; font-weight: 700; font-size: 1.25rem;
            letter-spacing: -0.02em; margin: 0; }
.wr-tagline { opacity: 0.65; font-size: 0.85rem; margin-top: 0.1rem; }
</style>
"""


def inject_style() -> None:
    st.markdown(STYLE, unsafe_allow_html=True)


def sidebar_brand() -> None:
    st.logo(str(LOGO), size="large")
    st.sidebar.divider()
    st.sidebar.markdown(
        f'<p class="wr-brand">{BRAND}</p><p class="wr-tagline">{TAGLINE}</p>', unsafe_allow_html=True
    )


def page_header(title: str, lede: str) -> None:
    st.markdown(f'<p class="wr-eyebrow">{BRAND}</p>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<p class="wr-lede">{lede}</p>', unsafe_allow_html=True)


def number(value: float | None, unit: str = "", digits: int = 0) -> str:
    if value is None:
        return MISSING
    return f"{value:,.{digits}f}{' ' + unit if unit else ''}"


def tiles(items: list[tuple[str, str, str | None]]) -> None:
    """A row of stat cards: (label, formatted value, help text)."""
    for column, (label, value, help_text) in zip(st.columns(len(items)), items, strict=True):
        column.container(border=True).metric(label, value, help=help_text)


def empty(message: str = "No data in this period yet.") -> None:
    st.info(message, icon=":material/hourglass_empty:")
