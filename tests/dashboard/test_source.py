import duckdb
import pytest

from kiatracker.dashboard.source import build_demo_database, is_local_only, resolve_source


@pytest.fixture
def personal(tmp_path):
    path = tmp_path / "kiatracker.duckdb"
    path.write_bytes(b"real data")
    return path


def test_demo_is_the_default_without_explicit_opt_in(personal):
    """Fail closed: `streamlit run app.py` on any machine shows demo data."""
    assert resolve_source(personal, environ={}).demo is True


def test_personal_mode_needs_explicit_opt_in(personal):
    source = resolve_source(personal, environ={"KIATRACKER_PERSONAL": "1"})
    assert source == source.__class__(personal, demo=False)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_demo_flag_wins_over_personal_opt_in(personal, value):
    source = resolve_source(personal, environ={"KIATRACKER_PERSONAL": "1", "KIATRACKER_DEMO": value})
    assert source.demo is True and source.db_path is None


@pytest.mark.parametrize("value", ["0", "false", ""])
def test_demo_flag_off_values(personal, value):
    source = resolve_source(personal, environ={"KIATRACKER_PERSONAL": "1", "KIATRACKER_DEMO": value})
    assert source.demo is False


@pytest.mark.parametrize(
    "address,local",
    [("127.0.0.1", True), ("localhost", True), ("::1", True), ("0.0.0.0", False), ("", False), (None, False)],
)
def test_is_local_only(address, local):
    assert is_local_only(address) is local


def test_demo_database_has_drives(tmp_path):
    db = build_demo_database(tmp_path, days=10)
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute("select count(*) from drives").fetchone()[0] > 5
        assert con.execute("select count(*) from drives where start_zone = 'home'").fetchone()[0] > 0


def test_demo_database_defaults_to_a_private_new_folder():
    a, b = build_demo_database(days=3), build_demo_database(days=3)
    assert a.parent != b.parent and a.parent.name.startswith("kiatracker-demo-")


def test_personal_data_only_on_localhost_unless_container_publishes_locally():
    from kiatracker.dashboard.source import may_show_personal

    assert may_show_personal("127.0.0.1", environ={})
    assert not may_show_personal("0.0.0.0", environ={})
    # in a container the server must listen on 0.0.0.0; compose publishes the port on the host's 127.0.0.1
    assert may_show_personal("0.0.0.0", environ={"KIATRACKER_IN_CONTAINER": "1"})
    assert not may_show_personal("0.0.0.0", environ={"KIATRACKER_IN_CONTAINER": "true"})
