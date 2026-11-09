"""What the public demo says about the real tracker: aggregates only, never places, times or the VIN.

The public site runs on simulated data until the real collection is rich enough to be worth showing (in
anonymised form): enough trustworthy drives, including cold ones, since winter is where range matters most.
`kiatracker showcase-status` writes this summary to a small JSON file that is committed with the code; the
demo banner reads it.
"""

import json
import math
from datetime import date, timedelta
from pathlib import Path

import duckdb

STATUS_FILE = Path(__file__).parent / "dashboard" / "real_data_status.json"
TARGET_DRIVES = 60  # trustworthy drives of 5 km or more with energy
TARGET_COLD = 10  # of which below 5 °C
COLD_C = 5.0
WINTER_STARTS = 12  # cold drives that are still missing arrive with winter


def expected_switch(today: date, drives: int, cold: int, since: date) -> date:
    """When both targets should be met at the current pace. Missing cold drives wait for winter (from
    December), then arrive over about a month."""
    pace = drives / max((today - since).days, 1)  # trustworthy drives per day so far
    if drives >= TARGET_DRIVES:
        by_drives = today
    elif pace > 0:
        by_drives = today + timedelta(days=math.ceil((TARGET_DRIVES - drives) / pace))
    else:
        by_drives = today + timedelta(days=365)
    by_cold = today
    if cold < TARGET_COLD:
        in_winter = today.month in (12, 1, 2)
        winter = today if in_winter else date(today.year, WINTER_STARTS, 1)
        by_cold = winter + timedelta(days=math.ceil(31 * (TARGET_COLD - cold) / TARGET_COLD))
    return max(by_drives, by_cold)


def real_data_status(con: duckdb.DuckDBPyConnection, today: date) -> dict:
    since = con.execute("select min(ts)::date from readings_battery").fetchone()[0]
    drives, km, cold = con.execute(
        f"""select count(*), coalesce(sum(d.distance_km), 0), count(*) filter (where w.temp_c < {COLD_C})
            from drives d left join drive_weather w using (drive_id)
            where d.quality = 'ok' and not d.in_progress and d.kwh_per_100km is not null
              and d.distance_km >= 5"""
    ).fetchone()
    switch = expected_switch(today, drives, cold, since) if since else None
    return {
        "collecting_since": since.isoformat() if since else None,
        "updated": today.isoformat(),
        "trustworthy_drives": drives,
        "km": round(km),
        "cold_drives": cold,
        "target_drives": TARGET_DRIVES,
        "target_cold_drives": TARGET_COLD,
        "expected_real_data": switch.strftime("%Y-%m") if switch else None,
    }


def write_status(status: dict, path: Path = STATUS_FILE) -> None:
    path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def load_status(path: Path = STATUS_FILE) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
