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


def test_collect_network_failure_is_reported_not_raised(tmp_path, capsys, monkeypatch):
    import httpx

    from kiatracker import cli

    monkeypatch.setenv("PLEOS_API_KEY_CLIENT_ID", "id")
    monkeypatch.setenv("PLEOS_API_KEY_CLIENT_SECRET", "secret")

    def offline(self):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(cli.PleosClient, "vehicles", offline)
    assert main(["--data-dir", str(tmp_path), "collect"]) == 1
    assert "collect failed" in capsys.readouterr().out


def test_dashboard_command_binds_localhost_and_passes_demo(tmp_path):
    from kiatracker.cli import dashboard_command

    argv, env = dashboard_command(demo=True, environ={"PATH": "x"})
    assert argv[1:4] == ["-m", "streamlit", "run"] and argv[4].endswith("app.py")
    assert argv[argv.index("--server.address") + 1] == "127.0.0.1"
    assert env["KIATRACKER_DEMO"] == "1" and env["PATH"] == "x"
    _, personal = dashboard_command(demo=False, environ={})
    assert "KIATRACKER_DEMO" not in personal


def test_dashboard_command_turns_off_usage_stats_and_error_details():
    from kiatracker.cli import dashboard_command

    argv, env = dashboard_command(demo=False, environ={})
    assert argv[argv.index("--browser.gatherUsageStats") + 1] == "false"
    assert argv[argv.index("--client.showErrorDetails") + 1] == "none"
    assert env["KIATRACKER_PERSONAL"] == "1"
    _, demo_env = dashboard_command(demo=True, environ={})
    assert "KIATRACKER_PERSONAL" not in demo_env


def test_train_and_forecast_on_demo_data(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "demo", "--days", "40"]) == 0
    demo = str(tmp_path / "demo")
    assert main(["--data-dir", demo, "train"]) == 0
    out = capsys.readouterr().out
    assert "MAE" in out and "headwind" in out
    assert (tmp_path / "demo" / "models" / "range.json").exists()
    assert main(["--data-dir", demo, "forecast", "--offline"]) == 0
    assert "km" in capsys.readouterr().out


def test_train_with_too_few_drives(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "build"]) == 0
    assert main(["--data-dir", str(tmp_path), "train"]) == 1
    assert "need 15 more drives" in capsys.readouterr().out
