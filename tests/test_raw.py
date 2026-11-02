from datetime import UTC, datetime

from kiatracker.raw import append_record, compact_isla, read_records

NOV = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
DEC = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)


def test_append_uses_monthly_file(tmp_path):
    path = append_record(tmp_path, "snapshots", {"a": 1}, now=NOV)
    assert path.name == "snapshots-2026-11.jsonl"


def test_round_trip_across_months_in_order(tmp_path):
    append_record(tmp_path, "snapshots", {"n": 2}, now=DEC)
    append_record(tmp_path, "snapshots", {"n": 1}, now=NOV)
    append_record(tmp_path, "trips", {"n": 9}, now=NOV)
    assert [r["n"] for r in read_records(tmp_path, "snapshots")] == [1, 2]


def test_corrupt_last_line_is_skipped(tmp_path):
    path = append_record(tmp_path, "snapshots", {"n": 1}, now=NOV)
    with path.open("a", encoding="utf-8") as f:
        f.write('{"n": 2, "body": {"da')  # power cut mid-write
    assert [r["n"] for r in read_records(tmp_path, "snapshots")] == [1]


def test_read_missing_dir_yields_nothing(tmp_path):
    assert list(read_records(tmp_path / "nope", "snapshots")) == []


def test_compact_isla_keeps_shape_not_repeats():
    payload = {
        "data": {
            "trips": [
                {"triggerStartTime": "t", "tripLength": 5, "isla": {"optionUsm": ["warning"] * 4 + [None]}}
            ]
        }
    }
    trip = compact_isla(payload)["data"]["trips"][0]
    assert trip["isla"] == {"optionUsm": {"len": 5, "distinct": ["None", "warning"]}}
    assert trip["tripLength"] == 5


def test_compact_isla_ignores_error_payload():
    assert compact_isla({"error": {"code": "4045"}}) == {"error": {"code": "4045"}}


def test_record_after_truncated_line_is_kept(tmp_path):
    path = append_record(tmp_path, "snapshots", {"n": 1}, now=NOV)
    with path.open("a", encoding="utf-8") as f:
        f.write('{"n": 2, "bo')  # power cut mid-write
    append_record(tmp_path, "snapshots", {"n": 3}, now=NOV)
    assert [r["n"] for r in read_records(tmp_path, "snapshots")] == [1, 3]


def test_append_records_batches_by_month(tmp_path):
    from kiatracker.raw import append_records

    append_records(tmp_path, "weather", [(NOV, {"n": 1}), (DEC, {"n": 2}), (NOV, {"n": 3})])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["weather-2026-11.jsonl", "weather-2026-12.jsonl"]
    assert [r["n"] for r in read_records(tmp_path, "weather")] == [1, 3, 2]
