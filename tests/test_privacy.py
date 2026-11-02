import pytest

from kiatracker.privacy import haversine_km


def test_haversine_one_degree_latitude():
    assert haversine_km((47.0, 19.0), (48.0, 19.0)) == pytest.approx(111.2, abs=0.1)


def test_haversine_same_point_is_zero():
    assert haversine_km((47.5, 19.0), (47.5, 19.0)) == 0
