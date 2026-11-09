from datetime import date

import pytest

from kiatracker.dashboard import queries as q
from kiatracker.dashboard.queries import Period

FORBIDDEN = {"lat", "lon", "latitude", "longitude", "vin"}


def frames(con, period):
    yield q.weekly(con, period)
    yield q.drives(con, period)
    yield q.consumption_by_band(con, period, "temp_c", [-20, 0, 10, 40])
    yield q.charging_sessions(con, period)
    yield q.weekly_charging(con, period)
    yield q.costs(con, period, q.CostAssumptions())


def test_no_query_returns_coordinates_or_vin(demo, all_time):
    for frame in frames(demo, all_time):
        for column in frame.columns:
            assert column not in FORBIDDEN and not column.endswith(("_lat", "_lon")), column


def test_kpis_on_demo(demo, all_time):
    k = q.kpis(demo, all_time)
    assert k["drives"] > 30 and k["distance_km"] > 300
    assert 10 < k["kwh_per_100km"] < 30
    assert k["energy_charged_kwh"] > 0
    assert 0 < k["latest_soc"] <= 100 and k["latest_range_km"] > 0


def test_weekly_adds_up_to_total(demo, all_time):
    weekly = q.weekly(demo, all_time)
    assert weekly["distance_km"].sum() == pytest.approx(q.kpis(demo, all_time)["distance_km"])
    assert list(weekly.columns) == ["week", "distance_km", "kwh_per_100km"]


def test_drives_table_is_local_time_with_weather(demo, all_time):
    d = q.drives(demo, all_time)
    assert d["start_local"].dt.tz is None  # local wall-clock time, ready to display
    assert d["temp_c"].notna().mean() > 0.9
    assert d["start_local"].is_monotonic_decreasing


def test_cold_costs_more_in_demo(demo, all_time):
    bands = q.consumption_by_band(demo, all_time, "temp_c", [-20, 5, 40])
    assert list(bands["band"]) == ["under 5", "5+"]
    assert bands["kwh_per_100km"].iloc[0] > bands["kwh_per_100km"].iloc[1]


def test_charging_tables(demo, all_time):
    sessions = q.charging_sessions(demo, all_time)
    assert (sessions["soc_end"] > sessions["soc_start"]).all()
    assert set(sessions["zone"]) <= {"home", "other"} and (sessions["zone"] == "home").mean() > 0.6
    assert q.weekly_charging(demo, all_time)["energy_kwh"].sum() == pytest.approx(
        q.kpis(demo, all_time)["energy_charged_kwh"]
    )


def test_period_filters_by_local_date(demo):
    future = Period(date(2099, 1, 1), date(2099, 1, 31))
    assert q.kpis(demo, future)["drives"] == 0
    assert q.drives(demo, future).empty


def test_empty_database(empty, all_time):
    k = q.kpis(empty, all_time)
    assert k == {
        "distance_km": 0,
        "drives": 0,
        "kwh_per_100km": None,
        "energy_charged_kwh": 0,
        "latest_soc": None,
        "latest_range_km": None,
    }
    for frame in frames(empty, all_time):
        assert frame.empty


def test_only_short_drives_have_no_consumption(tiny):
    with tiny(consumption=None) as con:
        assert q.kpis(con, Period(date(2026, 11, 1), date(2026, 11, 30)))["kwh_per_100km"] is None


def test_costs_arithmetic(tiny):
    assume = q.CostAssumptions(
        petrol_l_per_100km=6.5,
        diesel_l_per_100km=5.0,
        charging_loss_pct=10,
        hu_electricity_huf=70.0,
        at_electricity_eur=0.30,
    )
    with tiny() as con:
        [row] = q.costs(con, Period(date(2026, 11, 1), date(2026, 11, 30)), assume).to_dict("records")
    grid_kwh = 15 / 0.9  # 15 kWh into the battery over 100 km, 10 % lost on the way
    assert row["month"] == "2026-11" and row["distance_km"] == 100
    assert row["ev_huf"] == pytest.approx(grid_kwh * 70.0)
    assert row["petrol_huf"] == pytest.approx(6.5 * 640)  # November's average Hungarian petrol price
    assert row["diesel_huf"] == pytest.approx(5.0 * 700)
    assert row["ev_at_eur"] == pytest.approx(grid_kwh * 0.30)
    assert row["petrol_at_eur"] == pytest.approx(6.5 * 1.8)


def test_month_without_its_own_fuel_week_uses_the_latest_earlier_one(tiny):
    with tiny() as con:
        con_period = Period(date(2026, 11, 1), date(2026, 11, 30))
        prices = q.fuel_price_for_month(con, "2026-12")
    assert prices["hu_petrol_huf"] == 640 and con_period


def test_no_fuel_prices_yet_gives_no_costs(empty, all_time):
    assert q.costs(empty, all_time, q.CostAssumptions()).empty


