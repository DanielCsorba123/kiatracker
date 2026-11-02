from datetime import datetime

import pytest

from kiatracker.forecast.features import drive_features
from kiatracker.forecast.model import MIN_DRIVES, NotEnoughData, RangeModel, fit
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
    # consumption falls as "heat" rises: physically impossible, so heat must get no cost
    rows = [row(aero=2500 + 100 * i, heat=i / 10, kwh=15 + 0.001 * 100 * i - 0.5 * i) for i in range(20)]
    model = fit(rows)
    assert model.coef["heat"] == 0 and model.coef["aero"] >= 0


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
