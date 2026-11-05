import pandas as pd
import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty, number, page_header, tiles
from kiatracker.prices import ELECTRICITY

SERIES = ["Your EV", "Petrol car", "Diesel car"]


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


def render(con, period: queries.Period) -> None:
    page_header("Costs", "Your EV against petrol and diesel, at real Hungarian and Austrian pump prices.")
    week = queries.latest_fuel_week(con)
    if week is None:
        empty("No fuel prices yet: `kiatracker refresh` fetches them from the EU Weekly Oil Bulletin.")
        return
    assume = assumptions()
    monthly = queries.costs(con, period, assume)
    if monthly.empty:
        empty("No finished drives in this period yet.")
        return

    km = monthly["distance_km"].sum()
    st.caption(f"{km:,.0f} km in this period. Pump prices: EU Weekly Oil Bulletin, week of {week}.")
    per100 = {k: monthly[k].sum() / km * 100 for k in monthly.columns if k.endswith(("_huf", "_eur"))}

    st.subheader("Per 100 km in Hungary")
    tiles(
        [
            ("Your EV", number(per100["ev_huf"], "Ft"), "Home charging, losses included."),
            (
                "Petrol car",
                number(per100["petrol_huf"], "Ft"),
                f"{assume.petrol_l_per_100km:g} L/100 km at Hungarian pump prices.",
            ),
            ("Diesel car", number(per100["diesel_huf"], "Ft"), f"{assume.diesel_l_per_100km:g} L/100 km."),
            (
                "Saved vs petrol",
                number(monthly["petrol_huf"].sum() - monthly["ev_huf"].sum(), "Ft"),
                "Over the whole period.",
            ),
        ]
    )
    st.subheader("The same driving in Austria")
    tiles(
        [
            (
                "Your EV",
                number(per100["ev_at_eur"], "€", 2),
                f"At €{assume.at_electricity_eur:.2f}/kWh household electricity.",
            ),
            ("Petrol car", number(per100["petrol_at_eur"], "€", 2), "Austrian pump prices."),
            ("Diesel car", number(per100["diesel_at_eur"], "€", 2), None),
            (
                "Saved vs petrol",
                number(monthly["petrol_at_eur"].sum() - monthly["ev_at_eur"].sum(), "€"),
                None,
            ),
        ]
    )

    long = monthly.melt(
        id_vars="month",
        value_vars=["ev_huf", "petrol_huf", "diesel_huf"],
        var_name="series",
        value_name="cost",
    )
    long["series"] = long["series"].map(
        dict(zip(["ev_huf", "petrol_huf", "diesel_huf"], SERIES, strict=True))
    )
    st.altair_chart(
        charts.grouped_bar(long, "month", "series", "cost", "Monthly cost in Hungary", "Ft", SERIES),
        width="stretch",
    )
    own_car(monthly)
