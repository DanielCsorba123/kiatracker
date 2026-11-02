"""One poll of the car: store every snapshot group whose car timestamp is new, and the trip list every 6 h.

Scheduling lives outside the code (Task Scheduler now, a systemd timer on the Pi later).
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from kiatracker.pleos import SNAPSHOT_PATHS, TRIPS_PATH, PleosClient, RateLimited
from kiatracker.privacy import haversine_km
from kiatracker.raw import append_record, compact_isla

STATE_FILE = "logger_state.json"  # same file and keys as the spike logger, so it carries over
TRIP_SYNC_EVERY = timedelta(hours=6)
TRIP_ZONE = "Europe/Budapest"


@dataclass
class PollResult:
    new: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: str = ""


def load_state(raw_dir: Path) -> dict:
    try:
        state = json.loads((raw_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    return {"last_timestamp": {}, "last_position": None, "last_trip_sync": None, **state}


def save_state(raw_dir: Path, state: dict) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")


def poll(client: PleosClient, vin: str, raw_dir: Path, now: datetime | None = None) -> PollResult:
    now = now or datetime.now(UTC)
    state = load_state(raw_dir)
    result = PollResult()
    fetched_at = now.isoformat()
    data: dict[str, dict] = {}
    try:
        for group, path in SNAPSHOT_PATHS.items():
            status, payload = client.get(path.format(vin=vin))
            body = payload.get("data")
            if status != 200 or not isinstance(body, dict):
                append_record(raw_dir, "errors", {"fetched_at": fetched_at, "endpoint": group,
                                                  "http_status": status, "body": payload}, now)
                result.errors.append(group)
                continue
            data[group] = body
            if body.get("timestamp") != state["last_timestamp"].get(group):
                state["last_timestamp"][group] = body.get("timestamp")
                append_record(raw_dir, "snapshots", {"fetched_at": fetched_at, "endpoint": group,
                                                     "http_status": status, "body": payload}, now)
                result.new.append(group)

        last_sync = state["last_trip_sync"]
        if not last_sync or now - datetime.fromisoformat(last_sync) > TRIP_SYNC_EVERY:
            today = now.astimezone(ZoneInfo(TRIP_ZONE)).date()
            query = {"startDate": f"{today - timedelta(days=6):%Y%m%d}", "endDate": f"{today:%Y%m%d}",
                     "zoneId": TRIP_ZONE}
            status, payload = client.get(TRIPS_PATH.format(vin=vin), query)
            append_record(raw_dir, "trips", {"fetched_at": fetched_at, "query": query, "http_status": status,
                                             "body": compact_isla(payload), "isla_compacted": True}, now)
            state["last_trip_sync"] = fetched_at
            result.new.append("trips")
    except RateLimited:
        append_record(raw_dir, "errors", {"fetched_at": fetched_at, "endpoint": "any", "http_status": 429,
                                          "body": None}, now)
        result.errors.append("rate limited")

    result.summary = summarize(data, state, "locations" in result.new, result, now)
    save_state(raw_dir, state)
    return result


def summarize(data: dict, state: dict, new_location: bool, result: PollResult, now: datetime) -> str:
    """One log line without coordinates; updates state['last_position'] when the car reported a new one."""
    parts = []
    charge = (data.get("batteries") or {}).get("charge") or {}
    if charge:
        parts.append(f"SOC {charge.get('stateOfCharge')}% {charge.get('status')}")
    driving = data.get("driving") or {}
    if driving:
        parts.append(f"odo {(driving.get('odometer') or {}).get('value')}, "
                     f"ignition {(driving.get('ignition') or {}).get('status')}")
    location = data.get("locations") or {}
    loc = location.get("location") or {}
    if location.get("timestamp"):
        age = now - datetime.fromisoformat(location["timestamp"].replace("Z", "+00:00"))
        parts.append(f"location {age.total_seconds() / 60:.0f} min old")
    if new_location and loc.get("latitude") is not None:
        position = (float(loc["latitude"]), float(loc["longitude"]))
        if state["last_position"]:
            parts.append(f"moved {haversine_km(tuple(state['last_position']), position):.2f} km")
        state["last_position"] = position
    parts.append(f"new: {', '.join(result.new) or 'nothing'}")
    if result.errors:
        parts.append(f"errors: {', '.join(result.errors)}")
    return ", ".join(parts)
