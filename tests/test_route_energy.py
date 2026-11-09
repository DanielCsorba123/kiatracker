from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kiatracker.forecast.model import RangeModel
from kiatracker.route_energy import (
    Levers,
    conditions,
    differences,
    energy_breakdown,
    estimate,
    rival_first,
    simulate,
    weather_cells,
    win_shares,
)
from kiatracker.routing import Piece, Route

DEPART = datetime(2026, 11, 7, 5, 0, tzinfo=UTC)
MODEL = RangeModel(
    {"c0": 6.0, "aero": 0.001, "heat": 15.0, "climb": 0.006, "regen": 0.003}, -1.0, 1.0, 20, "x"
)


def piece(seq, lat, speed=60.0, bearing=0.0, km=1.0):
    return Piece(seq, km, speed, bearing, (lat, 18.0), (lat + 0.009, 18.0))


def hourly(temps, wind=20.0, wind_from=0.0):
    return {
        "time": [f"2026-11-07T{h:02d}:00" for h in range(24)],
        "temperature_2m": temps,
        "wind_speed_10m": [wind] * 24,
        "wind_direction_10m": [wind_from] * 24,
    }


class Ramp:
    def elevation(self, lat, lon):
        return (lat - 47.0) * 10_000  # 90 m per piece going north


def levers(**changes):
    return Levers(**{"depart": DEPART, "start_soc": 80.0, "capacity_kwh": 81.4} | changes)


def test_each_piece_gets_the_hour_it_is_driven_in_and_its_own_headwind():
    # 60 pieces of 1 km at 60 km/h: the last one is driven around 05:59
    pieces = [piece(i + 1, 47.0 + 0.009 * i) for i in range(60)]
    # cell 47.k is 10·k °C warmer, and every cell warms 1 °C per hour
    weather = {(round(47 + k / 10, 1), 18.0): hourly([10.0 * k + h for h in range(24)]) for k in range(6)}
    cond = conditions(pieces, levers(), weather, Ramp())
    assert cond[0].temp_c == 5.0  # cell 47.0 at 05:00
    assert cond[-1].temp_c == 56.0  # cell 47.5, 05:59 rounds to 06:00
    assert cond[0].headwind_kph == pytest.approx(20)  # northbound into a north wind
    assert cond[0].climb_m == pytest.approx(90) and cond[0].descent_m == 0


def test_speed_cap_and_pace():
    cond = conditions([piece(1, 47.0, speed=130.0)], levers(speed_cap_kph=110.0, pace=0.9), {}, None)
    assert cond[0].speed_kph == pytest.approx(99.0)
    assert cond[0].temp_c is None and cond[0].climb_m == 0  # no forecast, no terrain: flagged and flat


def test_breakdown_adds_up_to_the_model():
    cond = conditions([piece(1, 47.0, km=10.0)], levers(), {(47.0, 18.0): hourly([8.0] * 24)}, Ramp())
    parts = energy_breakdown(cond, MODEL)
    total = sum(parts.values())
    c = cond[0]
    expected = MODEL.predict(c.speed_kph, c.temp_c, (c.speed_kph + c.headwind_kph) ** 2, 900.0, 0.0) / 10
    assert total == pytest.approx(expected)
    assert parts["wind"] > 0 and parts["climb"] > 0 and parts["regen"] == 0


def test_monte_carlo_spreads_around_the_central_estimate():
    cond = conditions(
        [piece(i + 1, 47.0, km=5.0) for i in range(20)], levers(), {(47.0, 18.0): hourly([5.0] * 24)}, None
    )
    central = sum(energy_breakdown(cond, MODEL).values())
    draws = simulate(cond, MODEL, samples=2000, seed=1)
    p10, p50, p90 = (float(x) for x in __import__("numpy").quantile(draws, [0.1, 0.5, 0.9]))
    assert p10 < central < p90 and p50 == pytest.approx(central, rel=0.05)


