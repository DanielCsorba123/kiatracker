import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty, number, page_header, tiles


def render(con, period: queries.Period) -> None:
    page_header("Overview", "Distance, efficiency and charging at a glance.")
    k = queries.kpis(con, period)
    tiles(
        [
            ("Distance", number(k["distance_km"], "km"), None),
            ("Drives", number(k["drives"]), None),
            (
                "kWh / 100 km",
                number(k["kwh_per_100km"], digits=1),
                "Distance-weighted over drives of 5 km or more; shorter ones are too short to measure.",
            ),
            (
                "Energy charged",
                number(k["energy_charged_kwh"], "kWh"),
                "Into the battery, before charging losses.",
            ),
            (
                "Battery now",
                number(k["latest_soc"], "%"),
                f"Car's range estimate: {number(k['latest_range_km'], 'km')}",
            ),
        ]
    )

    weekly = queries.weekly(con, period)
    if weekly.empty:
        empty("No drives in this period yet.")
        return
    left, right = st.columns(2)
    left.altair_chart(
        charts.bar(weekly, "week:T", "distance_km:Q", "Distance per week", "km"), width="stretch"
    )
    right.altair_chart(
        charts.line(weekly.dropna(), "week:T", "kwh_per_100km:Q", "Consumption per week", "kWh/100 km"),
        width="stretch",
    )