def middle_edges(demo, all_time) -> tuple[int, int]:
    """Two whole-degree edges with drives on every side, whatever season the demo's dates fall in."""
    temps = q.drives(demo, all_time)["temp_c"].dropna()
    return round(temps.quantile(0.3)), round(temps.quantile(0.7))


def test_middle_bands_show_both_edges(demo, all_time):
    a, b = middle_edges(demo, all_time)
    bands = q.consumption_by_band(demo, all_time, "temp_c", [-30, a, b, 45])
    assert list(bands["band"]) == [f"under {a}", f"{a} to {b}", f"{b}+"]


def test_unfinished_drive_is_not_shown_or_counted(tiny):
    november = Period(date(2026, 11, 1), date(2026, 11, 30))
    with tiny(unfinished=True) as con:
        assert len(q.drives(con, november)) == 2
        assert q.kpis(con, november)["drives"] == 2 and q.kpis(con, november)["distance_km"] == 100


def test_drives_have_average_speed(demo, all_time):
    d = q.drives(demo, all_time)
    assert (d["speed_kph"] - d["distance_km"] / d["minutes"] * 60).abs().max() < 1e-9


def test_bands_carry_numeric_edges_for_drawing(demo, all_time):
    a, b = middle_edges(demo, all_time)
    bands = q.consumption_by_band(demo, all_time, "temp_c", [-30, a, b, 45])
    assert list(bands["lo"]) == [-30, a, b] and list(bands["hi"]) == [a, b, 45]


def test_condition_effects_compare_harder_and_easier_drives(demo, all_time):
    effects = q.condition_effects(demo, all_time).set_index("factor")
    cold = effects.loc["Cold"]
    assert cold["harder_label"] == "below 5 °C" and cold["easier_label"] == "10 °C or warmer"
    assert cold["enough"] and cold["n_harder"] >= 3 and cold["n_easier"] >= 3
    assert cold["diff_kwh"] == pytest.approx(cold["harder_kwh"] - cold["easier_kwh"])
    assert cold["diff_kwh"] > 0  # the simulator's car does use more in the cold
    assert set(effects.index) == {"Cold", "Wind", "Motorway speed", "Short trips"}


def test_condition_effects_say_when_there_is_not_enough_data(tiny):
    with tiny() as con:
        effects = q.condition_effects(con, Period(date(2026, 11, 1), date(2026, 11, 30)))
    assert not effects["enough"].any()


def test_usual_level_is_median_of_slow_sessions_rounded(sessions_db):
    con = sessions_db(ends=[79, 80, 81, 80, 78, 100], kw=[7.4] * 6)
    u = q.usual_charge_level(con, latest_soc=40)
    assert (u.level, u.assumed, u.sessions) == (80, False, 6) and u.at_level == 5


def test_dc_sessions_are_ignored_and_few_sessions_fall_back(sessions_db):
    con = sessions_db(ends=[100, 100, 90, 80], kw=[96, 88, 7.4, 7.4])
    u = q.usual_charge_level(con, latest_soc=40)
    assert (u.level, u.assumed) == (80, True)


def test_usual_level_never_below_latest_reading(sessions_db):
    con = sessions_db(ends=[80] * 6, kw=[7.4] * 6)
    assert q.usual_charge_level(con, latest_soc=95).level == 95


def test_usual_level_on_an_empty_database(empty):
    u = q.usual_charge_level(empty, latest_soc=None)
    assert (u.level, u.assumed, u.sessions) == (80, True, 0)


def test_monthly_consumption(demo, all_time):
    m = q.monthly(demo, all_time)
    assert list(m.columns) == ["month", "distance_km", "kwh_per_100km"] and len(m) >= 2
    assert m["kwh_per_100km"].between(10, 35).all()


def test_commute_pair_is_the_most_frequent_trip(tiny):
    pair = q.commute_pair(tiny(), Period(date(2026, 11, 1), date(2026, 11, 30)))
    assert pair == ("home", "other", 50.0)


def test_commute_pair_none_without_drives(empty, all_time):
    assert q.commute_pair(empty, all_time) is None


def test_tips_skip_conditions_that_do_not_hold(demo, all_time):
    warm = [dict(temp_min=12)] * 3
    tips = q.tips_facts(demo, all_time, warm, date.today())
    assert all("pre-heat" not in text for _, _, text in tips)
    assert any("at home" in text for _, _, text in tips)


def test_tips_cold_forecast_suggests_preheating(demo, all_time):
    cold = [dict(temp_min=-2)] + [dict(temp_min=8)] * 2
    assert any("pre-heat" in text for _, _, text in q.tips_facts(demo, all_time, cold, date.today()))


def test_tips_on_an_empty_database(empty, all_time):
    assert q.tips_facts(empty, all_time, [], date.today()) == []