def test_estimate_reports_arrival_charge_and_its_odds():
    pieces = [piece(i + 1, 47.0, km=5.0) for i in range(20)]
    route = Route("Fastest", 100.0, 100.0, [(47.0, 18.0), (47.9, 18.0)], [100.0], [6000.0])
    result = estimate(route, pieces, levers(), {(47.0, 18.0): hourly([5.0] * 24)}, None, MODEL)
    assert result.kwh_p10 < result.kwh_p50 < result.kwh_p90
    assert result.arrival_soc_p50 == pytest.approx(80 - result.kwh_p50 / 81.4 * 100)
    assert 0.99 <= result.p_reserve <= 1.0  # ~17 kWh of 65 usable: arrives well above 10 %
    assert result.weather_complete


def test_weather_cells_are_the_rounded_piece_midpoints():
    assert weather_cells([piece(1, 47.0), piece(2, 47.04), piece(3, 47.1)]) == [(47.0, 18.0), (47.1, 18.0)]


def test_differences_name_the_cause_and_how_often_the_cheaper_route_wins():
    flat = [piece(i + 1, 47.0, km=5.0) for i in range(20)]
    route = Route("Flat", 100.0, 100.0, [(47.0, 18.0)], [100.0], [6000.0])
    hilly = Route("Hilly", 95.0, 95.0, [(47.0, 18.0)], [95.0], [5700.0])
    weather = {(47.0, 18.0): hourly([5.0] * 24)}
    a = estimate(route, flat, levers(), weather, None, MODEL)
    b = estimate(
        hilly, flat[:19], levers(), weather, Ramp(), MODEL
    )  # 5 km shorter, but climbs 90 m per piece
    [line] = differences([a, b])
    assert line.startswith("Hilly needs") and "climbing" in line and "Flat uses less on" in line


def test_battery_reading_noise_of_short_drives_is_not_charged_to_long_trips():
    from kiatracker.route_energy import model_error_sd

    noisy = RangeModel(MODEL.coef, -4.0, 4.0, 20, "x", median_km=10.0)  # sd ≈ 3.1, reading noise 4.0
    assert model_error_sd(noisy) == pytest.approx(0.4 * 8 / 2.563)  # floor: 40 % kept
    clean = RangeModel(MODEL.coef, -4.0, 4.0, 20, "x", median_km=40.0)  # reading noise 1.0
    assert model_error_sd(clean) == pytest.approx((3.121**2 - 1.0) ** 0.5, rel=0.01)


@pytest.fixture
def two_routes():
    flat = [piece(i + 1, 47.0, km=5.0) for i in range(20)]
    weather = {(47.0, 18.0): hourly([5.0] * 24)}
    a = estimate(
        Route("Flat", 100.0, 100.0, [(47.0, 18.0)], [100.0], [6000.0]), flat, levers(), weather, None, MODEL
    )
    b = estimate(
        Route("Hilly", 95.0, 95.0, [(47.0, 18.0)], [95.0], [5700.0]),
        flat[:19],
        levers(),
        weather,
        Ramp(),
        MODEL,
    )
    return a, b


def test_win_shares_sum_to_one_and_follow_the_draws(two_routes):
    shares = win_shares(list(two_routes))
    assert sum(shares) == pytest.approx(1) and shares[0] > shares[1]


def test_win_shares_without_draws_pick_the_lowest_median(two_routes):
    a, b = (replace(e, draws=None) for e in two_routes)
    assert win_shares([b, a]) == [0.0, 1.0]


def test_win_shares_single_route(two_routes):
    assert win_shares([two_routes[0]]) == [1.0]


def test_rival_first_puts_the_closest_alternative_second(two_routes):
    a, b = two_routes
    far = replace(b, kwh_p50=b.kwh_p50 + 10, route=replace(b.route, label="Far"))
    assert [e.route.label for e in rival_first([a, far, b])] == ["Flat", "Hilly", "Far"]
    assert rival_first([a]) == [a]
