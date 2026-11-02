import json
from datetime import UTC, datetime, timedelta

import httpx

from kiatracker.collect import STATE_FILE, poll
from kiatracker.pleos import SNAPSHOT_PATHS, TRIPS_PATH, RateLimited
from kiatracker.raw import read_records

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
LAT, LON = "47.123456", "19.654321"


def snapshot(group: str, ts: str) -> dict:
    data = {
        "batteries": {
            "charge": {"stateOfCharge": 70.0, "status": "notCharging", "batteryCapacity": 293040.0}
        },
        "powertrains": {"distanceToEmpties": [{"type": "EV", "value": "400", "unit": "km"}]},
        "locations": {"location": {"latitude": LAT, "longitude": LON}},
        "driving": {"ignition": {"status": "off"}, "odometer": {"value": 76000.0, "unit": "km"}},
        "status": {"climateControl": {"status": "off"}},
    }[group]
    return {"data": {**data, "timestamp": ts}}


class FakeClient:
    def __init__(self, timestamps=None, failing=(), rate_limited=False):
        self.timestamps = timestamps or {}
        self.failing = set(failing)
        self.rate_limited = rate_limited
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        if self.rate_limited:
            raise RateLimited("rate limited", 429)
        if path == TRIPS_PATH.format(vin="VIN1"):
            return 200, {
                "data": {"trips": [{"triggerStartTime": "t", "tripLength": 1, "isla": {"x": ["a"] * 3}}]}
            }
        group = next(g for g, p in SNAPSHOT_PATHS.items() if p.format(vin="VIN1") == path)
        if group in self.failing:
            return 500, {"error": {"code": "50001"}}
        return 200, snapshot(group, self.timestamps.get(group, "2026-11-02T11:00:00Z"))


def records(raw_dir, kind):
    return list(read_records(raw_dir, kind))


def test_first_poll_stores_every_group_and_trips(tmp_path):
    result = poll(FakeClient(), "VIN1", tmp_path, now=NOW)
    assert sorted(r["endpoint"] for r in records(tmp_path, "snapshots")) == sorted(SNAPSHOT_PATHS)
    trips = records(tmp_path, "trips")
    assert len(trips) == 1 and trips[0]["isla_compacted"] is True
    assert trips[0]["body"]["data"]["trips"][0]["isla"] == {"x": {"len": 3, "distinct": ["a"]}}
    assert "trips" in result.new


def test_unchanged_readings_are_not_stored_again(tmp_path):
    poll(FakeClient(), "VIN1", tmp_path, now=NOW)
    result = poll(FakeClient(), "VIN1", tmp_path, now=NOW + timedelta(minutes=5))
    assert len(records(tmp_path, "snapshots")) == 5
    assert len(records(tmp_path, "trips")) == 1  # next trip sync only after 6 h
    assert result.new == []


def test_only_changed_group_is_stored(tmp_path):
    poll(FakeClient(), "VIN1", tmp_path, now=NOW)
    poll(FakeClient({"batteries": "2026-11-02T11:05:00Z"}), "VIN1", tmp_path, now=NOW + timedelta(minutes=5))
    assert [r["endpoint"] for r in records(tmp_path, "snapshots")][5:] == ["batteries"]


def test_trips_resync_after_six_hours(tmp_path):
    poll(FakeClient(), "VIN1", tmp_path, now=NOW)
    poll(FakeClient(), "VIN1", tmp_path, now=NOW + timedelta(hours=6, minutes=1))
    assert len(records(tmp_path, "trips")) == 2


def test_failing_group_is_logged_and_others_stored(tmp_path):
    result = poll(FakeClient(failing={"locations"}), "VIN1", tmp_path, now=NOW)
    assert len(records(tmp_path, "snapshots")) == 4
    errors = records(tmp_path, "errors")
    assert errors[0]["endpoint"] == "locations" and errors[0]["http_status"] == 500
    assert result.errors == ["locations"]


def test_rate_limit_stops_poll_without_raising(tmp_path):
    result = poll(FakeClient(rate_limited=True), "VIN1", tmp_path, now=NOW)
    assert result.errors == ["rate limited"]
    assert records(tmp_path, "errors")[0]["http_status"] == 429


def test_spike_state_file_is_honoured(tmp_path):
    state = {
        "last_timestamp": {g: "2026-11-02T11:00:00Z" for g in SNAPSHOT_PATHS},
        "last_position": None,
        "last_trip_sync": NOW.isoformat(),
    }
    (tmp_path / STATE_FILE).write_text(json.dumps(state))
    poll(FakeClient(), "VIN1", tmp_path, now=NOW + timedelta(minutes=5))
    assert records(tmp_path, "snapshots") == []


def test_summary_never_contains_coordinates(tmp_path):
    poll(FakeClient(), "VIN1", tmp_path, now=NOW)
    moved = FakeClient({"locations": "2026-11-02T11:05:00Z"})
    result = poll(moved, "VIN1", tmp_path, now=NOW + timedelta(minutes=5))
    assert "SOC 70.0%" in result.summary
    assert LAT not in result.summary and "47.12" not in result.summary


class FlakyClient(FakeClient):
    def get(self, path, params=None):
        if path.endswith("/batteries"):
            raise httpx.ConnectError("network unreachable")
        return super().get(path, params)


def test_network_error_on_one_group_is_logged_and_poll_continues(tmp_path):
    result = poll(FlakyClient(), "VIN1", tmp_path, now=NOW)
    assert len(records(tmp_path, "snapshots")) == 4
    error = records(tmp_path, "errors")[0]
    assert error["endpoint"] == "batteries" and error["exception"] == "ConnectError"
    assert result.errors == ["batteries"]
    assert (tmp_path / STATE_FILE).exists()
