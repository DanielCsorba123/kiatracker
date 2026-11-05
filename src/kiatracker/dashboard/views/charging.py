import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty, number, page_header, tiles

FULL = 95  # sessions ending at or above this count as charging to full


def render(con, period: queries.Period) -> None:
    page_header("Charging", "When the car charges, how much, and how full.")
    sessions = queries.charging_sessions(con, period)
    if sessions.empty:
        empty("No finished charging sessions in this period yet.")
        return

    tiles(
        [
            ("Sessions", number(len(sessions)), None),
            (
                "Energy charged",
                number(sessions["energy_kwh"].sum(), "kWh"),
                "Into the battery, before losses.",
            ),
            ("Average power", number(sessions["avg_kw"].mean(), "kW", 1), None),
            (
                "Charged to full",
                f"{(sessions['soc_end'] >= FULL).mean():.0%}",
                f"Share of sessions ending at {FULL} % or more. "
                "Daily charging to a lower limit is gentler on the battery.",
            ),
        ]
    )

    st.altair_chart(
        charts.bar(
            queries.weekly_charging(con, period), "week:T", "energy_kwh:Q", "Energy charged per week", "kWh"
        ),
        width="stretch",
    )
    left, right = st.columns(2)
    left.altair_chart(
        charts.histogram(sessions, "soc_start", "Battery % when plugged in", 10, "Battery %", (0, 100)),
        width="stretch",
    )
    right.altair_chart(
        charts.histogram(sessions, "soc_end", "Battery % when charging stopped", 10, "Battery %", (0, 100)),
        width="stretch",
    )

    st.subheader("All sessions")
    st.dataframe(
        sessions,
        hide_index=True,
        width="stretch",
        column_config={
            "start_local": st.column_config.DatetimeColumn("Start", format="YYYY-MM-DD HH:mm"),
            "zone": "Where",
            "soc_start": st.column_config.NumberColumn("From %", format="%.1f"),
            "soc_end": st.column_config.NumberColumn("To %", format="%.1f"),
            "energy_kwh": st.column_config.NumberColumn("kWh", format="%.1f"),
            "hours": st.column_config.NumberColumn("Hours", format="%.1f"),
            "avg_kw": st.column_config.NumberColumn("Avg kW", format="%.1f"),
        },
    )
