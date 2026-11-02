from kiatracker.forecast.features import COLUMNS, drive_features


def test_feature_rows_have_exactly_the_documented_columns(demo):
    rows = drive_features(demo)
    assert len(rows) > 100
    assert all(set(r) == set(COLUMNS) for r in rows)


def test_no_coordinates_leave_the_feature_layer(demo):
    for key in drive_features(demo)[0]:
        assert "lat" not in key and "lon" not in key and key != "vin"


def test_only_finished_measured_drives(demo):
    rows = drive_features(demo)
    assert all(r["distance_km"] >= 5 and r["kwh_per_100km"] is not None for r in rows)
    in_progress = demo.execute("select count(*) from drives where in_progress").fetchone()[0]
    measured = demo.execute(
        "select count(*) from drives d join drive_weather w using (drive_id) "
        "where not in_progress and kwh_per_100km is not null"
    ).fetchone()[0]
    assert len(rows) == measured and in_progress <= 1


def test_derived_physics_features(demo):
    r = drive_features(demo)[0]
    assert r["aero"] >= (r["speed_kph"] + r["headwind_kph"]) ** 2 - 1e-6  # mean of squares >= square of mean
    assert r["heat"] == max(0.0, 18 - r["temp_c"]) / r["speed_kph"]
    assert abs(r["headwind_kph"]) <= r["wind_kph"] + 1e-9


def test_headwinds_vary_in_sign(demo):
    winds = [r["headwind_kph"] for r in drive_features(demo)]
    assert min(winds) < -3 and max(winds) > 3
