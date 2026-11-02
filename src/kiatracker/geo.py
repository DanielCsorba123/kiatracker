"""Direction maths for wind: travel bearing and the headwind component along a path."""

import math

from kiatracker.privacy import haversine_km


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Initial compass bearing from a to b (0 = north, 90 = east)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    x = math.sin(lon2 - lon1) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.degrees(math.atan2(x, y)) % 360


def headwind_kph(wind_kph: float, wind_from_deg: float, bearing: float) -> float:
    """Wind component against the direction of travel; negative is a tailwind.

    Meteorological wind direction is where the wind comes from, so driving towards it is a headwind.
    """
    return wind_kph * math.cos(math.radians(wind_from_deg - bearing))


def path_airspeed_sq(
    points: list[tuple[float, float]], speed_kph: float, wind_kph: float, wind_from_deg: float
) -> float:
    """Distance-weighted mean of (v + headwind)² over the path's segments: what air drag actually sees.

    Squaring per segment matters: out and back into the wind has a mean headwind of zero but still costs
    ((v+w)² + (v-w)²)/2 = v² + w². With no path to go on, wind is averaged over all directions: v² + w²/2.
    """
    total = weighted = 0.0
    for a, b in zip(points, points[1:], strict=False):
        km = haversine_km(a, b)
        if km > 0:
            total += km
            weighted += km * (speed_kph + headwind_kph(wind_kph, wind_from_deg, bearing_deg(a, b))) ** 2
    return weighted / total if total else speed_kph**2 + wind_kph**2 / 2


def path_headwind(points: list[tuple[float, float]], wind_kph: float, wind_from_deg: float) -> float:
    """Distance-weighted mean headwind over the segments between consecutive points."""
    total = weighted = 0.0
    for a, b in zip(points, points[1:], strict=False):
        km = haversine_km(a, b)
        if km > 0:
            total += km
            weighted += km * headwind_kph(wind_kph, wind_from_deg, bearing_deg(a, b))
    return weighted / total if total else 0.0
