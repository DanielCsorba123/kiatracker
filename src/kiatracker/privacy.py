"""Location helpers that keep coordinates out of anything shown publicly."""

import math

EARTH_RADIUS_KM = 6371.0


def zone_of(
    lat: float | None, lon: float | None, home: tuple[float, float] | None, radius_km: float
) -> str | None:
    """Label a position 'home' or 'other' so derived data can be shared without coordinates."""
    if lat is None or lon is None or home is None:
        return None
    return "home" if haversine_km((lat, lon), home) <= radius_km else "other"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
