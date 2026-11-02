import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty, number, tiles


def render(con, period: queries.Period) -> None:
    st.title("Costs")
    st.caption("Enter your own prices; nothing here is stored. Defaults are neutral examples.")
    a, b, c, d, e = st.columns(5)
    currency = a.text_input("Currency", "EUR")
    electricity = b.number_input(f"Electricity ({currency}/kWh)", min_value=0.0, value=0.25, step=0.01)
    petrol = c.number_input(f"Petrol ({currency}/L)", min_value=0.0, value=1.70, step=0.05)
    petrol_use = d.number_input("Petrol car (L/100 km)", min_value=0.0, value=6.5, step=0.5)
    loss = e.number_input("Charging loss (%)", min_value=0.0, max_value=50.0, value=10.0, step=1.0)

    monthly = queries.costs(con, period, electricity, petrol, petrol_use, loss)
    if monthly.empty:
        empty("No drives or charging in this period yet.")
        return
    tiles(
        [
            (
                "Electricity",
                number(monthly["electricity_cost"].sum(), currency),
                "Energy charged, plus losses, at your price.",
            ),
            ("Same distance on petrol", number(monthly["petrol_cost"].sum(), currency), None),
            ("Saved", number(monthly["savings"].sum(), currency), None),
        ]
    )
    st.altair_chart(
        charts.bar(
            monthly, "month:O", "savings:Q", "Saved per month vs a petrol car", currency, x_title="Month"
        ),
        width="stretch",
    )
