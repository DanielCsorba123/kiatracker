"""HTML builders for the Morning sections: data in, an HTML string out, rendered with `st.html`.

No Streamlit import, so every builder is unit-tested. Every interpolated value goes through `e()`; the
class names are styled in `ui.STYLE`, and only data-driven widths and shades are inline.
"""

from html import escape
from typing import Literal

from kiatracker.dashboard import theme  # noqa: F401  (tokens, used by the page builders)

SKY_ICONS = {"sun": "☀", "part": "⛅", "cloud": "☁", "rain": "☂"}


def e(value) -> str:
    return escape("" if value is None else str(value))


def fmt_ft(value: float) -> str:
    """Forint rounded to 100, thousands separated by a space: 60 200 Ft."""
    return f"{round(value, -2):,.0f}".replace(",", " ") + " Ft"


def hidden_title(name: str) -> str:
    return f'<h1 class="wr-hidden">{e(name)}</h1>'


def section_title(title: str, note: str = "") -> str:
    side = f'<span class="wr-note">{e(note)}</span>' if note else ""
    return f'<div class="wr-title"><h2>{e(title)}</h2>{side}</div>'


def stat_strip(items: list[tuple[str, str, str | None]]) -> str:
    cells = "".join(
        f'<div class="wr-stat"><span class="k">{e(k)}</span><span class="v">{e(v)}</span>'
        f'<span class="n">{e(n)}</span></div>'
        for k, v, n in items
    )
    return f'<div class="wr-card"><div class="wr-strip" style="--n: {len(items)}">{cells}</div></div>'


def icon_list(items: list[tuple[str, str, str]]) -> str:
    rows = "".join(
        f'<div class="row"><span class="ic" style="background: {e(tint)}" aria-hidden="true">{e(icon)}</span>'
        f"<p>{e(text)}</p></div>"
        for icon, tint, text in items
    )
    return f'<div class="wr-icons">{rows}</div>'


def chip(text: str, tone: Literal["coral", "sky"]) -> str:
    return f'<span class="wr-chip {tone}">{e(text)}</span>'
