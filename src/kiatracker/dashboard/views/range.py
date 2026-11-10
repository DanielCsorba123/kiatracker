from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from kiatracker.dashboard import charts, components, queries
from kiatracker.dashboard.ui import card, empty, number, render_html
from kiatracker.forecast.model import NotEnoughData
from kiatracker.forecast.outlook import LOCAL, daily_outlook, range_interval
from kiatracker.forecast.specs import EV3
from kiatracker.forecast.train import Trained, car_state, train


def fingerprint(con) -> tuple:
    """Cheap summary that changes whenever the drives or weather change, to key the trained model on."""
    return con.execute(
        """select (select count(*) from drives), (select max(end_ts) from drives),
                  (select count(*) from drive_weather), (select count(*) from readings_location)"""
    ).fetchone()


@st.cache_data(max_entries=4, show_spinner="Training the range model…")
def cached_train(key: tuple, _con) -> Trained:
    """Training reads every GPS point and runs several fits, so don't redo it on each slider move."""
    return train(_con)


def forecast_hourly(con) -> dict | None:
    """The forecast table in the shape the outlook expects. A database built before the cloud and rain
    columns existed still works: those come back empty until the next `kiatracker build`."""
    columns = {
        c
        for (c,) in con.execute(
            "select column_name from information_schema.columns where table_name = 'forecast_hourly'"
        ).fetchall()
    }
    if not columns:
        return None
    extra = [c if c in columns else f"null as {c}" for c in ("cloud_pct", "rain_prob_pct")]
    rows = con.execute(
        f"select ts, temp_c, wind_kph, wind_dir_deg, {', '.join(extra)} from forecast_hourly order by ts"
    ).fetchall()
    if not rows:
        return None
    cols = list(zip(*rows, strict=True))
    return {
        "time": [ts.strftime("%Y-%m-%dT%H:%M") for ts in cols[0]],
        "temperature_2m": list(cols[1]),
        "wind_speed_10m": list(cols[2]),
        "wind_direction_10m": list(cols[3]),
        "cloud_cover": list(cols[4]),
        "precipitation_probability": list(cols[5]),
    }


def weather_now(hourly: dict | None) -> tuple[float, float] | None:
    """Forecast temperature and wind for the current hour, if the forecast covers it."""
    if not hourly:
        return None
    now = datetime.now(UTC).replace(tzinfo=None)
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    i = min(range(len(times)), key=lambda n: abs(times[n] - now))
    if abs(times[i] - now) > timedelta(hours=2):
        return None
    temp, wind = hourly["temperature_2m"][i], hourly["wind_speed_10m"][i]
    return None if temp is None or wind is None else (temp, wind)


def has_range(outlook: list[dict]) -> bool:
    """True if any day has a range (today may lack one when there is no battery reading)."""
    return any(r.get("range_km") is not None for r in outlook)


def km_range(lo, mid, hi) -> str:
    return "–" if mid is None else f"{lo:,.0f}–{hi:,.0f} km likely"


def render(con, period: queries.Period) -> None:
    render_html(components.hidden_title("Range"))
    try:
        trained = cached_train(fingerprint(con), con)
    except NotEnoughData as err:
        empty(
            f"The range model needs {err.needed} more drives of 5 km or more with weather. "
            "Keep the collector running and run `kiatracker weather`."
        )
        return
    model, speed = trained.model, trained.typical_speed_kph
    soc, capacity = car_state(con)
    hourly = forecast_hourly(con)

    now = weather_now(hourly)
    lo, mid, hi = range_interval(model, soc, capacity, speed, *now) if now else (None, None, None)
    mae = trained.backtest["model"]["mae"] if trained.backtest else None
    baseline = trained.backtest["temperature_only"]["mae"] if trained.backtest else None
    usable = (
        f"{soc / 100 * capacity:.0f} of {capacity:.0f} kWh usable" if soc is not None and capacity else None
    )
    render_html(
        components.stat_strip(
            [
                ("Range now", number(mid, "km"), f"{km_range(lo, mid, hi)} at {speed:.0f} km/h"),
                ("Battery", number(soc, "%"), usable),
                (
                    "Typical error",
                    number(mae, "kWh", 2),
                    f"per 100 km; temperature alone: {number(baseline, digits=2)}",
                ),
                ("Learned from", number(model.n_drives, "drives"), "retrained every night"),
            ]
        )
    )

    usual = queries.usual_charge_level(con, soc)
    today = datetime.now(LOCAL).date()
    with card("outlook"):
        left, right = st.columns([3, 1])
        left.html(components.section_title("The next seven days, and what each one costs you"))
        choice = right.segmented_control(
            "Later days start from",
            [f"Usual {usual.level} %", "Full 100 %"],
            default=f"Usual {usual.level} %",
            label_visibility="collapsed",
            key="outlook-soc",
        )
        full = choice == "Full 100 %"
        outlook = (
            daily_outlook(hourly, model, soc, 100 if full else usual.level, capacity, speed, today)
            if hourly
            else []
        )
        if has_range(outlook):
            scale = max(r["mild_km"] or 0 for r in outlook) * 1.05
            render_html(
                components.rule_line(soc, usual, full) + components.forecast_rows(outlook, scale, today)
            )
            st.caption(
                "Route unknown, so wind is averaged over all directions: "
                "on a round trip it always costs range."
            )
        else:
            empty("No forecast yet: run `kiatracker forecast`, then `kiatracker build`.")

    with card("whatif"):
        left, right = st.columns([6, 5], gap="large")
        with left:
            st.html(components.section_title("What if…"))
            temp = st.slider("Outside temperature", -20, 35, 5, format="%d °C")
            wind = st.slider("Wind", 0, 70, 15, format="%d km/h")
            what_speed = st.slider("Average speed", 20, 130, int(round(speed)), format="%d km/h")
        full_lo, full_mid, full_hi = range_interval(model, 100, capacity, what_speed, temp, wind)
        if full_mid is not None:
            right.html(components.whatif_result(full_lo, full_mid, full_hi, EV3.best_range_km))

    left, right = st.columns(2)
    with left, card("predicts"):
        st.html(components.section_title("How well it predicts"))
        if trained.backtest:
            predictions = pd.DataFrame(trained.backtest["predictions"])
            st.altair_chart(charts.predicted_vs_actual(predictions, "kWh/100 km"), width="stretch")
            st.caption(
                "Each dot predicts a later drive from earlier ones only. On the line would be perfect."
            )
    with right, card("learned"):
        st.html(components.section_title("What it has learned about your car"))
        st.html(
            components.icon_list(
                [(icon, components.theme.TINT_SKY, text) for icon, text in model.explain_items(speed)]
            )
        )
