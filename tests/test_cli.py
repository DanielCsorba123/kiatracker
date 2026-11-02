from kiatracker.cli import main


def test_demo_then_stats(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "demo", "--days", "10"]) == 0
    assert (tmp_path / "demo" / "kiatracker.duckdb").exists()
    capsys.readouterr()
    assert main(["--data-dir", str(tmp_path / "demo"), "stats"]) == 0
    assert "Drives:" in capsys.readouterr().out


def test_collect_without_credentials_fails_clearly(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PLEOS_API_KEY_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLEOS_API_KEY_CLIENT_SECRET", raising=False)
    assert main(["--data-dir", str(tmp_path), "collect"]) == 2
    assert "PLEOS_API_KEY_CLIENT_ID" in capsys.readouterr().err


def test_stats_before_build(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "stats"]) == 0
    assert "kiatracker build" in capsys.readouterr().out
