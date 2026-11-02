from datetime import UTC, datetime, timedelta

import pytest

from kiatracker.model import ApiTrip
from kiatracker.silver import load_readings, merge_trip_fragments
from rawfactory import battery, driving, location, range_km, status, trips_record, write

T0 = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)


def test_parses_every_group(tmp_path):
    write(
        tmp_path,
        "snapshots",
        [
            battery(T0, 77.0),
            driving(T0, 76088.5),
            location(T0, "47.1", "19.2", speed=12.0),
            status(T0, climate_on=True, seat_heat=True),
            range_km(T0, "433"),
        ],
    )
    r = load_readings(tmp_path)
    b = r.battery[0]
    assert (b.ts, b.soc, b.charging, b.plugin) == (T0, 77.0, False, "disconnected")
    assert b.capacity_kwh == pytest.approx(81.4)
    assert (b.target_soc_ac, b.target_soc_dc) == (100, 90)
    assert (r.driving[0].odometer_km, r.driving[0].ignition_on, r.driving[0].parked) == (76088.5, False, True)
    assert (r.location[0].lat, r.location[0].lon, r.location[0].speed_kph) == (47.1, 19.2, 12.0)
    assert (r.status[0].climate_on, r.status[0].seat_heat_any) == (True, True)
    assert r.range[0].range_km == 433


def test_same_reading_in_two_files_counts_once(tmp_path):
    write(tmp_path, "snapshots", [battery(T0, 70.0)], now=T0)
    write(tmp_path, "snapshots", [battery(T0, 70.0)], now=T0 + timedelta(days=40))  # next month's file
    write(tmp_path, "snapshots", [battery(T0 + timedelta(minutes=5), 69.5)], now=T0)
    assert [b.soc for b in load_readings(tmp_path).battery] == [70.0, 69.5]


def test_readings_sorted_by_car_time(tmp_path):
    write(tmp_path, "snapshots", [battery(T0 + timedelta(minutes=5), 69.5), battery(T0, 70.0)], now=T0)
    assert [b.soc for b in load_readings(tmp_path).battery] == [70.0, 69.5]


def test_invalid_values_become_none(tmp_path):
    write(tmp_path, "snapshots", [range_km(T0, "-"), driving(T0, None)])
    r = load_readings(tmp_path)
    assert r.range[0].range_km is None
    assert r.driving[0].odometer_km is None


def test_error_records_are_ignored(tmp_path):
    write(tmp_path, "snapshots", [battery(T0, 50.0) | {"http_status": 500}])
    assert load_readings(tmp_path).battery == []


def test_api_trips_deduplicated_and_merged(tmp_path):
    start = T0
    write(
        tmp_path,
        "trips",
        [
            trips_record(T0, [(start, 10), (start + timedelta(minutes=10, seconds=2), 5)]),
            trips_record(
                T0 + timedelta(hours=6), [(start, 10), (start + timedelta(minutes=10, seconds=2), 5)]
            ),
        ],
    )
    trips = load_readings(tmp_path).api_trips
    assert trips == [ApiTrip(start, start + timedelta(minutes=15, seconds=2))]


def test_fragments_further_apart_than_60s_stay_separate():
    a = ApiTrip(T0, T0 + timedelta(minutes=10))
    b = ApiTrip(T0 + timedelta(minutes=11, seconds=1), T0 + timedelta(minutes=20))
    assert merge_trip_fragments([a, b]) == [a, b]
