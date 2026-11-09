import pytest

from kiatracker.forecast.features import air_density_ratio, physics
from kiatracker.forecast.model import RangeModel
from kiatracker.forecast.specs import EV3, prior_coefficients, usable_kwh

FLAT = ("aero", "heat", "cold", "cool", "time")


def flat_kwh(coef, speed, temp):
    x = physics(speed, temp, speed**2)
    return coef["c0"] + sum(coef[f] * x[f] for f in FLAT)


def test_prior_coefficients_follow_from_the_specs():
    coef = prior_coefficients(EV3)
    assert coef["aero"] == pytest.approx(0.00095, rel=0.05)
    assert coef["c0"] == pytest.approx(6.2, abs=0.3)
    assert coef["heat"] >= 0 and coef["cold"] > 0 and coef["time"] > 50
    assert coef["cool"] == pytest.approx(12.0)


def test_prior_reproduces_the_real_world_benchmarks():
    coef = prior_coefficients(EV3)
    for b in EV3.benchmarks:
        assert flat_kwh(coef, b.speed_kph, b.temp_c) == pytest.approx(b.kwh_per_100km, rel=0.02), b.label


def test_no_prediction_beats_the_best_measured_case():
    model = RangeModel(prior_coefficients(EV3), 0.0, 0.0, 0, "specs")
    assert EV3.best_range_km == pytest.approx(672, abs=5)
    for speed, temp in ((15, 22), (30, 20), (40, 30), (60, 20)):
        assert EV3.usable_kwh / model.predict(speed, temp, speed**2) * 100 <= EV3.best_range_km + 1e-6
    low, _, _ = RangeModel(prior_coefficients(EV3), -5.0, 5.0, 0, "x").interval(30, 23, 900)
    assert low >= EV3.best_kwh_per_100km - 1e-9  # not even the optimistic end of the interval


def test_slow_hot_driving_is_not_free():
    """At 20 km/h in 35 °C the air conditioning and the time-based load dominate."""
    assert EV3.usable_kwh / flat_kwh(prior_coefficients(EV3), 20, 35) * 100 < 450


def test_reported_capacity_is_the_gross_size():
    assert usable_kwh(81.4) == pytest.approx(78.0)
    assert usable_kwh(None) == pytest.approx(78.0)


def test_cold_air_is_denser_so_drag_costs_more():
    assert air_density_ratio(-10) == pytest.approx(1.095, abs=0.005)
    assert physics(100, -10, 100**2)["aero"] > physics(100, 20, 100**2)["aero"] * 1.1


def test_climbing_costs_lifting_the_car_and_descents_return_part_of_it():
    coef = prior_coefficients(EV3)
    lift_kwh_per_m = EV3.mass_kg * 9.81 / 3.6e6
    assert coef["climb"] == pytest.approx(lift_kwh_per_m / EV3.drivetrain_efficiency)
    assert coef["regen"] == pytest.approx(lift_kwh_per_m * EV3.regen_efficiency)
    assert coef["regen"] < coef["climb"]
