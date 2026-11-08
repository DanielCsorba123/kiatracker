"""Compare ways to get somewhere: energy, arrival charge and the reasons, in the forecast weather."""

from datetime import date, datetime, timedelta
from itertools import accumulate

import httpx
import pandas as pd
import pydeck as pdk
import streamlit as st

from kiatracker.config import load_settings
from kiatracker.dashboard import charts, queries
from kiatracker.dashboard.ui import number, page_header
from kiatracker.dashboard.views.drives import cached_model
from kiatracker.dashboard.views.range import fingerprint
from kiatracker.elevation import Terrain, download_tile
from kiatracker.forecast.outlook import LOCAL
from kiatracker.forecast.train import car_state
from kiatracker.route_energy import (
    Comparison,
    Levers,
    PlaceNotFound,
    compare_routes,
    differences,
    energy_breakdown,
)

DEFAULT_CAPACITY_KWH = 81.4
CAPS = {"No cap (typical road speeds)": None, "130 km/h": 130.0, "120 km/h": 120.0, "110 km/h": 110.0,
        "100 km/h": 100.0}  # fmt: skip
RGB = [tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in charts.ROUTE_COLOURS]


@st.cache_data(
    ttl=3600, max_entries=16, show_spinner="Routing, fetching the forecast and pricing each route…"
)
def cached_compare(
    origin, destination, vias, depart, soc, capacity, cap, pace, model_key, _model
) -> Comparison:
    levers = Levers(depart, soc, capacity, cap, pace)
    with httpx.Client() as http:
        terrain = Terrain(load_settings().dem_dir, lambda name: download_tile(name, http))
        return compare_routes(origin, destination, [list(v) for v in vias], levers, _model, terrain, http)


def form(soc_now: float | None) -> dict | None:
    with st.form("route"):
        left, right = st.columns(2)
        origin = left.text_input("From", "Krems an der Donau")
        destination = right.text_input("To", "Wiener Neustadt")
        vias = st.text_area(
            "Also compare routes through",
            "St. Pölten\nWien",
            help="One route per line; several places on a line, separated by ';', are passed in order.",
        )
        a, b, c, d = st.columns(4)
        day = a.date_input("Departure", date.today(), min_value=date.today(),
                           max_value=date.today() + timedelta(days=6))  # fmt: skip
        next_hour = (datetime.now(LOCAL) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        hour = b.time_input("Time", next_hour.time(), step=timedelta(minutes=30))
        soc = c.slider("Charge at departure", 10, 100, int(soc_now or 80), format="%d %%")
        cap = d.selectbox("Speed cap", list(CAPS), help="Lever: what slowing down on fast roads saves.")
        pace = st.slider("Your pace vs typical road speeds", 80, 120, 100, 5, format="%d %%",
                         help="Lever: above 100 % if you usually drive faster than traffic.")  # fmt: skip
        if not st.form_submit_button("Compare routes", type="primary"):
            return None
    lines = [tuple(p.strip() for p in line.split(";") if p.strip()) for line in vias.splitlines()]
    return {
        "origin": origin.strip(),
        "destination": destination.strip(),
        "vias": tuple(line for line in lines if line),
        "depart": datetime.combine(day, hour, LOCAL),
        "soc": float(soc),
        "cap": CAPS[cap],
        "pace": pace / 100,
    }


def table(comparison: Comparison) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Route": e.route.label,
            "Distance": e.km,
            "Time": e.minutes,
            "Energy": e.kwh_p50,
            "Likely range": f"{e.kwh_p10:.1f}–{e.kwh_p90:.1f} kWh",
            "Arrive with": e.arrival_soc_p50,
            "Above 10 %": e.p_reserve,
            "Climbing": e.climb_m,
        }
        for e in comparison.estimates
    )


