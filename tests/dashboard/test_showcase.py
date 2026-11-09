from datetime import date

from kiatracker.showcase import expected_switch, load_status, real_data_status, write_status


def test_switch_waits_for_enough_drives_at_the_current_pace():
    # 20 drives in 10 days: 40 more take 20 days; plenty of cold drives already
    assert expected_switch(date(2027, 1, 10), 20, 12, date(2026, 12, 31)) == date(2027, 1, 30)


def test_switch_waits_for_winter_when_cold_drives_are_missing():
    # targets reached in November except the cold drives: December, plus about a month
    assert expected_switch(date(2026, 11, 9), 70, 0, date(2026, 9, 1)) == date(2027, 1, 1)


def test_status_holds_only_aggregates(demo):
    status = real_data_status(demo, date.today())
    assert set(status) == {
        "collecting_since", "updated", "trustworthy_drives", "km", "cold_drives", "target_drives",
        "target_cold_drives", "expected_real_data",
    }  # fmt: skip
    assert status["trustworthy_drives"] > 0 and status["km"] > 0


def test_status_round_trip(tmp_path):
    path = tmp_path / "status.json"
    write_status({"trustworthy_drives": 3}, path)
    assert load_status(path) == {"trustworthy_drives": 3}
    assert load_status(tmp_path / "missing.json") is None
