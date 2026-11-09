"""Display helpers shared by the pages: the Morning look (CSS), cards, the demo strip and the period."""

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
[data-testid="stButtonGroup"] {{ background: {t.WASH}; border-radius: 999px; padding: 4px;
                                 width: fit-content; }}
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
.wr-icons .ic {{ flex: none; width: 34px; height: 34px; border-radius: 12px; display: grid;
                 place-items: center; }}
.wr-icons p {{ margin: 0; font-size: 15px; line-height: 1.5; color: {t.INK_SOFT}; }}
.wr-days {{ display: flex; flex-direction: column; gap: 2px; }}
.wr-day {{ display: grid; grid-template-columns: 74px 150px minmax(0, 1fr) 120px; gap: 18px;
           align-items: center;
           padding: 12px 14px; border-radius: 16px; }}
.wr-day .d, .wr-day .w, .wr-day .r {{ display: flex; flex-direction: column; gap: 3px; }}
.wr-day .d span, .wr-day .r span, .wr-day .muted {{ font-size: 12px; color: {t.MUTED}; }}
.wr-day .w .muted {{ display: flex; align-items: center; gap: 5px; font-size: 13px; }}
.wr-day .r {{ align-items: flex-end; }}
.wr-day .r b {{ font-family: "{t.SERIF}", serif; font-weight: 400; font-size: 24px; line-height: 1.1; }}
.wr-day .bar {{ position: relative; height: 26px; }}
.wr-day .bar i {{ position: absolute; top: 4px; height: 18px; left: 0; border-radius: 999px 0 0 999px; }}
.wr-day .bar i + i {{ border-radius: 0; }}
.wr-day .bar i.end {{ border-radius: 0 999px 999px 0; }}
.wr-day .bar .lbl {{ position: absolute; top: 5px; font-size: 11px; color: {t.SKY_INK};
                     white-space: nowrap; }}
.wr-day .bar .lbl.muted {{ color: {t.MUTED}; }}
.wr-legend {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; font-size: 13px;
              color: {t.MUTED}; margin-top: 10px; }}
.wr-legend div {{ display: flex; flex-wrap: wrap; gap: 16px; }}
.wr-legend i {{ display: inline-block; width: 14px; height: 10px; border-radius: 3px; margin-right: 6px; }}
.wr-whatif {{ background: {t.PAPER}; border-radius: 22px; padding: 26px; display: flex;
              flex-direction: column;
              gap: 6px; }}
.wr-whatif .big {{ font-family: "{t.SERIF}", serif; font-size: 64px; line-height: 1; color: {t.CORAL}; }}
.wr-whatif .track {{ height: 10px; border-radius: 999px; background: {t.RULE}; margin-top: 14px; }}
.wr-whatif .track i {{ display: block; height: 100%; border-radius: 999px; background: {t.CORAL}; }}
@media (max-width: 640px) {{
  .wr-day {{ grid-template-columns: 64px minmax(0, 1fr) 90px; }}
  .wr-day .bar {{ grid-column: 1 / -1; order: 4; }}
}}
.wr-hero {{ display: flex; flex-direction: column; gap: 14px; }}
.wr-hero h2 {{ margin: 0; font-family: "{t.SERIF}", serif; font-weight: 400; font-size: 56px;
               line-height: 1.08;
               color: {t.INK}; }}
