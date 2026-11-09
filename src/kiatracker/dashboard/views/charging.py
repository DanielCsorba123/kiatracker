"""Charging: how you charge, from where to where, and when."""

import streamlit as st

from kiatracker.dashboard import charts, components, queries
from kiatracker.dashboard.ui import card, empty, number, render_html

FULL = 95  # sessions ending at or above this count as charging to full


def common_bins(values, step: int = 10) -> str:
    """'between 20 and 50 %': the span of the busiest bins that hold at least half the sessions."""
    bins = (values.dropna().clip(upper=99.99) // step * step).value_counts().sort_values(ascending=False)
    if bins.empty:
        return ""
    picked, total = [], bins.sum()
    for edge in bins.index:
        picked.append(edge)
        if sum(bins[p] for p in picked) >= total / 2:
            break
    return f"between {min(picked):.0f} and {min(100, max(picked) + step):.0f} %"


def render(con, period: queries.Period) -> None:
    render_html(components.hidden_title("Charging"))
    sessions = queries.charging_sessions(con, period)
    if sessions.empty:
        empty("No finished charging sessions in this period yet.")
        return

    total = sessions["energy_kwh"].sum()
    home = sessions.loc[sessions["zone"] == "home", "energy_kwh"].sum() / total if total else None
    render_html(
        components.stat_strip(
            [
                ("Sessions", number(len(sessions)), "in this period"),
                ("Energy charged", number(total, "kWh"), "into the battery, before losses"),
                ("At home", "–" if home is None else f"{home:.0%}", "of the energy"),
                (
                    "Charged to full",
                    f"{(sessions['soc_end'] >= FULL).mean():.0%}",
                    f"of sessions ended at {FULL} % or more",
                ),
            ]
        )
    )

    with card("typical"):
        st.html(components.section_title("A typical charge", "median session"))
        st.html(components.typical_charge(sessions["soc_start"].median(), sessions["soc_end"].median()))

    left, right = st.columns(2)
    with left, card("plugin"):
        st.html(components.section_title("Battery when you plug in"))
        chart = charts.histogram(sessions, "soc_start", None, 10, "Battery %", (0, 100), colour=charts.SKY)
        st.altair_chart(chart, width="stretch")
        st.caption(f"Most often {common_bins(sessions['soc_start'])}.")
    with right, card("unplug"):
        st.html(components.section_title("Battery when you stop"))
        chart = charts.histogram(sessions, "soc_end", None, 10, "Battery %", (0, 100), colour=charts.CORAL)
        st.altair_chart(chart, width="stretch")
        st.caption(f"Most often {common_bins(sessions['soc_end'])}.")

    hours = queries.plug_hours(con, period)
    with card("hours"):
        st.html(components.section_title("When you plug in", "hour of the day"))
        st.altair_chart(charts.plug_hours(hours), width="stretch")
        st.caption(components.peak_sentence(hours))

    with card("weekly"):
        st.html(components.section_title("Energy charged per week", "kWh · this week in coral"))
        weekly = queries.weekly_charging(con, period)
        st.altair_chart(
            charts.bar(weekly, "week:T", "energy_kwh:Q", None, "kWh", highlight_last=True), width="stretch"
        )

    with card("sessions"):
        st.html(components.section_title("Latest sessions", "coral = fast charging"))
        st.html(components.session_list(sessions))
        with st.expander("All sessions"):
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
