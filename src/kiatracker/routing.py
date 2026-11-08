"""Candidate routes between two places, cut into ~1 km pieces with their own speed and direction.

Routing is OSRM (open source, OpenStreetMap roads, no key): the public demo server by default, or your own
with KIATRACKER_OSRM_URL. Place names are looked up with OpenStreetMap's Nominatim; typing "lat, lon" skips
that. Only the places you type are sent, never recorded drives.
"""

import os
import re
from dataclasses import dataclass

import httpx

from kiatracker.geo import bearing_deg

OSRM_URL = os.environ.get("KIATRACKER_OSRM_URL", "https://router.project-osrm.org").rstrip("/")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "kiatracker (https://github.com/DanielCsorba123/kiatracker)"  # Nominatim's policy asks for one
COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Route:
    label: str
    distance_km: float
    duration_min: float
    points: list[tuple[float, float]]  # (lat, lon), one more than edges
    edge_km: list[float]
    edge_s: list[float]
    roads: str = ""  # the main roads in driving order, e.g. "S33, A1, A21, A2"


@dataclass(frozen=True)
class Piece:
    seq: int
    km: float
    speed_kph: float  # OSRM's typical speed on these roads, before any speed cap
    bearing_deg: float
    start: tuple[float, float]
    end: tuple[float, float]


def geocode(query: str, http: httpx.Client) -> Place | None:
    if match := COORDINATES.match(query):
        lat, lon = float(match[1]), float(match[2])
        return Place(f"{lat:.3f}, {lon:.3f}", lat, lon)
    response = http.get(
        NOMINATIM_URL,
        params={"q": query, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    found = response.json()
    if not found:
        return None
    hit = found[0]
    return Place(hit.get("display_name", query).split(",")[0], float(hit["lat"]), float(hit["lon"]))


def _osrm(places: list[Place], http: httpx.Client, alternatives: bool) -> list[dict]:
    path = ";".join(f"{p.lon},{p.lat}" for p in places)
    response = http.get(
        f"{OSRM_URL}/route/v1/driving/{path}",
        params={
            "alternatives": "true" if alternatives else "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "steps": "true",  # for the road names
        },
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("routes", []) if body.get("code") == "Ok" else []


def main_roads(raw: dict, share: float = 0.04) -> str:
    """Road numbers (or names) carrying at least `share` of the distance, in the order they are driven."""
    km: dict[str, float] = {}
    for leg in raw["legs"]:
        for step in leg.get("steps", []):
            road = (step.get("ref") or step.get("name") or "").split(";")[0].replace(" ", "")
            if road:
                km[road] = km.get(road, 0.0) + step["distance"] / 1000
    total = sum(km.values())
    return ", ".join(road for road, length in km.items() if total and length >= share * total)


def _route(label: str, raw: dict) -> Route:
    edge_km = [d / 1000 for leg in raw["legs"] for d in leg["annotation"]["distance"]]
    edge_s = [s for leg in raw["legs"] for s in leg["annotation"]["duration"]]
    points = [(lat, lon) for lon, lat in raw["geometry"]["coordinates"]]
    return Route(
        label, raw["distance"] / 1000, raw["duration"] / 60, points, edge_km, edge_s, main_roads(raw)
    )


def fetch_routes(
    origin: Place, destination: Place, vias: list[list[Place]], http: httpx.Client
) -> list[Route]:
    """OSRM's fastest route and its alternatives, then one route through each list of via places."""
    direct = _osrm([origin, destination], http, alternatives=True)
    routes = [_route("Fastest" if i == 0 else f"Alternative {i}", r) for i, r in enumerate(direct)]
    for through in vias:
        found = _osrm([origin, *through, destination], http, alternatives=False)
        if found:
            routes.append(_route("via " + ", ".join(p.name for p in through), found[0]))
    return routes


def cut_pieces(route: Route, length_km: float = 1.0) -> list[Piece]:
    """Consecutive edges merged until each piece is about `length_km` long."""
    pieces: list[Piece] = []
    first, km, seconds = 0, 0.0, 0.0
    for i, (edge_km, edge_s) in enumerate(zip(route.edge_km, route.edge_s, strict=True)):
        km += edge_km
        seconds += edge_s
        if km >= length_km - 1e-9 or i == len(route.edge_km) - 1:
            start, end = route.points[first], route.points[i + 1]
            speed = km / (seconds / 3600) if seconds > 0 else 50.0
            pieces.append(Piece(len(pieces) + 1, km, speed, bearing_deg(start, end), start, end))
            first, km, seconds = i + 1, 0.0, 0.0
    return pieces