.wr-hero p {{ margin: 0; font-size: 18px; line-height: 1.6; color: {t.INK_SOFT}; }}
.wr-battery {{ padding: 26px; display: flex; flex-direction: column; gap: 14px; }}
.wr-battery .top {{ display: flex; justify-content: space-between; align-items: baseline; }}
.wr-battery .big {{ font-family: "{t.SERIF}", serif; font-size: 28px; }}
.wr-battery .track {{ height: 14px; border-radius: 999px; background: {t.WASH}; overflow: hidden; }}
.wr-battery .track i {{ display: block; height: 100%; border-radius: 999px;
                        background: linear-gradient(90deg, {t.SKY}, #7FB5DB); }}
.wr-battery .cells {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
.wr-battery .cells div {{ display: flex; flex-direction: column; gap: 2px; }}
.wr-battery .cells b {{ font-family: "{t.SERIF}", serif; font-weight: 400; font-size: 22px; }}
.wr-week {{ display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }}
.wr-week .day {{ display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 14px 6px;
                 border-radius: 16px; }}
.wr-week .day .km {{ font-family: "{t.SERIF}", serif; font-size: 20px; }}
@media (max-width: 640px) {{
  .wr-hero h2 {{ font-size: 38px; }}
  .wr-week {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
}}
.wr-brief {{ background: linear-gradient(135deg, {t.CARD} 0%, #FFF8EC 100%); border-radius: 24px;
              padding: 24px 26px; box-shadow: {t.SHADOW}; display: flex; flex-direction: column; gap: 18px; }}
.wr-brief .head {{ display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap;
                   gap: 8px; }}
.wr-brief .t {{ font-family: "{t.SERIF}", serif; font-size: 22px; }}
.wr-brief .items {{ display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 24px; }}
.wr-brief .item {{ display: flex; gap: 12px; align-items: flex-start; }}
.wr-brief .ic {{ flex: none; width: 36px; height: 36px; border-radius: 12px; display: grid;
                 place-items: center; }}
.wr-brief p {{ margin: 4px 0 0; font-size: 14px; line-height: 1.5; color: {t.INK_SOFT}; }}
.wr-effects {{ display: flex; flex-direction: column; gap: 18px; }}
.wr-effect {{ display: grid; grid-template-columns: 230px minmax(0, 1fr) 64px; gap: 16px;
              align-items: center; }}
.wr-effect > div:first-child {{ display: flex; flex-direction: column; }}
.wr-effect .track {{ height: 16px; background: {t.WASH}; border-radius: 999px; }}
.wr-effect .track i {{ display: block; height: 100%; border-radius: 999px; }}
.wr-effect .v {{ font-family: "{t.SERIF}", serif; font-size: 20px; text-align: right; }}
.wr-grid {{ display: grid; grid-template-columns: 150px repeat(var(--n), minmax(0, 1fr)); gap: 8px; }}
.wr-grid .h {{ text-align: center; font-size: 13px; color: {t.MUTED}; }}
.wr-grid .w {{ font-size: 14px; color: {t.MUTED}; align-self: center; }}
.wr-grid .c {{ border-radius: 14px; padding: 14px 6px; text-align: center; font-family: "{t.SERIF}", serif;
               font-size: 22px; }}
.wr-grid .c span {{ font-family: "{t.SANS}", sans-serif; font-size: 12px; color: {t.MUTED}; }}
.wr-drives {{ display: flex; flex-direction: column; gap: 18px; }}
.wr-drives-day .day {{ display: block; padding-bottom: 6px; }}
.wr-drives-day .row {{ display: grid; grid-template-columns: 56px minmax(0, 1fr) 90px 130px 60px; gap: 12px;
                       align-items: center; padding: 12px 0; border-top: 1px solid {t.RULE}; }}
.wr-drives-day .row .km, .wr-drives-day .row .tag {{ text-align: right; }}
@media (max-width: 640px) {{
  .wr-brief .items {{ grid-template-columns: 1fr; }}
  .wr-effect {{ grid-template-columns: 1fr 56px; }}
  .wr-effect .track {{ grid-column: 1 / -1; order: 3; }}
  .wr-grid {{ grid-template-columns: 80px repeat(var(--n), minmax(0, 1fr)); gap: 4px; }}
  .wr-grid .c {{ font-size: 15px; padding: 10px 2px; }}
  .wr-drives-day .row {{ grid-template-columns: 48px minmax(0, 1fr) 70px; }}
  .wr-drives-day .row .tag, .wr-drives-day .row > :last-child {{ display: none; }}
}}
.wr-charge {{ display: flex; flex-direction: column; gap: 10px; }}
.wr-charge .bat {{ position: relative; height: 44px; border-radius: 999px; background: {t.WASH};
                   overflow: hidden; }}
.wr-charge .bat i {{ position: absolute; top: 0; bottom: 0; left: 0; }}
.wr-charge .bat .before {{ background: #DCE8F3; }}
.wr-charge .bat .added {{ background: linear-gradient(90deg, {t.SKY}, #7FB5DB); }}
.wr-charge .bat span {{ position: absolute; top: 12px; font-size: 14px; color: {t.CARD}; font-weight: 600; }}
.wr-charge .marks {{ position: relative; height: 18px; font-size: 13px; color: {t.MUTED}; }}
.wr-charge .marks span {{ position: absolute; transform: translateX(-50%); white-space: nowrap; }}
.wr-charge .marks span:first-child {{ transform: none; left: 0; }}
.wr-charge .marks .end {{ right: 0; transform: none; }}
.wr-sessions .row {{ display: grid; grid-template-columns: 110px 60px minmax(0, 1fr) 220px 80px 70px;
                     gap: 12px; align-items: center; padding: 12px 0; border-top: 1px solid {t.RULE}; }}
.wr-sessions .soc {{ display: flex; align-items: center; gap: 8px; }}
.wr-sessions .track {{ position: relative; flex: 1; height: 8px; border-radius: 999px;
                       background: {t.WASH}; }}
.wr-sessions .track i {{ position: absolute; top: 0; bottom: 0; border-radius: 999px; }}
.wr-sessions .r {{ text-align: right; }}
@media (max-width: 640px) {{
  .wr-sessions .row {{ grid-template-columns: 90px minmax(0, 1fr) 70px; }}
  .wr-sessions .row > :nth-child(2), .wr-sessions .soc, .wr-sessions .row > :last-child {{ display: none; }}
}}
.wr-savings {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 8px; }}
.wr-savings div {{ display: flex; flex-direction: column; gap: 2px; }}
.wr-savings b {{ font-family: "{t.SERIF}", serif; font-weight: 400; font-size: 28px; }}
.wr-savings b.big {{ font-size: 44px; line-height: 1.1; }}
.wr-compare {{ display: flex; flex-direction: column; gap: 14px; }}
.wr-compare .row {{ display: grid; grid-template-columns: 170px minmax(0, 1fr) 120px; gap: 16px; align-items: center; }}
.wr-compare .row > div:first-child {{ display: flex; flex-direction: column; }}
.wr-compare .track {{ height: 30px; border-radius: 10px; background: {t.PAPER}; }}
.wr-compare .track i {{ display: block; height: 100%; border-radius: 10px; }}
.wr-compare .v {{ font-family: "{t.SERIF}", serif; font-size: 22px; text-align: right; }}
@media (max-width: 640px) {{
  .wr-savings {{ grid-template-columns: 1fr; }}
  .wr-compare .row {{ grid-template-columns: 1fr 90px; }}
  .wr-compare .track {{ grid-column: 1 / -1; order: 3; }}
}}
.wr-routes {{ display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 18px; }}
.wr-route {{ background: {t.CARD}; border-radius: 24px; padding: 20px; box-shadow: {t.SHADOW}; display: flex; flex-direction: column; gap: 8px; }}
.wr-route .head {{ display: flex; align-items: center; gap: 10px; }}
.wr-route .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
.wr-route .wins {{ margin-left: auto; font-size: 13px; color: {t.MUTED}; background: {t.PAPER}; padding: 3px 10px; border-radius: 999px; }}
.wr-route .big {{ font-family: "{t.SERIF}", serif; font-size: 34px; }}
.wr-route > span:not(.big) {{ font-size: 14px; color: {t.INK_SOFT}; }}
@media (max-width: 640px) {{ .wr-routes {{ grid-template-columns: 1fr; }} }}
.wr-callout {{ background: {t.TINT_CORAL}; border-radius: 18px; padding: 20px 22px; font-size: 15px; line-height: 1.55; color: {t.INK_SOFT}; }}
.stFormSubmitButton button p, .stButton button[kind="primary"] p {{ color: {t.CARD}; }}
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
