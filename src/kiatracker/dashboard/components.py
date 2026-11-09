"""HTML builders for the Morning sections: data in, an HTML string out, rendered with `st.html`.

No Streamlit import, so every builder is unit-tested. Every interpolated value goes through `e()`; the
class names are styled in `ui.STYLE`, and only data-driven widths and shades are inline.
"""

from html import escape
from typing import Literal

from kiatracker.dashboard import theme

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


COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _wind(direction: float | None, kph: float) -> str:
    if direction is None:
        return f"{kph:.0f} km/h"
    arrow = (
        f'<svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" '
        f'style="transform: rotate({direction + 180:.0f}deg)"><path d="M8 1 L12 11 L8 8.5 L4 11 Z" '
        f'fill="{theme.MUTED}"/></svg>'
    )
    return f"{arrow} {COMPASS[round(direction / 45) % 8]} {kph:.0f} km/h"


def forecast_rows(rows: list[dict], scale_km: float, today) -> str:
    """The Range page's days: weather, a bar split into range / lost to cold / lost to wind, and the range."""

    def pct(km: float) -> str:
        return f"{max(0.0, km) / scale_km * 100:.1f}%"

    out = []
    for r in rows:
        if r["range_km"] is None:
            continue
        is_today = r["day"] == today
        fill = theme.CORAL if is_today else theme.SKY
        cold, wind, mid = r["lost_cold_km"] or 0, r["lost_wind_km"] or 0, r["range_km"]
        cold_label = (
            f'<span class="lbl" style="left: calc({pct(mid)} + 6px)">−{cold:.0f} cold</span>'
            if cold >= 8
            else ""
        )
        wind_label = (
            f'<span class="lbl muted" style="left: calc({pct(mid + cold)} + 6px)">−{wind:.0f}</span>'
            if wind >= 8
            else ""
        )
        out.append(
            f'<div class="wr-day{" today" if is_today else ""}"'
            f"{f' style=background:{theme.TINT_CORAL}' if is_today else ''}>"
            f'<div class="d"><b>{"Today" if is_today else e(r["day"].strftime("%a"))}</b>'
            f"<span>from {r['start_soc']:.0f} %</span></div>"
            f'<div class="w"><span>{SKY_ICONS.get(r["sky"], "")} '
            f"{r['temp_min']:.0f}–{r['temp_max']:.0f} °C</span>"
            f'<span class="muted">{_wind(r["wind_dir_deg"], r["wind_kph"])}</span></div>'
            f'<div class="bar"><i style="width: {pct(mid)}; background: {fill}"></i>'
            f'<i style="left: {pct(mid)}; width: {pct(cold)}; background: {theme.TINT_SKY}"></i>'
            f'<i class="end" style="left: {pct(mid + cold)}; width: {pct(wind)}; '
            f'background: {theme.WASH}"></i>'
            f"{cold_label}{wind_label}</div>"
            f'<div class="r"><b>{mid:.0f} km</b>'
            f"<span>likely {r['range_lo']:.0f}–{r['range_hi']:.0f}</span></div>"
            "</div>"
        )
    legend = "".join(
        f'<span><i style="background: {c}"></i>{n}</span>'
        for n, c in (
            ("Your range", theme.SKY),
            ("Lost to cold", theme.TINT_SKY),
            ("Lost to wind", theme.WASH),
        )
    )
    return (
        f'<div class="wr-days">{"".join(out)}</div><div class="wr-legend"><div>{legend}</div>'
        "<span>full bar = the same charge on a mild, calm day</span></div>"
    )


