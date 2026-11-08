import httpx
import pytest
import respx

from kiatracker.routing import Place, Route, cut_pieces, fetch_routes, geocode

A, B, VIA = Place("A", 47.0, 18.0), Place("B", 47.0, 18.3), Place("V", 47.1, 18.15)


def osrm_body(*routes):
    """Each route: list of (lat, lon) points; edges are 0.5 km at 60 km/h, split into one leg per 4 edges."""
    out = []
    for points in routes:
        edges = len(points) - 1
        legs = [list(range(i, min(i + 4, edges))) for i in range(0, edges, 4)]
        out.append({
            "distance": 500.0 * edges,
            "duration": 30.0 * edges,
            "geometry": {"coordinates": [[lon, lat] for lat, lon in points]},
            "legs": [{"annotation": {"distance": [500.0] * len(leg), "duration": [30.0] * len(leg)}}
                     for leg in legs],
        })  # fmt: skip
    return {"code": "Ok", "routes": out}


def line(n, lat=47.0):
    return [(lat, 18.0 + 0.3 * i / (n - 1)) for i in range(n)]


def test_coordinates_are_parsed_without_any_request():
    with respx.mock(assert_all_called=False) as mock:
        place = geocode("47.5, 18.25", httpx.Client())
        assert mock.calls.call_count == 0
    assert (place.lat, place.lon) == (47.5, 18.25)


@respx.mock
def test_place_names_are_looked_up_once_with_an_identifying_agent():
    route = respx.get("https://nominatim.openstreetmap.org/search").respond(
        json=[{"lat": "48.41", "lon": "15.60", "display_name": "Krems an der Donau, Austria"}]
    )
    place = geocode("Krems", httpx.Client())
    assert place == Place("Krems an der Donau", 48.41, 15.60)
    assert "kiatracker" in route.calls[0].request.headers["user-agent"]


@respx.mock
def test_unknown_place_is_none():
    respx.get("https://nominatim.openstreetmap.org/search").respond(json=[])
    assert geocode("Nowhere at all", httpx.Client()) is None


@respx.mock
def test_routes_with_alternatives_and_via_points():
    direct = respx.get(url__regex=r".*/route/v1/driving/18\.0,47\.0;18\.3,47\.0\?.*").respond(
        json=osrm_body(line(9), line(11, 47.02))
    )
    via = respx.get(url__regex=r".*/route/v1/driving/18\.0,47\.0;18\.15,47\.1;18\.3,47\.0\?.*").respond(
        json=osrm_body(line(13, 47.05))
    )
    routes = fetch_routes(A, B, [[VIA]], httpx.Client())
    assert [r.label for r in routes] == ["Fastest", "Alternative 1", "via V"]
    assert routes[0].distance_km == 4.0 and routes[0].duration_min == 4.0
    assert len(routes[2].points) == 13 and len(routes[2].edge_km) == 12
    assert "alternatives=true" in str(direct.calls[0].request.url)
    assert "alternatives=false" in str(via.calls[0].request.url)


def test_pieces_are_about_a_kilometre_with_their_own_speed_and_direction():
    points = line(9)  # 8 edges of 0.5 km
    route = Route("r", 4.0, 4.0, points, [0.5] * 8, [30.0, 30.0, 30.0, 30.0, 15.0, 15.0, 15.0, 15.0])
    pieces = cut_pieces(route, length_km=1.0)
    assert [p.km for p in pieces] == [1.0, 1.0, 1.0, 1.0]
    assert [round(p.speed_kph) for p in pieces] == [60, 60, 120, 120]
    assert pieces[0].bearing_deg == pytest.approx(90, abs=1)  # due east
    assert (pieces[0].start, pieces[0].end) == (points[0], points[2])
    assert pieces[-1].end == points[-1]


def test_short_tail_is_kept_as_its_own_piece():
    route = Route("r", 1.5, 1.5, line(4), [0.5] * 3, [30.0] * 3)
    assert [p.km for p in cut_pieces(route, length_km=1.0)] == [1.0, 0.5]
