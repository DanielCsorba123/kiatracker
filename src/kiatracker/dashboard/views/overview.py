"""Overview: today's range in a sentence, the week ahead, how much you use, and a few things worth knowing."""

from datetime import UTC, datetime, timedelta

import streamlit as st

from kiatracker.dashboard import charts, components, queries
from kiatracker.dashboard.ui import card, empty, render_html
from kiatracker.dashboard.views.range import cached_train, fingerprint, forecast_hourly
from kiatracker.forecast.model import NotEnoughData
from kiatracker.forecast.outlook import LOCAL, daily_outlook, range_interval
from kiatracker.forecast.train import car_state


def weather_line(hourly: dict | None) -> tuple[str, tuple[float, float] | None]:
    """'It's 6 °C with a light west wind.' for the current hour, and (temperature, wind) for the model."""
    if not hourly:
        return "", None
    now = datetime.now(UTC).replace(tzinfo=None)
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    i = min(range(len(times)), key=lambda n: abs(times[n] - now))
    temp, wind = hourly["temperature_2m"][i], hourly["wind_speed_10m"][i]
    if abs(times[i] - now) > timedelta(hours=2) or temp is None or wind is None:
        return "", None
    direction = (hourly.get("wind_direction_10m") or [None] * len(times))[i]
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    side = f" {names[round(direction / 45) % 8]}" if direction is not None else ""
    return f" It's {temp:.0f} °C with {components.wind_words(wind)}{side} wind.", (temp, wind)


def render(con, period: queries.Period) -> None:
    render_html(components.hidden_title("Overview"))
    soc, capacity = car_state(con)
    hourly = forecast_hourly(con)
    line, now = weather_line(hourly)
    greeting = components.greeting(datetime.now(LOCAL).hour) + "." + line
    try:
        trained = cached_train(fingerprint(con), con)
    except NotEnoughData:
        trained = None

    k = queries.kpis(con, period)
    costs = queries.costs(con, period, queries.CostAssumptions())
    saved = float((costs["petrol_huf"] - costs["ev_huf"]).sum()) if not costs.empty else None
    usual = queries.usual_charge_level(con, soc)
    today = datetime.now(LOCAL).date()
    outlook = (
        daily_outlook(hourly, trained.model, soc, usual.level, capacity, trained.typical_speed_kph, today)
        if trained and hourly
        else []
    )
    lo = mid = hi = None
    if outlook and outlook[0]["day"] == today:  # today's daytime forecast, the same number as the week strip
        lo, mid, hi = outlook[0]["range_lo"], outlook[0]["range_km"], outlook[0]["range_hi"]
    elif trained and now:
        lo, mid, hi = range_interval(trained.model, soc, capacity, trained.typical_speed_kph, *now)
    comparison = None
    pair = queries.commute_pair(con, period)
    if mid and pair and pair[2] > 0:
        trips = int(mid // (2 * pair[2]))
        comparison = f"Enough for {trips} of your usual {pair[2]:.0f} km trips there and back."

    left, right = st.columns([6, 5], gap="large", vertical_alignment="center")
    left.html(components.hero(greeting, mid, lo, hi, soc, comparison))
    right.html(components.battery_card(soc, k["distance_km"], k["kwh_per_100km"], saved))

    if outlook:
        with card("week"):
            note = (
                f"today from {soc:.0f} %, then from your usual {usual.level} % · typical commute speeds"
                if soc is not None
                else "typical commute speeds"
            )
            st.html(components.section_title("Range this week, with the forecast", note))
            st.html(components.week_strip(outlook, today))

    monthly = queries.monthly(con, period)
    if monthly["kwh_per_100km"].notna().sum() == 0:
        empty("No drives in this period yet.")
        return
    left, right = st.columns([13, 10])
    with left, card("monthly"):
        st.html(components.section_title("How much you use, month by month"))
        st.caption("kWh per 100 km · coral months are the cold ones")
        st.altair_chart(charts.monthly_use(monthly), width="stretch")
    tips = queries.tips_facts(con, period, outlook, today)
    if tips:
        with right, card("tips"):
            st.html(components.section_title("Worth knowing"))
            st.html(components.icon_list(tips))

    weekly = queries.weekly(con, period)
    with card("weekly"):
        st.html(components.section_title("Distance per week"))
        st.altair_chart(charts.weekly_distance(weekly), width="stretch")
