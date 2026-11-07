from dataclasses import dataclass

import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty, number, page_header, tiles
from kiatracker.dashboard.views.range import fingerprint
from kiatracker.forecast.scenarios import choose_model, range_grid
from kiatracker.forecast.train import car_state

DEFAULT_CAPACITY_KWH = 81.4
TEMPS = [-10, -5, 0, 5, 10, 15, 20, 25, 30]
WINDS = [0, 10, 20, 30, 40, 50]
SPEEDS = {
    "Town (40 km/h)": 40,
    "Country roads (70 km/h)": 70,
    "Motorway (110 km/h)": 110,
    "Fast motorway (130 km/h)": 130,
}


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


def at_a_glance(measured, drives) -> None:
    best = measured.loc[measured["kwh_per_100km"].idxmin()] if not measured.empty else None
    worst = measured.loc[measured["kwh_per_100km"].idxmax()] if not measured.empty else None
    avg = (measured["energy_kwh"].sum() / measured["distance_km"].sum() * 100) if not measured.empty else None
    tiles(
        [
            ("Drives", number(len(drives)), None),
            ("Distance", number(drives["distance_km"].sum(), "km"), None),
            ("kWh / 100 km", number(avg, digits=1), "Distance-weighted, drives of 5 km or more."),
            (
                "Most efficient",
                number(best["kwh_per_100km"] if best is not None else None, "kWh", 1),
                f"{best['start_local']:%d %b}, {best['distance_km']:.0f} km" if best is not None else None,
            ),
            (
                "Least efficient",
                number(worst["kwh_per_100km"] if worst is not None else None, "kWh", 1),
                f"{worst['start_local']:%d %b}, {worst['distance_km']:.0f} km" if worst is not None else None,
            ),
        ]
    )


def what_changes_consumption(con, period) -> None:
    effects = queries.condition_effects(con, period)
    st.altair_chart(charts.effect_bars(effects), width="stretch")
    st.caption(
        f"Each bar compares your drives in harder conditions with drives in easier ones, energy per km, "
        f"straight from the data. Grey bars need at least {queries.MIN_PER_SIDE} drives on each side."
    )


def range_in_conditions(con) -> None:
    model, source = cached_model(fingerprint(con), con)
    _, capacity = car_state(con)
    speed_name = st.segmented_control("Driving", list(SPEEDS), default="Motorway (110 km/h)")
    speed = SPEEDS[speed_name or "Motorway (110 km/h)"]
    grid = range_grid(model, capacity or DEFAULT_CAPACITY_KWH, speed, TEMPS, WINDS)
    st.altair_chart(charts.range_heatmap(grid, f"Range on a full battery at {speed} km/h"), width="stretch")
    if source == "trained":
        st.caption(
            f"From the model trained on your {model.n_drives} drives. Wind is averaged over all directions."
        )
    else:
        st.caption(
            "Physics from the EV3's specifications: your own model takes over once it predicts "
            "better than "
            "the simple average (see the Range page). Wind is averaged over all directions."
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
    page_header(
        "Drives", "What makes a drive cheap or expensive, and how far the battery goes in any weather."
    )
    drives = queries.drives(con, period)
    if drives.empty:
        empty("No drives in this period yet.")
        return
    measured = drives.dropna(subset=["kwh_per_100km"])
    at_a_glance(measured, drives)
    what_changes_consumption(con, period)
    st.subheader("Range in different conditions")
    range_in_conditions(con)
    if not measured.dropna(subset=["temp_c"]).empty:
        st.altair_chart(charts.drive_log(measured), width="stretch")
        st.caption(
            "Each dot is a drive: higher means more energy per km, bigger means longer, "
            "blue cold, orange warm."
        )
    for_analysts(con, period, measured, drives)
