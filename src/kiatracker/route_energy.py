"""Energy for a planned route, piece by piece, in the forecast weather, with its uncertainty.

Each ~1 km piece is driven at a known time (departure plus the time to get there), so it gets the forecast
for that hour and its ~10 km cell, the headwind along its own direction, and its climb or descent from the
terrain tiles. The range model then prices it. The uncertainty is simulated: forecast temperature and wind
can be off, traffic changes the pace, and the model itself misses real drives by its residual spread.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np

from kiatracker.forecast.features import T_BASE, T_COOL, air_density_ratio
from kiatracker.forecast.model import RangeModel
from kiatracker.geo import headwind_kph
from kiatracker.routing import Piece, Place, Route, cut_pieces, fetch_routes, geocode
from kiatracker.segments import hour_values

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CELLS_PER_REQUEST = 50
CAUSES = {
    "base": "Rolling and drivetrain",
    "time": "Electronics and stop-and-go",
    "drag": "Air drag (still air)",
    "wind": "Wind",
    "heating": "Heating",
    "cooling": "Air conditioning",
    "climb": "Climbing",
    "regen": "Downhill regen",
}
COMPONENTS = tuple(CAUSES)
# each cause in words, by which way it moves the energy (regen: more of it saves energy)
MORE = {"base": "more rolling resistance", "time": "more time on the road", "drag": "more air drag",
        "wind": "more headwind", "heating": "more heating", "cooling": "more air conditioning",
        "climb": "more climbing",
        "regen": "less energy back downhill"}  # fmt: skip
LESS = {"base": "less rolling resistance", "time": "less time on the road", "drag": "less air drag",
        "wind": "less headwind", "heating": "less heating", "cooling": "less air conditioning",
        "climb": "less climbing",
        "regen": "more energy back downhill"}  # fmt: skip
# Monte Carlo spreads: how wrong a day-ahead forecast and the traffic typically are
TEMP_SD = 1.5  # °C
WIND_SPEED_SD = 0.25  # log scale: about ±25 %
WIND_DIR_SD = 20.0  # degrees
PACE_SD = 0.04  # share of speed
READING_NOISE_KWH = 0.4  # one 0.5 % step of the battery reading: blurs every measured drive by about this
FALLBACK_TEMP = 10.0  # when the forecast is missing for a piece (flagged in the result)
SPECS_SD = 0.2  # without fitted drives, each coefficient is trusted to about ±20 %


@dataclass(frozen=True)
class Levers:
    depart: datetime
    start_soc: float
    capacity_kwh: float
    speed_cap_kph: float | None = None
    pace: float = 1.0  # 1.1 = you drive 10 % faster than OSRM's typical speed
    reserve_soc: float = 10.0


@dataclass(frozen=True)
class Conditions:
    km: float
    speed_kph: float
    hours_in: float  # since departure, at the middle of the piece
    bearing_deg: float
    temp_c: float | None
    wind_kph: float | None
    wind_dir_deg: float | None
    headwind_kph: float
    climb_m: float
    descent_m: float


@dataclass(frozen=True)
class RouteEstimate:
    route: Route
    km: float
    minutes: float
    kwh_p10: float
    kwh_p50: float
    kwh_p90: float
    breakdown: dict[str, float]
    arrival_soc_p10: float
    arrival_soc_p50: float
    arrival_soc_p90: float
    p_reserve: float  # chance of arriving with at least the reserve
    climb_m: float
    descent_m: float
    weather_complete: bool
    conditions: list[Conditions] = field(repr=False)
    draws: np.ndarray = field(repr=False, default=None)  # simulated kWh, same random days for every route


def weather_cells(pieces: list[Piece]) -> list[tuple[float, float]]:
    return sorted({_cell(p) for p in pieces})


def _cell(p: Piece) -> tuple[float, float]:
    return round((p.start[0] + p.end[0]) / 2, 1), round((p.start[1] + p.end[1]) / 2, 1)


def fetch_route_weather(cells: list[tuple[float, float]], http: httpx.Client) -> dict[tuple, dict]:
    """Hourly forecast (UTC, 7 days) for each cell; Open-Meteo answers many points per request, in order."""
    weather = {}
    for i in range(0, len(cells), CELLS_PER_REQUEST):
        batch = cells[i : i + CELLS_PER_REQUEST]
        response = http.get(
            FORECAST_URL,
            params={
                "latitude": ",".join(str(lat) for lat, _ in batch),
                "longitude": ",".join(str(lon) for _, lon in batch),
                "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m",
                "wind_speed_unit": "kmh",
                "timezone": "UTC",
                "forecast_days": 7,
            },
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        for cell, place in zip(batch, body if isinstance(body, list) else [body], strict=True):
            weather[cell] = place.get("hourly")
    return weather


def conditions(pieces: list[Piece], levers: Levers, weather: dict, terrain) -> list[Conditions]:
    out, hours = [], 0.0
    for p in pieces:
        speed = min(p.speed_kph, levers.speed_cap_kph or p.speed_kph) * levers.pace
        duration = p.km / speed
        middle = hours + duration / 2
        w = hour_values(weather.get(_cell(p)), levers.depart + timedelta(hours=middle))
        h0 = terrain.elevation(*p.start) if terrain else None
        h1 = terrain.elevation(*p.end) if terrain else None
        rise = h1 - h0 if h0 is not None and h1 is not None else 0.0
        wind, wind_from = w.get("wind"), w.get("dir")
        head = (
            headwind_kph(wind, wind_from, p.bearing_deg)
            if wind is not None and wind_from is not None
            else 0.0
        )
        out.append(
            Conditions(p.km, speed, middle, p.bearing_deg, w.get("temp"), wind, wind_from, head,
                       max(rise, 0.0), max(-rise, 0.0))
        )  # fmt: skip
        hours += duration
    return out


def energy_breakdown(cond: list[Conditions], model: RangeModel) -> dict[str, float]:
    """kWh per cause over the route: what the model charges for each term (regen is negative)."""
    c = model.coef
    parts = dict.fromkeys(COMPONENTS, 0.0)
    for x in cond:
        temp = FALLBACK_TEMP if x.temp_c is None else x.temp_c
        rho, per = air_density_ratio(temp), x.km / 100
        parts["base"] += per * c["c0"]
        parts["drag"] += per * c["aero"] * x.speed_kph**2 * rho
        parts["wind"] += per * c["aero"] * ((x.speed_kph + x.headwind_kph) ** 2 - x.speed_kph**2) * rho
        parts["heating"] += per * c["heat"] * max(0.0, T_BASE - temp) / x.speed_kph
        parts["heating"] += per * c.get("cold", 0.0) * max(0.0, T_BASE - temp)  # a cold car loses more
        parts["cooling"] += per * c.get("cool", 0.0) * max(0.0, temp - T_COOL) / x.speed_kph
        parts["time"] += per * c.get("time", 0.0) / x.speed_kph
        parts["climb"] += c.get("climb", 0.0) * x.climb_m
        parts["regen"] -= c.get("regen", 0.0) * x.descent_m
    return parts


def simulate(cond: list[Conditions], model: RangeModel, samples: int = 1000, seed: int = 0) -> np.ndarray:
    """Trip kWh under `samples` plausible versions of the day (each error shared along the whole route)."""
    rng = np.random.default_rng(seed)
    c = coefficient_draws(model, samples, rng)
    km = np.array([x.km for x in cond])
    speed = np.array([x.speed_kph for x in cond])[None, :] * rng.normal(1, PACE_SD, (samples, 1))
    temp = np.array([FALLBACK_TEMP if x.temp_c is None else x.temp_c for x in cond])[None, :]
    temp = temp + rng.normal(0, TEMP_SD, (samples, 1))
    wind = np.array([x.wind_kph or 0.0 for x in cond])[None, :] * rng.lognormal(
        0, WIND_SPEED_SD, (samples, 1)
    )
    wind_from = np.array([x.wind_dir_deg or 0.0 for x in cond])[None, :] + rng.normal(
        0, WIND_DIR_SD, (samples, 1)
    )
    bearing = np.array([x.bearing_deg for x in cond])[None, :]
    head = wind * np.cos(np.radians(wind_from - bearing))
    per_100 = (
        c["c0"]
        + c["aero"] * (speed + head) ** 2 * (288.15 / (273.15 + temp))
        + c["heat"] * np.maximum(0.0, T_BASE - temp) / speed
        + c.get("cool", 0.0) * np.maximum(0.0, temp - T_COOL) / speed
        + c.get("time", 0.0) / speed
        + c["cold"] * np.maximum(0.0, T_BASE - temp)
    )
    per_100 = np.maximum(per_100, model.floor_kwh_100km)  # never better than the best measured case
    climb, descent = sum(x.climb_m for x in cond), sum(x.descent_m for x in cond)
    hills = (c["climb"] * climb - c["regen"] * descent)[:, 0]
    kwh = (per_100 * km / 100).sum(axis=1) + hills
    centre = (model.residual_q10 + model.residual_q90) / 2
    return kwh + rng.normal(centre, model_error_sd(model), samples) * km.sum() / 100


def coefficient_draws(model: RangeModel, samples: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """One coefficient set per simulated day, as (samples, 1) columns: the model's bootstrap refits, or
    for the specs model ±20 % around each value. Every route gets the same sets in the same order."""
    names = ("c0", "aero", "heat", "cold", "cool", "time", "climb", "regen")
    draws = model.coef_draws or [
        {k: model.coef.get(k, 0.0) * rng.lognormal(0, SPECS_SD) for k in names} for _ in range(200)
    ]
    pick = np.arange(samples) % len(draws)
    return {k: np.array([d.get(k, 0.0) for d in draws])[pick][:, None] for k in names}


def model_error_sd(model: RangeModel) -> float:
    """The model's real error in kWh/100 km, without the battery-reading noise of short training drives.

    A measured drive of L km is off by about READING_NOISE_KWH, i.e. 100·noise/L kWh/100 km, on top of what
    the model gets wrong. Its residual spread holds both, so the reading part is taken out (keeping at least
    40 % of the spread, in case the noise is overestimated); a long trip's prediction carries only the rest.
    """
    total = max(model.residual_q90 - model.residual_q10, 0.0) / 2.563  # 10-90 % of a normal is 2.563 sd
    reading = 100 * READING_NOISE_KWH / max(model.median_km, 1.0)
    return float(np.sqrt(max(total**2 - reading**2, (0.4 * total) ** 2)))


def estimate(
    route: Route, pieces: list[Piece], levers: Levers, weather: dict, terrain, model: RangeModel
) -> RouteEstimate:
    cond = conditions(pieces, levers, weather, terrain)
    draws = simulate(cond, model)
    p10, p50, p90 = (float(v) for v in np.quantile(draws, [0.1, 0.5, 0.9]))
    soc = levers.start_soc - draws / levers.capacity_kwh * 100
    to_soc = lambda kwh: levers.start_soc - kwh / levers.capacity_kwh * 100  # noqa: E731
    return RouteEstimate(
        route=route,
        km=sum(x.km for x in cond),
        minutes=sum(x.km / x.speed_kph for x in cond) * 60,
        kwh_p10=p10,
        kwh_p50=p50,
        kwh_p90=p90,
        breakdown=energy_breakdown(cond, model),
        arrival_soc_p10=to_soc(p90),
        arrival_soc_p50=to_soc(p50),
        arrival_soc_p90=to_soc(p10),
        p_reserve=float(np.mean(soc >= levers.reserve_soc)),
        climb_m=sum(x.climb_m for x in cond),
        descent_m=sum(x.descent_m for x in cond),
        weather_complete=all(x.temp_c is not None for x in cond),
        conditions=cond,
        draws=draws,
    )


def differences(estimates: list[RouteEstimate]) -> list[str]:
    """Plain-language comparison of each route with the one using least energy.

    Every route is simulated on the same random days (same seed), so "how often is it really cheaper"
    compares like with like: the forecast error that hurts one route hurts the others too.
    """
    if len(estimates) < 2:
        return []
    best = min(estimates, key=lambda e: e.kwh_p50)
    lines = []
    for e in estimates:
        if e is best:
            continue
        extra = e.kwh_p50 - best.kwh_p50
        causes = {k: e.breakdown[k] - best.breakdown[k] for k in COMPONENTS}
        worse, better = max(causes, key=causes.get), min(causes, key=causes.get)
        offset = (
            f", partly offset by {LESS[better]} ({causes[better]:+.1f} kWh)" if causes[better] < -0.2 else ""
        )
        odds = (
            float(np.mean(best.draws < e.draws)) if best.draws is not None and e.draws is not None else None
        )
        sure = "" if odds is None else f" {best.route.label} uses less on {odds:.0%} of simulated days."
        lines.append(
            f"{e.route.label} needs {extra:.1f} kWh more than {best.route.label}: "
            f"{e.km - best.km:+.0f} km, {e.minutes - best.minutes:+.0f} min, "
            f"{e.climb_m - best.climb_m:+.0f} m of climbing. Mostly {MORE[worse]} "
            f"({causes[worse]:+.1f} kWh){offset}.{sure}"
        )
    return lines


def rival_first(estimates: list[RouteEstimate]) -> list[RouteEstimate]:
    """The first route, then its closest rival in energy, then the rest: the pair worth comparing leads."""
    if len(estimates) < 3:
        return list(estimates)
    first, rest = estimates[0], estimates[1:]
    rival = min(rest, key=lambda e: abs(e.kwh_p50 - first.kwh_p50))
    return [first, rival, *(e for e in rest if e is not rival)]


def win_shares(estimates: list[RouteEstimate]) -> list[float]:
    """How often each route uses the least energy over the same simulated days; ties are split evenly.

    Without simulated days, the route with the lowest median takes it all."""
    if not estimates:
        return []
    if any(e.draws is None for e in estimates):
        best = min(range(len(estimates)), key=lambda i: estimates[i].kwh_p50)
        return [1.0 if i == best else 0.0 for i in range(len(estimates))]
    draws = np.vstack([e.draws for e in estimates])
    lowest = draws == draws.min(axis=0)
    return [float(x) for x in (lowest / lowest.sum(axis=0)).mean(axis=1)]


class PlaceNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Comparison:
    origin: Place
    destination: Place
    estimates: list[RouteEstimate]


def compare_routes(
    origin: str, destination: str, vias: list[list[str]], levers: Levers, model: RangeModel, terrain,
    http: httpx.Client,
) -> Comparison:  # fmt: skip
    """Look up the places, fetch candidate routes and price each one in the forecast weather."""

    def find(query: str) -> Place:
        place = geocode(query, http)
        if place is None:
            raise PlaceNotFound(query)
        return place

    start, end = find(origin), find(destination)
    routes = fetch_routes(start, end, [[find(q) for q in through] for through in vias if through], http)
    cut = {r.label: cut_pieces(r) for r in routes}
    cells = sorted({c for pieces in cut.values() for c in weather_cells(pieces)})
    try:
        weather = fetch_route_weather(cells, http)
    except (httpx.HTTPError, ValueError):
        weather = {}
    depart = max(levers.depart, datetime.now(UTC) - timedelta(hours=1))
    lever = Levers(depart, levers.start_soc, levers.capacity_kwh, levers.speed_cap_kph, levers.pace,
                   levers.reserve_soc)  # fmt: skip
    return Comparison(start, end, [estimate(r, cut[r.label], lever, weather, terrain, model) for r in routes])
