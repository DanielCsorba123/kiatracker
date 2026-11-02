from pathlib import Path

from kiatracker.config import load_settings


def test_reads_env_txt_when_no_env(tmp_path: Path):
    (tmp_path / ".env.txt").write_text("PLEOS_API_KEY_CLIENT_ID=abc\r\nPLEOS_API_KEY_CLIENT_SECRET='s3'\r\n")
    settings = load_settings(tmp_path, environ={})
    assert settings.client_id == "abc"
    assert settings.client_secret == "s3"


def test_environment_overrides_file(tmp_path: Path):
    (tmp_path / ".env").write_text("PLEOS_API_KEY_CLIENT_ID=from-file\n")
    settings = load_settings(tmp_path, environ={"PLEOS_API_KEY_CLIENT_ID": "from-env"})
    assert settings.client_id == "from-env"


def test_home_requires_both_coordinates(tmp_path: Path):
    assert load_settings(tmp_path, environ={"KIATRACKER_HOME_LAT": "47.1"}).home is None
    both = load_settings(tmp_path, environ={"KIATRACKER_HOME_LAT": "47.1", "KIATRACKER_HOME_LON": "19.2"})
    assert both.home == (47.1, 19.2)


def test_defaults(tmp_path: Path):
    settings = load_settings(tmp_path, environ={})
    assert settings.data_dir == tmp_path / "data"
    assert settings.raw_dir == tmp_path / "data" / "raw"
    assert settings.db_path == tmp_path / "data" / "kiatracker.duckdb"
    assert settings.home_radius_km == 0.3
    assert settings.client_id is None
