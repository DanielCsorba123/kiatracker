import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty

TEMP_BANDS = [-30, 0, 5, 10, 15, 45]
WIND_BANDS = [0, 10, 20, 30, 100]
LENGTH_BANDS = [5, 10, 20, 40, 1000]


def weather_cost_caption(bands) -> str | None:
    """How much more the coldest band used than the mildest, if both have drives."""
    if len(bands) < 2:
        return None
    cold, mild = bands.iloc[0], bands.iloc[-1]
    extra = cold["kwh_per_100km"] / mild["kwh_per_100km"] - 1
    return (
        f"In the coldest band ({cold['band']} °C) the car used {extra:.0%} more energy per km "
        f"than in the mildest ({mild['band']} °C)."
    )


def render(con, period: queries.Period) -> None:
    st.title("Drives")
    drives = queries.drives(con, period)
    measured = drives.dropna(subset=["kwh_per_100km", "temp_c"])
    if drives.empty:
        empty("No drives in this period yet.")
        return

    if not measured.empty:
        st.subheader("Weather")
        left, right = st.columns(2)
        left.altair_chart(
            charts.scatter(
                measured,
                "temp_c:Q",
                "kwh_per_100km:Q",
                "Consumption vs outside temperature",
                "Outside temperature (°C)",
                "kWh/100 km",
                ["start_local:T", "distance_km:Q", "temp_c:Q", "kwh_per_100km:Q"],
            ),
            width="stretch",
        )
        temp = queries.consumption_by_band(con, period, "temp_c", TEMP_BANDS)
        right.altair_chart(
            charts.bar(
                temp, "band:O", "kwh_per_100km:Q", "Consumption by temperature", "kWh/100 km", x_title="°C"
            ),
            width="stretch",
        )
        if caption := weather_cost_caption(temp):
            right.caption(caption)

        left, right = st.columns(2)
        left.altair_chart(
            charts.scatter(
                measured,
                "wind_kph:Q",
                "kwh_per_100km:Q",
                "Consumption vs wind speed",
                "Wind speed (km/h)",
                "kWh/100 km",
                ["start_local:T", "distance_km:Q", "wind_kph:Q", "kwh_per_100km:Q"],
            ),
            width="stretch",
        )
        length = queries.consumption_by_band(con, period, "distance_km", LENGTH_BANDS)
        right.altair_chart(
            charts.bar(
                length, "band:O", "kwh_per_100km:Q", "Consumption by trip length", "kWh/100 km", x_title="km"
            ),
            width="stretch",
        )
    else:
        empty("No drives with both consumption and weather yet: run `kiatracker weather`.")

    st.subheader("All drives")
    st.dataframe(
        drives,
        hide_index=True,
        width="stretch",
        column_config={
            "start_local": st.column_config.DatetimeColumn("Start", format="YYYY-MM-DD HH:mm"),
            "distance_km": st.column_config.NumberColumn("km", format="%.1f"),
            "minutes": st.column_config.NumberColumn("Minutes", format="%.0f"),
            "kwh_per_100km": st.column_config.NumberColumn("kWh/100 km", format="%.1f"),
            "energy_kwh": st.column_config.NumberColumn("kWh", format="%.1f"),
            "temp_c": st.column_config.NumberColumn("°C", format="%.0f"),
            "wind_kph": st.column_config.NumberColumn("Wind km/h", format="%.0f"),
            "start_zone": "From",
            "end_zone": "To",
        },
    )