def rule_line(soc_today: float | None, usual, full: bool) -> str:
    """One sentence saying which charge each day starts from (spec §7)."""
    now = (
        f"Today starts from what is in the battery now ({soc_today:.0f} %). " if soc_today is not None else ""
    )
    if full:
        rest = "The coming days assume a full charge."
    elif usual.assumed:
        rest = (
            "The coming days assume an 80 % charge until there are enough charging sessions to learn yours."
        )
    else:
        habit = (
            f"you stopped at {usual.level} % in {usual.at_level} of your last {usual.sessions} charges"
            if usual.at_level
            else f"you usually stop around {usual.level} %, the middle of your last {usual.sessions} charges"
        )
        rest = f"The coming days assume you charge as usual: {habit}. Switch to 100 % to plan a road trip."
    return f'<p class="wr-note" style="font-size: 14px; margin: 0 0 12px">{e(now + rest)}</p>'


def whatif_result(lo: float, mid: float, hi: float, best_km: float) -> str:
    share = min(100.0, mid / best_km * 100)
    return (
        f'<div class="wr-whatif"><span class="wr-note">On a full battery</span>'
        f'<span class="big">{mid:.0f} km</span><span class="wr-note">likely {lo:.0f}–{hi:.0f} km</span>'
        f'<div class="track"><i style="width: {share:.0f}%"></i></div>'
        '<span class="wr-note" style="font-size: 12px">'
        f"of the EV3's best case, {best_km:.0f} km</span></div>"
    )


def greeting(local_hour: int) -> str:
    if 5 <= local_hour < 12:
        return "Good morning"
    return "Good afternoon" if 12 <= local_hour < 18 else "Good evening"


def wind_words(kph: float) -> str:
    return "a light" if kph < 12 else "a moderate" if kph < 25 else "a strong"


def hero(
    greeting_line: str,
    range_km: float | None,
    lo: float | None,
    hi: float | None,
    soc: float | None,
    comparison: str | None,
) -> str:
    if range_km is None:
        title = "Your range appears once the model has enough drives."
        body = ""
    else:
        title = f'You can drive about <span style="color: {theme.CORAL}">{range_km:.0f} km</span> today.'
        battery = f", from {soc:.0f} % battery" if soc is not None else ""
        body = f"Somewhere between {lo:.0f} and {hi:.0f}{battery}." + (f" {comparison}" if comparison else "")
    return (
        f'<div class="wr-hero"><span class="wr-note" style="font-size: 15px">{e(greeting_line)}</span>'
        f"<h2>{title}</h2><p>{e(body)}</p></div>"
    )


def battery_card(soc: float | None, year_km: float, avg: float | None, saved_ft: float | None) -> str:
    width = 0 if soc is None else max(0.0, min(100.0, soc))
    cells = "".join(
        f'<div><span class="wr-note" style="font-size: 12px">{k}</span><b>{e(v)}</b></div>'
        for k, v in (
            ("This year", f"{year_km:,.0f} km".replace(",", " ")),
            ("Average", "–" if avg is None else f"{avg:.1f} kWh"),
            (
                "Saved",
                "–" if saved_ft is None else f"{round(saved_ft, -3) / 1000:,.0f}k Ft".replace(",", " "),
            ),
        )
    )
    return (
        f'<div class="wr-card wr-battery"><div class="top"><b class="lbl">Battery</b>'
        f'<span class="big">{"–" if soc is None else f"{soc:.0f} %"}</span></div>'
        f'<div class="track"><i style="width: {width:.0f}%"></i></div><div class="cells">{cells}</div></div>'
    )


def week_strip(rows: list[dict], today) -> str:
    cells = []
    for r in rows:
        if r.get("range_km") is None:
            continue
        is_today = r["day"] == today
        style = f' style="background: {theme.TINT_CORAL}"' if is_today else ""
        cells.append(
            f'<div class="day"{style}><span class="wr-note">'
            f"{'Today' if is_today else e(r['day'].strftime('%a'))}"
            f'</span><span aria-hidden="true">{SKY_ICONS.get(r.get("sky"), "")}</span>'
            f'<b>{r["temp_max"]:.0f}°</b><span class="km">{r["range_km"]:.0f}</span>'
            '<span class="wr-note" style="font-size: 11px">km range</span></div>'
        )
    return f'<div class="wr-week">{"".join(cells)}</div>'
