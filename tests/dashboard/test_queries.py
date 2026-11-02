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
    yield q.costs(con, period, 60, 600, 6, 10)


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
    assert (sessions["zone"] == "home").all() and (sessions["soc_end"] > sessions["soc_start"]).all()
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
    with tiny() as con:
        costs = q.costs(con, Period(date(2026, 11, 1), date(2026, 11, 30)), 50, 600, 6, 10)
    row = costs.iloc[0]
    assert row["month"] == "2026-11"
    assert row["distance_km"] == 100
    assert row["electricity_cost"] == pytest.approx(20 / 0.9 * 50)
    assert row["petrol_cost"] == pytest.approx(100 * 6 / 100 * 600)
    assert row["savings"] == pytest.approx(row["petrol_cost"] - row["electricity_cost"])


def test_middle_bands_show_both_edges(demo, all_time):
    bands = q.consumption_by_band(demo, all_time, "temp_c", [-30, 0, 10, 45])
    assert list(bands["band"]) == ["under 0", "0 to 10", "10+"]


def test_unfinished_drive_is_not_shown_or_counted(tiny):
    november = Period(date(2026, 11, 1), date(2026, 11, 30))
    with tiny(unfinished=True) as con:
        assert len(q.drives(con, november)) == 2
        assert q.kpis(con, november)["drives"] == 2 and q.kpis(con, november)["distance_km"] == 100
