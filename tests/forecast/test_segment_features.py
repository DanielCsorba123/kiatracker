from datetime import UTC, datetime, timedelta

import pytest

from kiatracker.forecast.features import air_density_ratio, segment_features
from kiatracker.segments import Segment

T0 = datetime(2026, 11, 7, 5, 0, tzinfo=UTC)


def seg(km, speed, temp, headwind, climb=0.0, descent=0.0):
    return Segment(1, 1, T0, T0 + timedelta(hours=km / speed), km, speed, 0.0, temp, 20.0, 0.0, headwind,
                   climb, descent)  # fmt: skip


def test_each_stretch_counts_with_its_own_speed_temperature_and_wind():
    # a cold slow town stretch then a mild fast motorway stretch into the wind
    town, motorway = seg(10, 30, 0, 0, climb=50), seg(30, 120, 10, 20, descent=20)
    x = segment_features([town, motorway], distance_km=40)
    assert x["temp_c"] == pytest.approx((10 * 0 + 30 * 10) / 40)
    assert x["headwind_kph"] == pytest.approx(30 * 20 / 40)
    assert x["aero"] == pytest.approx(
        (10 * 30**2 * air_density_ratio(0) + 30 * 140**2 * air_density_ratio(10)) / 40
    )
    # heating draws power by the hour: 18 K for 1/3 h plus 8 K for 1/4 h, per km
    assert x["heat"] == pytest.approx((18 * 10 / 30 + 8 * 30 / 120) / 40)
    assert (x["climb"], x["regen"]) == (pytest.approx(125.0), pytest.approx(-50.0))  # per 100 km


def test_straight_lines_are_scaled_up_to_the_road_distance():
    # 10 km as the crow flies in 20 minutes, but the odometer says 15 km: the car drove 45 km/h, not 30
    x = segment_features([seg(10, 30, 18, 0)], distance_km=15)
    assert x["aero"] == pytest.approx(45**2 * air_density_ratio(18))


def test_unknown_weather_on_any_stretch_means_no_segment_features():
    assert segment_features([seg(10, 30, None, None)], distance_km=10) is None
    assert segment_features([], distance_km=10) is None


def test_unknown_terrain_counts_as_flat():
    s = seg(10, 30, 5, 0)
    s = Segment(*[*s.__dict__.values()][:11], None, None)
    assert segment_features([s], 10)["climb"] == 0.0
