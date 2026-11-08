import pytest

from kiatracker.forecast.features import air_density_ratio, physics
from kiatracker.forecast.specs import EV3, prior_coefficients


def test_prior_coefficients_follow_from_the_specs():
    coef = prior_coefficients(EV3)
    assert coef["aero"] == pytest.approx(0.00095, rel=0.05)
    assert coef["c0"] == pytest.approx(6.0, abs=0.5)
    assert coef["heat"] == pytest.approx(15.0)


def test_prior_matches_real_world_motorway_consumption():
    coef = prior_coefficients(EV3)
    x = physics(110, 15, 110**2)
    kwh = coef["c0"] + coef["aero"] * x["aero"] + coef["heat"] * x["heat"]
    assert 16 < kwh < 19


def test_cold_air_is_denser_so_drag_costs_more():
    assert air_density_ratio(-10) == pytest.approx(1.095, abs=0.005)
    assert physics(100, -10, 100**2)["aero"] > physics(100, 20, 100**2)["aero"] * 1.1


def test_climbing_costs_lifting_the_car_and_descents_return_part_of_it():
    coef = prior_coefficients(EV3)
    lift_kwh_per_m = EV3.mass_kg * 9.81 / 3.6e6
    assert coef["climb"] == pytest.approx(lift_kwh_per_m / EV3.drivetrain_efficiency)
    assert coef["regen"] == pytest.approx(lift_kwh_per_m * EV3.regen_efficiency)
    assert coef["regen"] < coef["climb"]
