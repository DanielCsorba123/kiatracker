"""Display helpers shared by the pages: the Morning look (CSS), cards, the demo strip and the period control."""

from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from kiatracker.dashboard import theme as t
from kiatracker.dashboard.queries import Period

MISSING = "–"
BRAND = "Windrose"
TAGLINE = "How far an EV3 really goes, in real weather."
STATIC = Path(__file__).parent / "static"
LOGO = STATIC / "windrose-sun.svg"
TINTS = {"coral": t.TINT_CORAL, "sky": t.TINT_SKY, "sun": t.TINT_SUN, "warm": "#FFF8EC"}

STYLE = f"""
<style>
.stApp {{ background: linear-gradient(180deg, {t.SKY_TOP} 0px, {t.PAPER} 520px) fixed; }}
.stApp, .stApp p, .stApp label {{ color: {t.INK}; }}
h1, h2, h3 {{ font-family: "{t.SERIF}", serif; font-weight: 400; letter-spacing: -0.01em; }}
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebar"] {{ display: none; }}
[data-testid="stHeader"] {{ background: transparent; }}

/* cards: st.container(key="card-…") */
[class*="st-key-card-"] {{ background: {t.CARD}; border-radius: 24px; padding: 26px;
                          box-shadow: {t.SHADOW}; }}
{"".join(f'[class*="st-key-card-tint-{name}"] {{ background: {colour}; }}' for name, colour in TINTS.items())}

/* top navigation as a rounded pill bar */
[data-testid="stTopNavLinkContainer"], .stAppHeader nav {{ background: rgba(255,255,255,0.55);
    border-radius: 999px; padding: 4px; }}
[data-testid="stTopNavLink"] {{ border-radius: 999px; color: {t.MUTED}; }}
[data-testid="stTopNavLink"][aria-current="page"], [data-testid="stTopNavLink"]:has(> [aria-current]) {{
    background: {t.CARD}; color: {t.INK}; box-shadow: 0 1px 4px rgba(29,43,58,0.10); font-weight: 600; }}

/* segmented controls as a wash pill with a white active segment */
[data-testid="stButtonGroup"] {{ background: {t.WASH}; border-radius: 999px; padding: 4px; width: fit-content; }}
[data-testid="stButtonGroup"] button {{ border: 0; border-radius: 999px; background: transparent;
                                        color: {t.MUTED}; }}
[data-testid="stButtonGroup"] button[kind$="Active"] {{ background: {t.CARD}; color: {t.INK};
    box-shadow: 0 1px 3px rgba(29,43,58,0.10); font-weight: 600; }}

/* sliders: wash track, sky fill, white thumb */
[data-testid="stSlider"] [role="slider"] {{ background: {t.CARD}; box-shadow: 0 1px 4px rgba(29,43,58,0.25);
                                            border: 0; }}
[data-testid="stSlider"] [data-baseweb="slider"] > div > div {{ background: {t.WASH}; }}

/* primary buttons: ink pills */
.stButton button[kind="primary"], .stFormSubmitButton button {{ background: {t.INK}; border: 0;
    border-radius: 14px; color: {t.CARD}; padding: 10px 22px; }}

/* demo strip */
.st-key-demo-strip {{ background: {t.TINT_SKY}; border-radius: 16px; padding: 10px 16px; }}
.st-key-demo-strip p {{ font-size: 0.85rem; color: {t.INK_SOFT}; margin: 0; }}

/* HTML components (components.py) */
.wr-title {{ display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px;
             margin-bottom: 12px; }}
.wr-title h2 {{ margin: 0; padding: 0; font-family: "{t.SERIF}", serif; font-weight: 400; font-size: 24px;
                color: {t.INK}; }}
.wr-note {{ font-size: 13px; color: {t.MUTED}; }}
.wr-card {{ background: {t.CARD}; border-radius: 24px; padding: 20px 8px; box-shadow: {t.SHADOW}; }}
.wr-strip {{ display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); }}
.wr-stat {{ display: flex; flex-direction: column; gap: 3px; padding: 4px 18px; }}
.wr-stat + .wr-stat {{ border-left: 1px solid {t.RULE}; }}
.wr-stat .k {{ font-size: 13px; color: {t.MUTED}; }}
.wr-stat .v {{ font-family: "{t.SERIF}", serif; font-size: 28px; color: {t.INK}; }}
.wr-stat .n {{ font-size: 12px; color: {t.MUTED}; }}
.wr-chip {{ font-size: 13px; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }}
.wr-chip.coral {{ background: {t.TINT_CORAL}; color: {t.CORAL_INK}; }}
.wr-chip.sky {{ background: {t.TINT_SKY}; color: {t.SKY_INK}; }}
.wr-icons {{ display: flex; flex-direction: column; gap: 14px; }}
.wr-icons .row {{ display: flex; gap: 12px; align-items: flex-start; }}
.wr-icons .ic {{ flex: none; width: 34px; height: 34px; border-radius: 12px; display: grid; place-items: center; }}
.wr-icons p {{ margin: 0; font-size: 15px; line-height: 1.5; color: {t.INK_SOFT}; }}
.wr-hidden {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);
              white-space: nowrap; }}
@media (max-width: 640px) {{
  .wr-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 14px; }}
  .wr-stat + .wr-stat {{ border-left: 0; }}
}}
</style>
"""


def inject_style() -> None:
    st.markdown(STYLE, unsafe_allow_html=True)


def card(key: str, *, tint: str | None = None):
    """A Morning card: a keyed container the CSS styles; `tint` is one of TINTS."""
    return st.container(key=f"card-tint-{tint}-{key}" if tint else f"card-{key}")


def render_html(markup: str) -> None:
    st.html(markup)


def demo_strip(text: str) -> None:
    with st.container(key="demo-strip"):
        st.markdown(text)


def period_label(start: date, end: date, today: date) -> str:
    days = (end - start).days
    if end == today and days in (364, 365, 366):
        return "This year"
    if end == today and days in (29, 30, 31):
        return "Last 30 days"
    return f"{start.day} {start:%b} – {end.day} {end:%b}"


def period_control(default_days: int) -> Period:
    """The date range, in a compact popover at the top right of the page."""
    today = date.today()
    st.session_state.setdefault("period", (today - timedelta(days=default_days), today))
    picked = st.session_state["period"]
    start, end = (picked[0], picked[-1]) if isinstance(picked, tuple) and picked else (today, today)
    _, right = st.columns([5, 1])
    with right.popover(period_label(start, end, today), use_container_width=True):
        st.date_input("Period", key="period", max_value=today)
        st.caption("Times are local (Europe/Budapest). Places are shown as home / other only.")
    return Period(start, end)


def page_header(title: str, lede: str) -> None:
    st.title(title)
    st.markdown(f"<p style='color:{t.MUTED}'>{lede}</p>", unsafe_allow_html=True)


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
