import duckdb

from kiatracker.dashboard.source import build_demo_database, resolve_source


def test_demo_env_wins_over_existing_personal_database(tmp_path):
    personal = tmp_path / "kiatracker.duckdb"
    personal.write_bytes(b"real data")
    source = resolve_source(personal, demo_requested=False, environ={"KIATRACKER_DEMO": "1"})
    assert source.demo is True
    assert source.db_path != personal


def test_personal_database_is_default(tmp_path):
    personal = tmp_path / "kiatracker.duckdb"
    source = resolve_source(personal, demo_requested=False, environ={})
    assert source == source.__class__(personal, demo=False)


def test_demo_requested_uses_demo(tmp_path):
    assert resolve_source(tmp_path / "x.duckdb", demo_requested=True, environ={}).demo is True


def test_demo_database_has_drives_and_no_real_home(tmp_path):
    db = build_demo_database(tmp_path, days=10)
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute("select count(*) from drives").fetchone()[0] > 5
        assert con.execute("select count(*) from drives where start_zone = 'home'").fetchone()[0] > 0
