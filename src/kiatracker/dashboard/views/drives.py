from dataclasses import dataclass

import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty


@dataclass(frozen=True)
class Factor:
    column: str
    heading: str
    axis: str
    bands: list[float]
    unit: str
    needs_weather: bool


FACTORS = [
    Factor("temp_c", "Temperature", "Outside temperature (°C)", [-30, 0, 5, 10, 15, 45], "°C", True),
    Factor("wind_kph", "Wind", "Wind speed (km/h)", [0, 10, 20, 30, 100], "km/h", True),
    Factor("distance_km", "Trip length", "Trip length (km)", [5, 10, 20, 40, 1000], "km", False),
    Factor("speed_kph", "Average speed", "Average speed (km/h)", [0, 30, 50, 70, 90, 200], "km/h", False),
]


def band_caption(bands, unit: str) -> str | None:
    """How much the most expensive range used compared with the cheapest, if there are at least two."""
    if len(bands) < 2:
        return None
    high, low = bands.loc[bands["kwh_per_100km"].idxmax()], bands.loc[bands["kwh_per_100km"].idxmin()]
    extra = high["kwh_per_100km"] / low["kwh_per_100km"] - 1
    return (
        f"Drives at {high['band']} {unit} used {extra:.0%} more energy per km than drives at "
        f"{low['band']} {unit}."
    )


def factor_section(con, period, measured, factor: Factor) -> None:
    st.subheader(factor.heading)
    points = measured.dropna(subset=[factor.column])
    if points.empty:
        empty(
            "No drives with weather yet: `kiatracker refresh` fetches it."
            if factor.needs_weather
            else "No measured drives yet."
        )
        return
    bands = queries.consumption_by_band(con, period, factor.column, factor.bands)
    st.altair_chart(
        charts.points_with_bands(
            points, factor.column, bands, f"Consumption by {factor.heading.lower()}", factor.axis
        ),
        width="stretch",
    )
    caption = "Dots: each drive. Orange lines: average for the range."
    st.caption(f"{caption} {band_caption(bands, factor.unit) or ''}")


def render(con, period: queries.Period) -> None:
    st.title("Drives")
    drives = queries.drives(con, period)
    if drives.empty:
        empty("No drives in this period yet.")
        return
    measured = drives.dropna(subset=["kwh_per_100km"])
    st.caption("Consumption is measured for drives of 5 km or more; shorter ones are too short to measure.")

    for factor in FACTORS:
        factor_section(con, period, measured, factor)

    st.subheader("Combined")
    together = measured.dropna(subset=["temp_c", "wind_kph"])
    if together.empty:
        empty("Needs drives with weather.")
    else:
        st.altair_chart(charts.combined_scatter(together), width="stretch")
        st.caption("Bigger dots are longer trips, darker dots windier days.")

    st.subheader("All drives")
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
        },
    )
