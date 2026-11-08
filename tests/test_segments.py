from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from kiatracker.gold import Drive
from kiatracker.model import LocationReading
from kiatracker.segments import drive_segments

T0 = datetime(2026, 11, 7, 5, 0, tzinfo=UTC)


def drive(**changes) -> Drive:
    base = Drive(
        1,
        T0,
        T0 + timedelta(minutes=20),
        0,
        22.2,
        22.2,
        90,
        86,
        3.3,
        15,
        47.0,
        18.0,
        47.2,
        18.0,
        T0 + timedelta(minutes=10),
        47.1,
        18.0,
        "home",
        "other",
        0,
        1,
        False,
    )
    return replace(base, **changes)


def hourly(day, temps, wind=20.0, wind_from=0.0):
    return {
        "hourly": {
            "time": [f"{day}T{h:02d}:00" for h in range(24)],
            "temperature_2m": temps,
            "wind_speed_10m": [wind] * 24,
            "wind_direction_10m": [wind_from] * 24,
        }
    }


class FlatThenHill:
    def elevation(self, lat, lon):
        return 200.0 if lat < 47.15 else 450.0


def test_each_stretch_gets_its_own_hour_place_and_headwind():
    inner = [LocationReading(T0 + timedelta(minutes=10), 47.1, 18.0, 0.0, 66.0)]
    temps = [float(h) for h in range(24)]  # 1 °C per hour, so the hour shows in the result
    weather = {
        (47.0, 18.0, "2026-11-07"): hourly("2026-11-07", temps),
        (47.1, 18.0, "2026-11-07"): hourly("2026-11-07", [t + 10 for t in temps]),
    }
    first, second = drive_segments(drive(end_lat=47.18), inner, weather, FlatThenHill())
    assert first.km == pytest.approx(11.12, abs=0.05) and second.km == pytest.approx(8.9, abs=0.05)
    assert first.speed_kph == pytest.approx(66.7, abs=0.5)
    assert first.temp_c == 5.0  # 05:05 UTC -> 05:00, cell 47.0
    assert second.temp_c == 15.0  # 05:15 UTC -> 05:00, cell 47.1 (+10)
    assert first.headwind_kph == pytest.approx(20)  # driving north into a north wind
    assert (first.climb_m, first.descent_m) == (0, 0)
    assert (second.climb_m, second.descent_m) == (250, 0)


def test_no_segments_for_unusable_drives():
    assert drive_segments(drive(quality="gap"), [], {}, None) == []
    assert drive_segments(drive(in_progress=True), [], {}, None) == []
    assert drive_segments(drive(start_lat=None), [], {}, None) == []


def test_stretches_without_weather_or_terrain_still_count_distance():
    [only] = drive_segments(drive(), [], {}, None)
    assert only.km == pytest.approx(22.2, abs=0.1)
    assert only.temp_c is None and only.headwind_kph is None and only.climb_m is None


def test_readings_seconds_apart_use_the_drive_speed_not_an_absurd_one():
    inner = [LocationReading(T0 + timedelta(minutes=10, seconds=-0.1), 47.1, 18.0, 0.0, 66.0),
             LocationReading(T0 + timedelta(minutes=10), 47.11, 18.0, 0.0, 66.0)]  # fmt: skip
    speeds = [s.speed_kph for s in drive_segments(drive(), inner, {}, None)]
    assert max(speeds) < 100  # 1 km in 0.1 s would be 36,000 km/h
