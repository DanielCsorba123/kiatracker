from datetime import UTC, datetime, timedelta

import pytest

from kiatracker.gold import derive_charge_windows, derive_charging_sessions, derive_drives
from kiatracker.model import ApiTrip, BatteryReading, DrivingReading, LocationReading, Readings

T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
CAP = 81.4
HOME = (47.5, 19.0)
FAR = (47.6, 19.2)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def bat(minutes, soc, charging=False):
    return BatteryReading(
        at(minutes),
        soc,
        "connected" if charging else "disconnected",
        "charging" if charging else "notCharging",
        charging,
        CAP,
        100,
        100,
        0,
    )


def drv(minutes, odo, ignition_on):
    return DrivingReading(at(minutes), ignition_on, "off", odo, not ignition_on)


def loc(minutes, point):
    return LocationReading(at(minutes), point[0], point[1], 0.0, 0.0)


def drives_of(readings: Readings):
    return derive_drives(readings, CAP, HOME, 0.3)


def simple_drive() -> Readings:
    return Readings(
        battery=[bat(0, 80.0), bat(5, 79.5), bat(10, 78.5), bat(15, 77.5)],
        driving=[drv(0, 1000.0, False), drv(5, 1003.0, True), drv(10, 1008.0, True), drv(15, 1012.0, False)],
        location=[loc(0, HOME), loc(5, (47.52, 19.05)), loc(10, (47.56, 19.12)), loc(15, FAR)],
    )


def test_drive_from_five_minute_readings():
    [d] = drives_of(simple_drive())
    assert (d.start_ts, d.end_ts) == (at(5), at(15))
    assert (d.odo_start, d.odo_end, d.distance_km) == (1000.0, 1012.0, 12.0)
    assert (d.soc_start, d.soc_end) == (80.0, 77.5)
    assert d.energy_kwh == pytest.approx(2.035)
    assert d.kwh_per_100km == pytest.approx(16.96, abs=0.01)
    assert (d.start_zone, d.end_zone) == ("home", "other")
    assert d.location_points == 3
    assert d.mid_ts == at(10) and (d.mid_lat, d.mid_lon) == (47.56, 19.12)
    assert d.in_progress is False


def test_short_drive_between_two_parked_readings_is_counted():
    r = Readings(battery=[bat(0, 80.0), bat(5, 79.0)], driving=[drv(0, 1000.0, False), drv(5, 1003.0, False)])
    [d] = drives_of(r)
    assert (d.start_ts, d.end_ts, d.distance_km) == (at(0), at(5), 3.0)


def test_short_drive_has_no_consumption():
    [d] = drives_of(
        Readings(battery=[bat(0, 80.0), bat(5, 79.0)], driving=[drv(0, 1000.0, False), drv(5, 1003.0, False)])
    )
    assert d.energy_kwh == pytest.approx(0.814)
    assert d.kwh_per_100km is None


def test_drive_still_running_is_in_progress():
    r = Readings(driving=[drv(0, 1000.0, False), drv(5, 1003.0, True), drv(10, 1009.0, True)])
    [d] = drives_of(r)
    assert d.in_progress is True
    assert (d.end_ts, d.distance_km) == (at(10), 9.0)


def test_api_trip_refines_start_and_end():
    r = simple_drive()
    r.api_trips = [ApiTrip(at(2), at(14))]
    [d] = drives_of(r)
    assert (d.start_ts, d.end_ts, d.api_trips) == (at(2), at(14), 1)


def test_missing_odometer_does_not_crash():
    r = Readings(driving=[drv(0, None, False), drv(5, None, True), drv(10, None, False)])
    [d] = drives_of(r)
    assert d.distance_km is None and d.kwh_per_100km is None


def test_parked_car_has_no_drives():
    r = Readings(driving=[drv(0, 1000.0, False), drv(60, 1000.0, False)])
    assert drives_of(r) == []


def charging_readings() -> Readings:
    return Readings(
        battery=[bat(0, 30.0), bat(5, 31.0, True), bat(180, 50.0, True), bat(365, 80.0)],
        location=[loc(0, HOME)],
    )


def test_charging_session():
    [s] = derive_charging_sessions(charging_readings(), CAP, HOME, 0.3)
    assert (s.start_ts, s.end_ts) == (at(5), at(365))
    assert (s.soc_start, s.soc_end) == (30.0, 80.0)
    assert s.energy_kwh == pytest.approx(40.7)
    assert s.hours == pytest.approx(6.0)
    assert s.avg_kw == pytest.approx(6.783, abs=0.001)
    assert s.zone == "home" and s.in_progress is False


def test_charging_session_in_progress():
    r = Readings(battery=[bat(0, 30.0), bat(5, 31.0, True), bat(60, 40.0, True)])
    [s] = derive_charging_sessions(r, CAP, None, 0.3)
    assert s.in_progress is True and s.soc_end == 40.0 and s.zone is None


