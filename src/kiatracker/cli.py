"""Command line: kiatracker [--data-dir DIR] collect | build | weather | train | forecast | demo | stats |
dashboard."""

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median

import duckdb
import httpx

from kiatracker.collect import poll
from kiatracker.config import Settings, load_settings
from kiatracker.db import build_database, derive_all, stats
from kiatracker.forecast.features import drive_features
from kiatracker.forecast.model import NotEnoughData, RangeModel
from kiatracker.forecast.outlook import LOCAL, daily_outlook, fetch_forecast, latest_forecast
from kiatracker.forecast.train import DEFAULT_SPEED, MODEL_FILE, car_state, train, weather_cell
from kiatracker.pleos import PleosClient, PleosError
from kiatracker.prices import download_oil_bulletin, fuel_is_stale, parse_oil_bulletin, store_fuel_prices
from kiatracker.schedule import Job, run_jobs
from kiatracker.synthetic import FAKE_HOME, generate
from kiatracker.weather import fetch_weather


def vin_for(client: PleosClient, settings: Settings) -> str:
    """The car's VIN, cached locally so each poll doesn't need an extra API call."""
    cache = settings.data_dir / "vehicle.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["vin"]
    vehicles = client.vehicles()
    if not vehicles:
        raise PleosError("no vehicle on this API key: re-add the car in the Kia app, then reissue the key")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"vin": vehicles[0]["vin"]}), encoding="utf-8")
    return vehicles[0]["vin"]


def cmd_collect(settings: Settings, args) -> int:
    if not settings.client_id or not settings.client_secret:
        print(
            "Set PLEOS_API_KEY_CLIENT_ID and PLEOS_API_KEY_CLIENT_SECRET (environment or .env)",
            file=sys.stderr,
        )
        return 2
    client = PleosClient(settings.client_id, settings.client_secret)
    try:
        result = poll(client, vin_for(client, settings), settings.raw_dir)
    except PleosError as err:
        print(f"{datetime.now():%m-%d %H:%M}  collect failed: {err} ({err.status} {err.code})", flush=True)
        return 1
    except httpx.HTTPError as err:  # e.g. the PC just woke up and has no network yet
        print(f"{datetime.now():%m-%d %H:%M}  collect failed: {type(err).__name__}", flush=True)
        return 1
    print(f"{datetime.now():%m-%d %H:%M}  {result.summary}", flush=True)
    return 0


def cmd_build(settings: Settings, args) -> int:
    for table, rows in build_database(settings).items():
        print(f"{table:20} {rows:>7}")
    return 0


def cmd_weather(settings: Settings, args) -> int:
    _, drives, _, _ = derive_all(settings)
    with httpx.Client() as http:
        fetched = fetch_weather(drives, settings.raw_dir, http, date.today())
    print(f"Fetched weather for {fetched} place-days")
    return cmd_build(settings, args)


def cmd_refresh(settings: Settings, args) -> int:
    """Everything after collecting, for a scheduler: weather, forecast, rebuild, retrain.

    Each step is best-effort, so a network outage never stops the database from being rebuilt.
    """
    r, drives, _, _ = derive_all(settings)
    cell = settings.home or next(((p.lat, p.lon) for p in reversed(r.location) if p.lat is not None), None)
    with httpx.Client() as http:
        try:
            fetched = fetch_weather(drives, settings.raw_dir, http, date.today())
            print(f"Weather fetched for {fetched} place-days")
        except httpx.HTTPError as err:
            print(f"Weather skipped: {type(err).__name__}")
        if cell:
            try:
                status = fetch_forecast(cell, settings.raw_dir, http, datetime.now(UTC))
                print("Forecast fetched" if status == 200 else f"Forecast not available (HTTP {status})")
            except httpx.HTTPError as err:
                print(f"Forecast skipped: {type(err).__name__}")
        if fuel_is_stale(settings.raw_dir, datetime.now(UTC)):
            try:
                weeks = parse_oil_bulletin(download_oil_bulletin(http))
                store_fuel_prices(settings.raw_dir, weeks, datetime.now(UTC))
                print(f"Fuel prices: {len(weeks)} weeks, latest {weeks[-1]['week'] if weeks else '-'}")
            except (httpx.HTTPError, KeyError, ValueError) as err:
                print(f"Fuel prices skipped: {type(err).__name__}")
    counts = build_database(settings)
    print(f"Rebuilt: {counts['drives']} drives, {counts['charging_sessions']} charging sessions")
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        try:
            trained = train(con)
        except NotEnoughData as err:
            print(f"Range model not trained: {err}")
            return 0
    trained.model.save(settings.data_dir / MODEL_FILE)
    print(f"Range model trained on {trained.model.n_drives} drives")
    return 0


def cmd_scheduler(settings: Settings, args) -> int:
    """Long-running loop for the container: collect every 5 minutes, refresh hourly (after the first poll)."""
    print("Scheduler started: collect every 5 min, refresh every hour", flush=True)
    run_jobs(
        [
            Job("collect", timedelta(minutes=5), lambda: cmd_collect(settings, args)),
            Job(
                "refresh",
                timedelta(hours=1),
                lambda: cmd_refresh(settings, args),
                first_delay=timedelta(minutes=2),
            ),
        ]
    )
    return 0


def cmd_demo(settings: Settings, args) -> int:
    demo = dataclasses.replace(settings, data_dir=settings.data_dir / "demo", home=FAKE_HOME)
    shutil.rmtree(demo.data_dir, ignore_errors=True)
    start = datetime.combine(date.today() - timedelta(days=args.days), datetime.min.time(), UTC)
    truth = generate(demo.raw_dir, start, args.days)
    print(f"Generated {len(truth)} fake drives over {args.days} days in {demo.data_dir}")
    build_database(demo)
    print(stats(demo))
    return 0


