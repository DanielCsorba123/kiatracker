from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import empty, number, page_header, tiles
from kiatracker.forecast.model import NotEnoughData
from kiatracker.forecast.outlook import LOCAL, daily_outlook, range_interval
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
    """The forecast table in the shape the outlook expects."""
    rows = con.execute(
        "select ts, temp_c, wind_kph, wind_dir_deg from forecast_hourly order by ts"
    ).fetchall()
    if not rows:
        return None
    return {
        "time": [ts.strftime("%Y-%m-%dT%H:%M") for ts, *_ in rows],
        "temperature_2m": [t for _, t, _, _ in rows],
        "wind_speed_10m": [w for _, _, w, _ in rows],
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
    return hourly["temperature_2m"][i], hourly["wind_speed_10m"][i]


def km_range(lo, mid, hi) -> str:
    return "–" if mid is None else f"{lo:,.0f}–{hi:,.0f} km likely"


def render(con, period: queries.Period) -> None:
    page_header("Range", "How far the current charge goes in the coming days' weather.")
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
    tiles(
        [
            (
                "Range now",
                number(mid, "km"),
                km_range(lo, mid, hi) + f" at {speed:.0f} km/h in the current weather.",
            ),
            ("Battery", number(soc, "%"), None),
            (
                "Avg. error",
                number(mae, digits=1),
                f"In kWh/100 km, predicting later drives from earlier ones; a temperature-only model: "
                f"{number(baseline, 'kWh/100 km', 1)}.",
            ),
            ("Trained on", number(model.n_drives, "drives"), None),
        ]
    )

    st.subheader("Next days")
    outlook = daily_outlook(hourly, model, soc, capacity, speed, datetime.now(LOCAL).date()) if hourly else []
    if outlook and outlook[0]["range_km"] is not None:
        days = pd.DataFrame(outlook)
        days["label"] = [f"{d:%a %d %b}" for d in days["day"]]
        st.altair_chart(
            charts.bar_with_interval(
                days,
                "label:O",
                "range_km",
                "range_lo",
                "range_hi",
                f"Daytime range from {soc:.0f} % at {speed:.0f} km/h",
                "km",
            ),
            width="stretch",
        )
        st.caption(
            "Route unknown, so wind is averaged over all directions: on a round trip it always costs range."
        )
    else:
        empty("No forecast yet: run `kiatracker forecast`, then `kiatracker build`.")

    st.subheader("What if")
    a, b, c = st.columns(3)
    temp = a.slider("Outside temperature (°C)", -20, 35, 5)
    wind = b.slider("Wind (km/h)", 0, 70, 15)
    what_speed = c.slider("Average speed (km/h)", 20, 130, int(round(speed)))
    full = range_interval(model, 100, capacity, what_speed, temp, wind)
    if full[1] is not None:
        st.metric("Range on a full battery", f"{full[1]:,.0f} km", help=km_range(*full))

    st.subheader("How well it predicts")
    if trained.backtest:
        predictions = pd.DataFrame(trained.backtest["predictions"])
        st.altair_chart(charts.predicted_vs_actual(predictions, "kWh/100 km"), width="stretch")
    st.subheader("What the model learned")
    for line in model.explain(speed):
        st.markdown(f"- {line}")
