from datetime import date

import pandas as pd
import streamlit as st

from kiatracker.dashboard import charts, components, queries
from kiatracker.dashboard.ui import card, empty, number, render_html
from kiatracker.prices import ELECTRICITY


def assumptions() -> queries.CostAssumptions:
    """Sensible defaults, adjustable in an expander; nothing has to be typed in."""
    default = queries.CostAssumptions()
    with st.expander("Assumptions"):
        a, b, c = st.columns(3)
        band = a.radio(
            "Your electricity price (Hungary)",
            [
                f"Above average consumption: {ELECTRICITY['hu_above_average_huf']:.1f} Ft/kWh",
                f"Within average consumption: {ELECTRICITY['hu_below_average_huf']:.0f} Ft/kWh",
            ],
            help="Hungary's regulated household tariff has a cheaper band up to the average consumption "
            "(2,523 kWh a year) and a dearer one above it. With solar on yearly net metering, the car's kWh "
            "come on top of what the panels cover, so they're billed in the upper band. Check your bill.",
        )
        hu_price = (
            ELECTRICITY["hu_above_average_huf"]
            if band.startswith("Above")
            else ELECTRICITY["hu_below_average_huf"]
        )
        petrol = b.number_input(
            "Petrol car (L/100 km)",
            3.0,
            15.0,
            default.petrol_l_per_100km,
            0.5,
            help="A comparable compact petrol SUV uses about 6-7 L/100 km.",
        )
        diesel = c.number_input("Diesel car (L/100 km)", 3.0, 15.0, default.diesel_l_per_100km, 0.5)
        loss = a.slider(
            "Charging loss (%)",
            0,
            25,
            int(default.charging_loss_pct),
            help="Not all electricity from the wall reaches the battery: the charger and cables turn some "
            "into heat. At home on 11 kW AC about 8-12 % is lost, so you pay for about 10 % more than the "
            "car stores.",
        )
    return queries.CostAssumptions(petrol, diesel, float(loss), hu_price, default.at_electricity_eur)


def own_car(monthly: pd.DataFrame) -> None:
    with st.expander("Compare with my own car"):
        a, b = st.columns(2)
        fuel = a.radio("Fuel", ["Petrol", "Diesel"], horizontal=True)
        use = b.number_input("Its consumption (L/100 km)", 2.0, 20.0, 7.0, 0.1)
        column = "petrol_huf" if fuel == "Petrol" else "diesel_huf"
        default_use = (
            queries.CostAssumptions().petrol_l_per_100km
            if fuel == "Petrol"
            else queries.CostAssumptions().diesel_l_per_100km
        )
        own = monthly[column].sum() / default_use * use  # same kilometres and prices, your car's thirst
        st.metric(
            f"Your {fuel.lower()} car would have cost",
            number(own, "Ft"),
            delta=f"{number(own - monthly['ev_huf'].sum(), 'Ft')} more than the EV",
            delta_color="off",
        )


FREQS = {"Week": "week", "Month": "month", "Year": "year"}
UNITS = {"week": ("week", "weeks"), "month": ("month", "months"), "year": ("year", "years")}


def render(con, period: queries.Period) -> None:
    render_html(components.hidden_title("Costs"))
    week = queries.latest_fuel_week(con)
    if week is None:
        empty("No fuel prices yet: `kiatracker refresh` fetches them from the EU Weekly Oil Bulletin.")
        return
    assume = queries.CostAssumptions()
    if "cost-assumptions" in st.session_state:
        assume = st.session_state["cost-assumptions"]

    with card("savings"):
        left, right = st.columns([3, 2], vertical_alignment="center")
        left.html(components.section_title("Saved compared with a petrol car"))
        choice = right.segmented_control(
            "Period", list(FREQS), default="Month", label_visibility="collapsed", key="savings-freq"
        )
        freq = FREQS[choice or "Month"]
        by_bucket = queries.costs(con, period, assume, freq)
        if by_bucket.empty:
            empty("No finished drives in this period yet.")
            return
        saved = queries.savings(by_bucket, freq, date.today())
        shown = saved if freq == "year" else saved.tail(12)
        done = shown[shown["complete"]]
        last = done.iloc[-1] if not done.empty else shown.iloc[-1]
        st.html(
            components.savings_figures(
                last, queries.bucket_label(last["bucket"], freq), assume.petrol_l_per_100km
            )
        )
        st.altair_chart(charts.savings_bars(shown), width="stretch")
        one, many = UNITS[freq]
        st.caption(
            f"Each bar is one {one}'s saving; the {one} still under way is included as far as it goes. "
            f"Last {len(shown)} {many}: {components.fmt_ft(shown['saved_huf'].sum())}."
        )

    monthly = queries.costs(con, period, assume)
    km = monthly["distance_km"].sum()
    per100 = {k: monthly[k].sum() / km * 100 for k in monthly.columns if k.endswith(("_huf", "_eur"))}
    t = components.theme
    with card("hungary"):
        st.html(
            components.section_title(
                "Per 100 km in Hungary", f"pump prices from the EU Weekly Oil Bulletin, week of {week}"
            )
        )
        st.html(
            components.compare_bars(
                [
                    ("Your EV", per100["ev_huf"], "home charging, losses included", t.SKY),
                    ("Diesel car", per100["diesel_huf"], f"{assume.diesel_l_per_100km:g} L/100 km", t.PALE),
                    ("Petrol car", per100["petrol_huf"], f"{assume.petrol_l_per_100km:g} L/100 km", t.CORAL),
                ],
                lambda v: f"{v:,.0f} Ft".replace(",", " "),
            )
        )
    with card("austria"):
        st.html(components.section_title("The same driving in Austria", "per 100 km"))
        st.html(
            components.compare_bars(
                [
                    (
                        "Your EV",
                        per100["ev_at_eur"],
                        f"€{assume.at_electricity_eur:.2f}/kWh household rate",
                        t.SKY,
                    ),
                    ("Diesel car", per100["diesel_at_eur"], "Austrian pump prices", t.PALE),
                    ("Petrol car", per100["petrol_at_eur"], "Austrian pump prices", t.CORAL),
                ],
                lambda v: f"€ {v:.2f}",
            )
        )
    st.session_state["cost-assumptions"] = assumptions()
    own_car(monthly)