def cmd_stats(settings: Settings, args) -> int:
    print(stats(settings))
    return 0


def cmd_train(settings: Settings, args) -> int:
    if not settings.db_path.exists():
        print("No database yet: run `kiatracker build` first.")
        return 1
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        try:
            trained = train(con)
        except NotEnoughData as err:
            print(f"Can't train yet: {err}.")
            return 1
    trained.model.save(settings.data_dir / MODEL_FILE)
    print(f"Trained on {trained.model.n_drives} drives.")
    if trained.backtest:
        print("Backtest, predicting later drives from earlier ones (MAE, kWh/100 km):")
        for name in ("model", "temperature_only", "mean"):
            print(f"  {name:17} {trained.backtest[name]['mae']:.2f}")
    for line in trained.model.explain(trained.typical_speed_kph):
        print(line)
    return 0


def cmd_forecast(settings: Settings, args) -> int:
    model_path = settings.data_dir / MODEL_FILE
    if not model_path.exists() or not settings.db_path.exists():
        print("No model yet: run `kiatracker train` first.")
        return 1
    model = RangeModel.load(model_path)
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        soc, capacity = car_state(con)
        cell = weather_cell(con, settings.home)
        speed = median([r["speed_kph"] for r in drive_features(con)] or [DEFAULT_SPEED])
    if not args.offline and cell:
        try:
            with httpx.Client() as http:
                fetch_forecast(cell, settings.raw_dir, http, datetime.now(UTC))
        except httpx.HTTPError as err:
            print(
                f"Couldn't fetch a new forecast ({type(err).__name__}); using the last one if there is one."
            )
    hourly = latest_forecast(settings.raw_dir)
    if not hourly:
        print("No forecast available: run `kiatracker forecast` with a network connection.")
        return 1

    def km(value):
        return "-" if value is None else f"{value:.0f}"

    print(f"Battery {km(soc)}%, typical speed {speed:.0f} km/h. Daytime range by day:")

    for day in daily_outlook(hourly, model, soc, capacity, speed, datetime.now(LOCAL).date()):
        print(
            f"  {day['day']:%a %d %b}: {day['temp_c']:.0f} °C, wind {day['wind_kph']:.0f} km/h -> "
            f"{km(day['range_km'])} km ({km(day['range_lo'])}-{km(day['range_hi'])})"
        )
    return 0


def dashboard_command(
    demo: bool,
    environ: Mapping[str, str],
    data_dir: Path | None = None,
    port: int = 8501,
    address: str = "127.0.0.1",
) -> tuple[list[str], dict[str, str]]:
    """The streamlit command and environment; bound to this computer only."""
    app = Path(__file__).parent / "dashboard" / "app.py"
    argv = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        address,
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
        "--client.showErrorDetails",
        "none",  # no stack traces or file paths in the browser
    ]
    env = dict(environ)
    if demo:
        env["KIATRACKER_DEMO"] = "1"
    else:
        env["KIATRACKER_PERSONAL"] = "1"
    if data_dir:
        env["KIATRACKER_DATA_DIR"] = str(data_dir)
    return argv, env


def cmd_dashboard(settings: Settings, args) -> int:
    argv, env = dashboard_command(args.demo, os.environ, settings.data_dir, args.port, args.address)
    print(
        f"Dashboard on http://{args.address}:{args.port} ({'demo data' if args.demo else settings.data_dir})"
    )
    return subprocess.call(argv, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kiatracker", description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="overrides KIATRACKER_DATA_DIR")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect", help="poll the car once and store new readings")
    sub.add_parser("build", help="rebuild the database from raw files")
    sub.add_parser("weather", help="fetch missing weather for drives, then rebuild")
    sub.add_parser("refresh", help="weather, forecast, rebuild and retrain in one go (schedule hourly)")
    sub.add_parser("scheduler", help="run collect every 5 min and refresh hourly until stopped (for Docker)")
    demo = sub.add_parser("demo", help="generate fake data into <data-dir>/demo and build it")
    demo.add_argument("--days", type=int, default=30)
    sub.add_parser("stats", help="print a summary without coordinates")
    sub.add_parser("train", help="fit the range model on your drives and show how well it predicts")
    forecast = sub.add_parser("forecast", help="range for today and the next days in the forecast weather")
    forecast.add_argument("--offline", action="store_true", help="use the last fetched forecast")
    dashboard = sub.add_parser("dashboard", help="open the dashboard in your browser (this computer only)")
    dashboard.add_argument("--demo", action="store_true", help="show generated demo data, not yours")
    dashboard.add_argument("--port", type=int, default=8501)
    dashboard.add_argument(
        "--address", default="127.0.0.1", help="listen address; only change it inside a container"
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.data_dir:
        settings = dataclasses.replace(settings, data_dir=args.data_dir.resolve())
    if sys.stdout is not None and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")  # pipes and logs: keep °C readable on Windows
    if sys.stdout is None:  # pythonw under Task Scheduler has no console
        log_dir = settings.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(log_dir / f"{args.command}.log", "a", encoding="utf-8")  # noqa: SIM115
    commands = {
        "collect": cmd_collect,
        "build": cmd_build,
        "weather": cmd_weather,
        "demo": cmd_demo,
        "stats": cmd_stats,
        "dashboard": cmd_dashboard,
        "train": cmd_train,
        "forecast": cmd_forecast,
        "refresh": cmd_refresh,
        "scheduler": cmd_scheduler,
    }
    return commands[args.command](settings, args)
