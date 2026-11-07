from kiatracker.forecast.scenarios import PRIOR, choose_model, range_grid


def test_range_grid_covers_every_temperature_and_wind(demo):
    model, _ = choose_model(demo)
    grid = range_grid(model, capacity_kwh=81.4, speed_kph=80, temps=[-10, 0, 20], winds=[0, 30])
    assert len(grid) == 6 and set(grid.columns) == {"temp_c", "wind_kph", "range_km"}
    cold_windy = grid.query("temp_c == -10 and wind_kph == 30")["range_km"].item()
    mild_calm = grid.query("temp_c == 20 and wind_kph == 0")["range_km"].item()
    assert cold_windy < mild_calm


def test_trained_model_is_used_when_it_beats_the_baseline(demo):
    model, source = choose_model(demo)
    assert source == "trained" and model is not PRIOR


def test_physics_prior_when_there_is_too_little_data(empty):
    model, source = choose_model(empty)
    assert model is PRIOR and source == "prior"


def test_prior_is_a_plausible_compact_ev():
    assert 12 < PRIOR.predict(80, 15, 80**2) < 20
