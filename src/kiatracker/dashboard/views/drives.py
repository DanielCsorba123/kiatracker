from dataclasses import dataclass
from datetime import datetime

import streamlit as st

from kiatracker.dashboard import charts, components, queries
from kiatracker.dashboard.ui import card, empty, number, render_html
from kiatracker.dashboard.views.range import fingerprint
from kiatracker.forecast.outlook import LOCAL
from kiatracker.forecast.scenarios import choose_model, range_grid
from kiatracker.forecast.specs import EV3
from kiatracker.forecast.train import car_state

DEFAULT_CAPACITY_KWH = EV3.usable_kwh
GRID_TEMPS = [-10, 0, 10, 20, 30]
GRID_WINDS = [0, 15, 30]
SPEEDS = {"Town 40": 40, "Country 70": 70, "Motorway 110": 110, "Fast 130": 130}
DEFAULT_SPEED = "Motorway 110"


@dataclass(frozen=True)
class Factor:
    column: str
    heading: str
    axis: str
    bands: list[float]
    unit: str


FACTORS = [
    Factor("temp_c", "Temperature", "Outside temperature (°C)", [-30, 0, 5, 10, 15, 45], "°C"),
    Factor("wind_kph", "Wind", "Wind speed (km/h)", [0, 10, 20, 30, 100], "km/h"),
    Factor("distance_km", "Trip length", "Trip length (km)", [5, 10, 20, 40, 1000], "km"),
    Factor("speed_kph", "Average speed", "Average speed (km/h)", [0, 30, 50, 70, 90, 200], "km/h"),
]


@st.cache_data(max_entries=4, show_spinner=False)
def cached_model(key: tuple, _con):
    return choose_model(_con)


def at_a_glance(measured, drives) -> str:
    best = measured.loc[measured["kwh_per_100km"].idxmin()] if not measured.empty else None
    worst = measured.loc[measured["kwh_per_100km"].idxmax()] if not measured.empty else None
    avg = (measured["energy_kwh"].sum() / measured["distance_km"].sum() * 100) if not measured.empty else None

    def when(row) -> str | None:
        return (
            f"{row['start_local'].day} {row['start_local']:%b} · {row['distance_km']:.0f} km"
            if row is not None
            else None
        )

    return components.stat_strip(
        [
            ("Drives", number(len(drives)), "in this period"),
            ("Distance", number(drives["distance_km"].sum(), "km"), None),
            ("Average", number(avg, "kWh", 1), "per 100 km, drives of 5 km or more"),
            ("Best", number(best["kwh_per_100km"] if best is not None else None, "kWh", 1), when(best)),
            ("Hardest", number(worst["kwh_per_100km"] if worst is not None else None, "kWh", 1), when(worst)),
        ]
    )


def what_changes_consumption(con, period) -> None:
    with card("effects"):
        st.html(
            components.section_title(
                "What makes a drive cost more",
                "your drives in harder conditions vs easier ones, energy per km",
            )
        )
        st.html(components.effect_rows(queries.condition_effects(con, period)))
        st.caption(
            "Straight from your data, no model: each bar compares drives on the two sides. A bar stays grey "
            f"until both sides have at least {queries.MIN_PER_SIDE} drives."
        )


def range_in_conditions(con) -> None:
    model, source = cached_model(fingerprint(con), con)
    _, capacity = car_state(con)
    with card("grid"):
        left, right = st.columns([3, 2], vertical_alignment="center")
        left.html(components.section_title("How far a full battery goes"))
        choice = right.segmented_control(
            "Driving", list(SPEEDS), default=DEFAULT_SPEED, label_visibility="collapsed", key="grid-speed"
        )
        speed = SPEEDS[choice or DEFAULT_SPEED]
        grid = range_grid(model, capacity or DEFAULT_CAPACITY_KWH, speed, GRID_TEMPS, GRID_WINDS)
        st.html(components.range_grid(grid))
        who = (
            f"the model trained on your {model.n_drives} drives"
            if source == "trained"
            else "the EV3's specifications until your own model predicts better (see the Range page)"
        )
        st.caption(
            f"From {who}, at {speed} km/h. Wind is averaged over all directions. "
            f"The EV3 can't beat {EV3.best_range_km:.0f} km even in perfect conditions."
        )


def for_analysts(con, period, measured, drives) -> None:
    with st.expander("For analysts: every drive against each factor, and the full table"):
        for factor in FACTORS:
            points = measured.dropna(subset=[factor.column])
            if points.empty:
                st.caption(f"{factor.heading}: no drives with this value yet.")
                continue
            bands = queries.consumption_by_band(con, period, factor.column, factor.bands)
            st.altair_chart(
                charts.points_with_bands(
                    points, factor.column, bands, f"Consumption by {factor.heading.lower()}", factor.axis
                ),
                width="stretch",
            )
        st.caption("Dots: each drive. Orange lines: distance-weighted average for the range.")
        st.dataframe(
            drives,
            hide_index=True,
            width="stretch",
            column_config={
                "start_local": st.column_config.DatetimeColumn("Start", format="YYYY-MM-DD HH:mm"),
                "distance_km": st.column_config.NumberColumn("km", format="%.1f"),
                "minutes": st.column_config.NumberColumn("Minutes", format="%.0f"),
                "speed_kph": st.column_config.NumberColumn("Avg km/h", format="%.0f"),
                "kwh_per_100km": st.column_config.NumberColumn("kWh/100 km", format="%.1f"),
                "energy_kwh": st.column_config.NumberColumn("kWh", format="%.1f"),
                "temp_c": st.column_config.NumberColumn("°C", format="%.0f"),
                "wind_kph": st.column_config.NumberColumn("Wind km/h", format="%.0f"),
                "start_zone": "From",
                "end_zone": "To",
                "quality": st.column_config.TextColumn(
                    "Quality",
                    help="gap: collector was off, so energy is unknown; implausible: impossible energy",
                ),
            },
        )


def render(con, period: queries.Period) -> None:
    render_html(components.hidden_title("Drives"))
    today = datetime.now(LOCAL).date()
    render_html(
        components.briefing(queries.briefing_facts(con, period, today), f"{today:%A} {today.day} {today:%B}")
    )
    drives = queries.drives(con, period)
    if drives.empty:
        empty("No drives in this period yet.")
        return
    measured = drives.dropna(subset=["kwh_per_100km"])
    render_html(at_a_glance(measured, drives))
    what_changes_consumption(con, period)
    range_in_conditions(con)
    if not measured.empty:
        with card("year"):
            st.html(
                components.section_title(
                    "Every drive", "coral = 19 kWh/100 km or more · line = the seasonal average"
                )
            )
            st.altair_chart(charts.drives_over_year(measured), width="stretch")
    with card("recent"):
        st.html(components.section_title("Recent drives", "every drive is in the full table below"))
        st.html(components.drive_list(queries.recent_drives(con, today)))
    for_analysts(con, period, measured, drives)