def profiles(comparison: Comparison, model) -> pd.DataFrame:
    frames = []
    for e in comparison.estimates:
        cond = e.conditions
        frames.append(
            pd.DataFrame(
                {
                    "route": e.route.label,
                    "km": list(accumulate(x.km for x in cond)),
                    "kwh": list(accumulate(sum(energy_breakdown([x], model).values()) for x in cond)),
                    "height": list(accumulate(x.climb_m - x.descent_m for x in cond)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def route_map(comparison: Comparison) -> None:
    paths = [
        {
            "route": e.route.label,
            "path": [[lon, lat] for lat, lon in e.route.points],
            "color": RGB[i % len(RGB)],
        }
        for i, e in enumerate(comparison.estimates)
    ]
    points = [p for e in comparison.estimates for p in e.route.points]
    view = pdk.ViewState(
        latitude=sum(p[0] for p in points) / len(points),
        longitude=sum(p[1] for p in points) / len(points),
        zoom=8,
    )
    layer = pdk.Layer("PathLayer", paths, get_path="path", get_color="color", width_min_pixels=4,
                      pickable=True, opacity=0.85)  # fmt: skip
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip={"text": "{route}"}))


def render(con, period: queries.Period) -> None:
    page_header("Routes", "Which way costs the least energy, in the weather forecast for when you drive.")
    soc_now, capacity = car_state(con)
    request = form(soc_now)
    if request is None:
        st.caption(
            "Each route is cut into ~1 km pieces. Every piece gets the forecast for the hour you'd drive "
            "it, the headwind along its own direction and its climb from terrain maps, then the range "
            "model prices it."
        )
        return
    model, source = cached_model(fingerprint(con), con)
    try:
        r = request
        comparison = cached_compare(
            r["origin"], r["destination"], r["vias"], r["depart"], r["soc"], capacity or DEFAULT_CAPACITY_KWH,
            r["cap"], r["pace"], tuple(model.coef.items()), model,
        )  # fmt: skip
    except PlaceNotFound as err:
        st.error(f"Couldn't find “{err}”. Try a town name, or type coordinates as “lat, lon”.")
        return
    except httpx.HTTPError as err:
        st.error(f"The routing service didn't answer ({type(err).__name__}). Try again in a minute.")
        return
    if not comparison.estimates:
        st.warning("No route found between these places.")
        return

    st.subheader(f"{comparison.origin.name} → {comparison.destination.name}")
    st.dataframe(
        table(comparison),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Distance": st.column_config.NumberColumn(format="%.0f km"),
            "Time": st.column_config.NumberColumn(format="%.0f min"),
            "Energy": st.column_config.NumberColumn("Energy (most likely)", format="%.1f kWh"),
            "Arrive with": st.column_config.NumberColumn(format="%.0f %%"),
            "Above 10 %": st.column_config.ProgressColumn(
                "Chance to arrive above 10 %", format="percent", min_value=0, max_value=1
            ),
            "Climbing": st.column_config.NumberColumn(format="%.0f m"),
        },
    )
    for line in differences(comparison.estimates):
        st.markdown(f"- {line}")
    if not all(e.weather_complete for e in comparison.estimates):
        st.warning("The forecast was missing for part of the way; those pieces assume 10 °C and no wind.")

    parts = pd.DataFrame(
        [
            {"route": e.route.label, "cause": k, "kwh": v}
            for e in comparison.estimates
            for k, v in e.breakdown.items()
        ]
    )
    st.altair_chart(charts.route_breakdown(parts), use_container_width=True)
    profile = profiles(comparison, model)
    left, right = st.columns(2)
    left.altair_chart(charts.route_profile(profile, "kwh", "Energy used along the way", "kWh"),
                      use_container_width=True)  # fmt: skip
    right.altair_chart(charts.route_profile(profile, "height", "Height along the way", "m from the start"),
                       use_container_width=True)  # fmt: skip
    route_map(comparison)

    with st.expander("How this is calculated"):
        which = (
            "trained on your drives"
            if source == "trained"
            else "the car's specs (too few drives to beat them)"
        )
        capped = ", capped" if request["cap"] else ""
        st.markdown(
            f"""
* **Model:** {which};
  base {model.coef["c0"]:.1f} kWh/100 km, plus drag, heating, climbing and regeneration terms.
* **Pieces:** OSRM's road speeds per ~1 km{capped}, at {request["pace"]:.0%} pace; each piece's time
  decides which forecast hour it gets.
* **Uncertainty:** 1,000 simulated days. Forecast temperature ±1.5 °C, wind ±25 % and ±20°,
  traffic ±4 %, plus how far the model misses real drives. Every route sees the same simulated days,
  so the odds compare like with like. The battery's 0.5 % reading steps blur short drives, so that
  part of the model's misses is taken out for long trips.
* **Privacy:** the places you type go to OpenStreetMap (Nominatim) and the OSRM route server; ~10 km weather
  cells along the routes go to Open-Meteo. Terrain is read from map tiles stored on this machine.
"""
        )
    st.caption(f"Battery capacity {number(capacity or DEFAULT_CAPACITY_KWH, 'kWh', 1)}.")
