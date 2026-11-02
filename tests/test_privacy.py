import pytest

from kiatracker.privacy import haversine_km, zone_of


def test_haversine_one_degree_latitude():
    assert haversine_km((47.0, 19.0), (48.0, 19.0)) == pytest.approx(111.2, abs=0.1)


def test_zone_home_other_and_unknown():
    home = (47.5, 19.0)
    assert zone_of(47.501, 19.001, home, 0.3) == "home"
    assert zone_of(47.6, 19.0, home, 0.3) == "other"
    assert zone_of(None, None, home, 0.3) is None
    assert zone_of(47.5, 19.0, None, 0.3) is None


def test_haversine_same_point_is_zero():
    assert haversine_km((47.5, 19.0), (47.5, 19.0)) == 0