def test_charge_window_totals():
    r = Readings(
        battery=[
            bat(0, 50.0),
            bat(5, 51.0, True),
            bat(60, 90.0),
            bat(600, 70.0),
            bat(605, 71.0, True),
            bat(700, 95.0),
        ],
        driving=[
            drv(100, 2000.0, False),
            drv(105, 2004.0, True),
            drv(110, 2010.0, False),
            drv(300, 2010.0, False),
            drv(305, 2020.0, True),
            drv(310, 2030.0, False),
        ],
    )
    sessions = derive_charging_sessions(r, CAP, None, 0.3)
    [w] = derive_charge_windows(sessions, drives_of(r), CAP)
    assert (w.start_ts, w.end_ts) == (at(60), at(605))
    assert w.soc_used == 20.0
    assert w.energy_kwh == pytest.approx(16.28)
    assert (w.distance_km, w.drives) == (30.0, 2)
    assert w.kwh_per_100km == pytest.approx(54.27, abs=0.01)


def test_window_ignores_drive_in_progress():
    r = Readings(
        battery=[
            bat(0, 50.0),
            bat(5, 51.0, True),
            bat(60, 90.0),
            bat(600, 70.0),
            bat(605, 71.0, True),
            bat(700, 95.0),
        ],
        driving=[drv(100, 2000.0, False), drv(105, 2004.0, True)],
    )
    [w] = derive_charge_windows(derive_charging_sessions(r, CAP, None, 0.3), drives_of(r), CAP)
    assert w.drives == 0 and w.distance_km == 0 and w.kwh_per_100km is None


def test_drive_starting_before_unplug_reading_counts_in_window():
    # charging ends; the first non-charging reading is the ignition-on poll at 65, but the API trip says
    # the drive began at 62, before that reading
    r = Readings(
        battery=[
            bat(0, 50.0),
            bat(5, 51.0, True),
            bat(65, 90.0),
            bat(75, 87.0),
            bat(600, 80.0),
            bat(605, 81.0, True),
            bat(700, 95.0),
        ],
        driving=[drv(0, 2000.0, False), drv(65, 2004.0, True), drv(75, 2020.0, False)],
        api_trips=[ApiTrip(at(62), at(74))],
    )
    [w] = derive_charge_windows(derive_charging_sessions(r, CAP, None, 0.3), drives_of(r), CAP)
    assert (w.drives, w.distance_km) == (1, 20.0)


def test_trips_merged_by_polling_are_split_by_api_trips():
    """Two trips with a short stop in between that the 5-minute polling never saw as 'ignition off'."""
    r = Readings(
        battery=[
            bat(0, 80.0),
            bat(5, 79.5),
            bat(10, 78.5),
            bat(15, 78.5),
            bat(20, 77.5),
            bat(25, 76.5),
            bat(30, 76.0),
        ],
        driving=[
            drv(0, 1000.0, False),
            drv(5, 1003.0, True),
            drv(10, 1008.0, True),
            drv(15, 1008.0, True),
            drv(20, 1012.0, True),
            drv(25, 1016.0, True),
            drv(30, 1018.0, False),
        ],
        api_trips=[ApiTrip(at(2), at(9)), ApiTrip(at(17), at(29))],
    )
    first, second = drives_of(r)
    assert (first.start_ts, first.end_ts, first.distance_km) == (at(2), at(9), 8.0)
    assert (first.soc_start, first.soc_end) == (80.0, 78.5)
    assert (second.start_ts, second.end_ts, second.distance_km) == (at(17), at(29), 10.0)
    assert (second.soc_start, second.soc_end) == (78.5, 76.0)
    assert not first.in_progress and not second.in_progress
    assert (first.drive_id, second.drive_id) == (1, 2)


def test_split_keeps_the_last_part_in_progress_while_driving():
    r = Readings(
        driving=[
            drv(0, 1000.0, False),
            drv(5, 1003.0, True),
            drv(10, 1008.0, True),
            drv(15, 1008.0, True),
            drv(20, 1012.0, True),
        ],
        api_trips=[ApiTrip(at(2), at(9)), ApiTrip(at(17), at(19))],
    )
    first, second = drives_of(r)
    assert not first.in_progress and second.in_progress


def test_drive_hidden_in_a_collection_gap_keeps_its_distance_but_not_its_energy():
    """The Krems day: collector off overnight, unseen charge, then 358 km; only the two ends exist."""
    r = Readings(
        battery=[bat(0, 59.5), bat(19 * 60, 19.5)],
        driving=[drv(0, 76784.2, False), drv(19 * 60, 77142.1, False)],
    )
    [d] = drives_of(r)
    assert d.distance_km == pytest.approx(357.9)
    assert d.quality == "gap"
    assert d.energy_kwh is None and d.kwh_per_100km is None


def test_impossible_consumption_is_flagged():
    # 20 km on 1 % of an 81.4 kWh battery would be 4 kWh/100 km: not a real measurement
    r = Readings(
        battery=[bat(0, 80.0), bat(5, 80.0), bat(25, 79.0)],
        driving=[drv(0, 1000.0, False), drv(5, 1010.0, True), drv(25, 1020.0, False)],
    )
    [d] = drives_of(r)
    assert d.quality == "implausible" and d.kwh_per_100km is None


def test_charge_rising_during_a_drive_is_flagged():
    r = Readings(
        battery=[bat(0, 50.0), bat(5, 49.0), bat(30, 70.0)],
        driving=[drv(0, 1000.0, False), drv(5, 1004.0, True), drv(30, 1020.0, False)],
    )
    [d] = drives_of(r)
    assert d.quality == "implausible" and d.energy_kwh is None


def test_normal_drive_is_ok():
    [d] = drives_of(simple_drive())
    assert d.quality == "ok"
