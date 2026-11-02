import pytest

from kiatracker.geo import bearing_deg, headwind_kph, path_headwind


def test_bearing_north_and_east():
    assert bearing_deg((47.0, 18.0), (47.1, 18.0)) == pytest.approx(0, abs=0.01)
    assert bearing_deg((47.0, 18.0), (47.0, 18.1)) == pytest.approx(90, abs=0.1)
    assert bearing_deg((47.1, 18.0), (47.0, 18.0)) == pytest.approx(180, abs=0.01)


@pytest.mark.parametrize(
    "wind_from,bearing,expected",
    [(0, 0, 20), (180, 0, -20), (90, 0, 0), (270, 90, -20), (45, 0, 20 * 2**-0.5)],
)
def test_headwind_component(wind_from, bearing, expected):
    """Wind direction is where it blows FROM: driving north into a north wind is a full headwind."""
    assert headwind_kph(20, wind_from, bearing) == pytest.approx(expected, abs=1e-9)


def test_path_headwind_is_distance_weighted():
    # 0.1 degree north (11 km) then 0.01 degree east (~0.8 km), north wind
    points = [(47.0, 18.0), (47.1, 18.0), (47.1, 18.01)]
    assert path_headwind(points, 20, 0) == pytest.approx(20 * 11.12 / (11.12 + 0.76), abs=0.2)


def test_path_without_movement_has_no_headwind():
    assert path_headwind([(47.0, 18.0), (47.0, 18.0)], 30, 0) == 0
    assert path_headwind([(47.0, 18.0)], 30, 0) == 0
