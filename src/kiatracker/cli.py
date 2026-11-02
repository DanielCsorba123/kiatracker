"""Command line: kiatracker [--data-dir DIR] collect | build | weather | demo | stats."""

import argparse
import dataclasses
import json
import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from kiatracker.collect import poll
from kiatracker.config import Settings, load_settings
from kiatracker.db import build_database, derive_all, stats
from kiatracker.pleos import PleosClient, PleosError
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kiatracker", description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="overrides KIATRACKER_DATA_DIR")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect", help="poll the car once and store new readings")
    sub.add_parser("build", help="rebuild the database from raw files")
    sub.add_parser("weather", help="fetch missing weather for drives, then rebuild")
    demo = sub.add_parser("demo", help="generate fake data into <data-dir>/demo and build it")
    demo.add_argument("--days", type=int, default=30)
    sub.add_parser("stats", help="print a summary without coordinates")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.data_dir:
        settings = dataclasses.replace(settings, data_dir=args.data_dir.resolve())
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
    }
    return commands[args.command](settings, args)
