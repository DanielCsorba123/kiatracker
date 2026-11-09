"""Compare ways to get somewhere: energy, arrival charge and the reasons, in the forecast weather."""

from datetime import date, datetime, timedelta
from itertools import accumulate

import httpx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components_v1

from kiatracker.config import load_settings
from kiatracker.dashboard import charts, components, queries
from kiatracker.dashboard.map import map_html
from kiatracker.dashboard.ui import card, number, render_html
from kiatracker.dashboard.views.drives import cached_model
from kiatracker.dashboard.views.range import fingerprint
from kiatracker.elevation import Terrain, download_tile
from kiatracker.forecast.outlook import LOCAL
from kiatracker.forecast.specs import EV3
from kiatracker.forecast.train import car_state
from kiatracker.route_energy import (
    Comparison,
    Levers,
    PlaceNotFound,
    compare_routes,
    differences,
    energy_breakdown,
    rival_first,
    win_shares,
)

DEFAULT_CAPACITY_KWH = EV3.usable_kwh
CAPS = {"No cap (typical road speeds)": None, "130 km/h": 130.0, "120 km/h": 120.0, "110 km/h": 110.0,
        "100 km/h": 100.0}  # fmt: skip
MAP_HEIGHT = 560


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
            "Knoten Vösendorf\nKnoten Prater",
            help="One route per line; several points on a line, separated by ';', are passed in order. The "
            "route is forced through that exact point, so a town name means its centre. To pick a motorway, "
            "name an interchange (Knoten Prater: A23 through Vienna; Knoten Vösendorf: A21 to the A2) or "
            "type 'lat, lon'. The Roads column shows what each route really uses.",
        )
        a, b, c, d = st.columns(4)
        next_hour = (datetime.now(LOCAL) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        day = a.date_input("Departure", next_hour.date(), min_value=date.today(),
                           max_value=date.today() + timedelta(days=6))  # fmt: skip
        hour = b.time_input("Time", next_hour.time(), step=timedelta(minutes=30))
        soc = c.slider("Charge at departure", 10, 100, int(soc_now or 80), format="%d %%")
        cap = d.selectbox("Speed cap", list(CAPS), help="Lever: what slowing down on fast roads saves.")
        pace = st.slider("Your pace vs typical road speeds", 80, 120, 100, 5, format="%d %%",
                         help="Lever: above 100 % if you usually drive faster than traffic.")  # fmt: skip
        if not st.form_submit_button("Compare", type="primary"):
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


def profiles(estimates) -> pd.DataFrame:
    frames = []
    for e in estimates:
        cond = e.conditions
        frames.append(
            pd.DataFrame(
                {
                    "route": e.route.label,
                    "km": list(accumulate(x.km for x in cond)),
                    "height": list(accumulate(x.climb_m - x.descent_m for x in cond)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def route_map(estimates) -> None:
    routes = [
        {
            "label": e.route.label,
            "colour": charts.ROUTE_COLOURS[i % len(charts.ROUTE_COLOURS)],
            "coords": [[round(lon, 5), round(lat, 5)] for lat, lon in e.route.points],
        }
        for i, e in enumerate(estimates)
    ]
    with card("map"):
        components_v1.html(map_html(routes), height=MAP_HEIGHT)


def render(con, period: queries.Period) -> None:
    render_html(components.hidden_title("Routes"))
    soc_now, capacity = car_state(con)
    with card("form"):
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

    estimates = rival_first(comparison.estimates)  # the chosen route and its closest rival lead
    colours = [charts.ROUTE_COLOURS[i % len(charts.ROUTE_COLOURS)] for i in range(len(estimates))]
    route_map(estimates)
    render_html(components.route_cards(estimates, win_shares(estimates), colours))
    if not all(e.weather_complete for e in estimates):
        st.warning("The forecast was missing for part of the way; those pieces assume 10 °C and no wind.")

    first = estimates[0]
    with card("heights"):
        st.html(components.section_title("Up and down along the way", "first route in coral, second in blue"))
        st.altair_chart(charts.route_heights(profiles(estimates)), width="stretch")
        parts_first = energy_breakdown(first.conditions, model)
        st.caption(
            f"{first.route.label}: the climbs cost about {parts_first.get('climb', 0.0):.1f} kWh; "
            f"rolling down gives {abs(parts_first.get('regen', 0.0)):.1f} kWh back."
        )
    if len(estimates) > 1:
        parts = pd.DataFrame(
            [
                {"route": e.route.label, "cause": k, "kwh": v}
                for e in estimates[:2]
                for k, v in e.breakdown.items()
            ]
        )
        with card("difference"):
            st.html(
                components.section_title(
                    "Why they differ", f"{first.route.label} compared with {estimates[1].route.label}"
                )
            )
            left, right = st.columns([3, 2], gap="large", vertical_alignment="center")
            left.altair_chart(
                charts.route_difference(parts, first.route.label, estimates[1].route.label), width="stretch"
            )
            lines = differences(estimates)
            if lines:
                right.html(f'<div class="wr-callout">{components.e(lines[0])}</div>')

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
* **Routes:** OSRM on OpenStreetMap roads, the fastest by typical speeds, without live traffic; a via point
  forces the route through it.
* **Pieces:** OSRM's road speeds per ~1 km{capped}, at {request["pace"]:.0%} pace; each piece's time
  decides which forecast hour it gets.
* **Uncertainty:** 1,000 simulated days. Forecast temperature ±1.5 °C, wind ±25 % and ±20°,
  traffic ±4 %, how unsure the model's coefficients are (refits on resampled drives), plus how far the
  model misses real drives. Every route sees the same simulated days,
  so the odds compare like with like. The battery's 0.5 % reading steps blur short drives, so that
  part of the model's misses is taken out for long trips.
* **Privacy:** the places you type go to OpenStreetMap (Nominatim) and the OSRM route server; ~10 km weather
  cells along the routes go to Open-Meteo. Terrain is read from map tiles stored on this machine.
"""
        )
    st.caption(f"Usable battery {number(capacity or DEFAULT_CAPACITY_KWH, 'kWh', 1)}.")
