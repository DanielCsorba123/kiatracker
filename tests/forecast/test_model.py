from datetime import datetime

import pytest

from kiatracker.forecast.features import air_density_ratio, drive_features
from kiatracker.forecast.model import MIN_DRIVES, NotEnoughData, RangeModel, fit, fit_coefficients
from kiatracker.synthetic import TRUTH


def row(aero, heat, kwh, km=20.0):
    return {
        "aero": aero,
        "heat": heat,
        "kwh_per_100km": kwh,
        "distance_km": km,
        "start_ts": datetime(2026, 1, 1),
    }


def test_recovers_the_simulators_true_physics(demo):
    model = fit(drive_features(demo))
    assert model.coef["c0"] == pytest.approx(TRUTH["c0"], rel=0.15)
    assert model.coef["aero"] == pytest.approx(TRUTH["c_aero"], rel=0.15)
    assert model.coef["heat"] == pytest.approx(TRUTH["c_heat"], rel=0.15)


def test_negative_cost_is_dropped_and_refit():
    # independent aero and heat; consumption falls as "heat" rises, which is physically impossible
    rows = [
        row(aero=2500 + 300 * (i % 5), heat=(i % 4) / 10, kwh=12 + 0.002 * 300 * (i % 5) - 3 * (i % 4) / 10)
        for i in range(20)
    ]
    model = fit(rows)
    assert model.coef["heat"] == 0
    assert model.coef["aero"] == pytest.approx(0.002, rel=0.05)


def test_intercept_is_never_negative():
    # a narrow speed band makes the unconstrained intercept negative
    rows = [row(aero=2400 + 10 * i, heat=0.1, kwh=-5 + 0.008 * (2400 + 10 * i)) for i in range(20)]
    model = fit(rows)
    assert all(value >= 0 for value in model.coef.values())
    assert model.predict(30, 25, 30**2) > 0


def test_too_few_drives_says_how_many_more():
    with pytest.raises(NotEnoughData) as err:
        fit([row(2500, 0.2, 16)] * (MIN_DRIVES - 1))
    assert err.value.needed == 1


def test_prediction_and_interval(demo):
    model = fit(drive_features(demo))
    lo, mid, hi = model.interval(speed_kph=50, temp_c=0, airspeed_sq=50**2)
    assert lo < mid < hi
    assert mid == pytest.approx(model.predict(50, 0, 50**2))
    assert model.predict(50, -5, 2500) > model.predict(50, 15, 2500)


def test_save_and_load_round_trip(demo, tmp_path):
    model = fit(drive_features(demo))
    path = tmp_path / "models" / "range.json"
    model.save(path)
    assert RangeModel.load(path) == model
    assert "lat" not in path.read_text() and "lon" not in path.read_text()


def test_explanations_use_plain_units(demo):
    lines = fit(drive_features(demo)).explain(speed_kph=50)
    assert any("headwind" in line for line in lines) and any("°C" in line for line in lines)


def test_strong_pull_keeps_coefficients_at_the_prior_and_none_is_a_plain_fit():
    from kiatracker.forecast.model import fit_coefficients

    prior = {"c0": 6.0, "aero": 0.001, "heat": 15.0}
    rows = [row(aero=2500 + 300 * (i % 5), heat=(i % 4) / 10, kwh=20.0 + (i % 3)) for i in range(20)]
    pulled = fit_coefficients(rows, prior=prior, strength=1e6)
    assert {k: pulled[k] for k in prior} == pytest.approx(prior, rel=0.02)
    assert fit_coefficients(rows, prior=prior, strength=0) == pytest.approx(fit_coefficients(rows), rel=1e-6)


def test_training_reports_the_specs_model_and_the_chosen_pull(demo):
    from kiatracker.forecast.train import train

    trained = train(demo)
    assert {"model", "specs", "mean", "temperature_only"} <= set(trained.backtest)
    assert trained.model.prior_strength >= 0


def test_hills_are_learned_from_climb_and_descent():
    # climb in m per 100 km; regen is minus the descent, so its (non-negative) coefficient lowers consumption
    rows = []
    for i in range(30):
        climb, descent = 100.0 * (i % 6), 80.0 * (i % 5)
        aero, heat = 3000 + 200 * (i % 7), (i % 3) / 10
        kwh = 6 + 0.001 * aero + 15 * heat + 0.006 * climb - 0.003 * descent
        rows.append(row(aero, heat, kwh) | {"climb": climb, "regen": -descent})
    model = fit(rows)
    assert model.coef["climb"] == pytest.approx(0.006, rel=0.02)
    assert model.coef["regen"] == pytest.approx(0.003, rel=0.02)
    flat = model.predict(60, 10, 3600)
    assert model.predict(60, 10, 3600, climb=500) == pytest.approx(flat + 3.0, rel=0.02)


def test_model_saved_before_hills_still_predicts(tmp_path):
    path = tmp_path / "old.json"
    old = RangeModel({"c0": 6.0, "aero": 0.001, "heat": 15.0}, -1, 1, 20, "2026-11-01")
    old.save(path)
    assert RangeModel.load(path).predict(60, 10, 3600, climb=300) == pytest.approx(
        6 + 3.6 * air_density_ratio(10) + 2.0
    )


def test_a_term_without_any_evidence_keeps_its_prior():
    prior = {"c0": 6.0, "aero": 0.001, "heat": 15.0, "climb": 0.006, "regen": 0.003}
    rows = [
        row(aero=2500 + 300 * (i % 5), heat=(i % 4) / 10, kwh=8 + 0.001 * (2500 + 300 * (i % 5)))
        for i in range(20)
    ]
    coef = fit_coefficients(rows, prior=prior, strength=0.0)  # rows have no climb or regen at all
    assert (coef["climb"], coef["regen"]) == (0.006, 0.003)
    assert fit_coefficients(rows)["climb"] == 0.0  # no prior: nothing to fall back on


def test_descents_never_give_back_more_than_climbs_cost():
    # noisy data that, unconstrained, would credit descents more than climbs cost
    rows = []
    for i in range(30):
        climb, descent = 100.0 * (i % 3), 100.0 * (i % 5)
        aero = 3000 + 200 * (i % 7)
        rows.append(row(aero, 0.1, 6 + 0.001 * aero + 1.5 + 0.002 * climb - 0.006 * descent)
                    | {"climb": climb, "regen": -descent})  # fmt: skip
    coef = fit_coefficients(rows)
    assert coef["regen"] <= coef["climb"]
