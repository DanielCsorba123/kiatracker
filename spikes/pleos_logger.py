"""Throwaway logger: save every new Pleos status reading while this runs.

Not part of the real project, but its output is: each new reading is appended
untouched to data/raw/ (gitignored) so the real pipeline can import it later.
Questions it answers: how often each value updates, and whether location
changes during a drive.

Run from the project root:
  python spikes/pleos_logger.py            # poll every 5 minutes until Ctrl+C
  python spikes/pleos_logger.py --once     # one poll, for a scheduler
"""
import argparse
import json
import math
import sys
import time
from datetime import date, datetime, timedelta, timezone

from pleos_probe import ROOT, SNAPSHOTS, TRIPS, ZONE, call, load_env

RAW = ROOT / "data" / "raw"
STATE = RAW / "logger_state.json"
TRIP_SYNC_EVERY = timedelta(hours=6)
TOKEN_ERRORS = {"40003", "40004"}


def now():
    return datetime.now(timezone.utc)


def append(kind, record):
    path = RAW / f"{kind}-{now():%Y-%m}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_timestamp": {}, "last_position": None, "last_trip_sync": None}


def error_code(payload):
    return str(((payload or {}).get("error") or {}).get("code", "")) if isinstance(payload, dict) else ""


class Client:
    def __init__(self, client_id, client_secret):
        self.credentials = {"clientId": client_id, "clientSecret": client_secret}
        self.token = None

    def login(self):
        status, payload = call("POST", "/v1/auth/personal-token", body=self.credentials)
        self.token = ((payload.get("data") or {}).get("accessToken")) if isinstance(payload, dict) else None
        if not self.token:
            raise RuntimeError(f"login failed: HTTP {status} {error_code(payload)}")

    def get(self, path, query=None):
        if not self.token:
            self.login()
        status, payload = call("GET", path, self.token, query=query)
        if error_code(payload) in TOKEN_ERRORS:
            self.login()
            status, payload = call("GET", path, self.token, query=query)
        return status, payload


def km_between(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def poll(client, vin, state):
    fetched_at = now().isoformat()
    new, data = [], {}
    for name, path in SNAPSHOTS.items():
        status, payload = client.get(path.format(vin=vin))
        if status == 429:
            raise RuntimeError("rate limited (HTTP 429)")
        body = payload.get("data") if isinstance(payload, dict) else None
        if status != 200 or not isinstance(body, dict):
            append("errors", {"fetched_at": fetched_at, "endpoint": name, "http_status": status, "body": payload})
            continue
        data[name] = body
        if body.get("timestamp") != state["last_timestamp"].get(name):
            state["last_timestamp"][name] = body.get("timestamp")
            append("snapshots", {"fetched_at": fetched_at, "endpoint": name, "http_status": status, "body": payload})
            new.append(name)

    moved = ""
    loc = (data.get("locations") or {}).get("location") or {}
    if "locations" in new and loc.get("latitude") is not None:
        position = (float(loc["latitude"]), float(loc["longitude"]))
        if state["last_position"]:
            moved = f" moved {km_between(state['last_position'], position):.2f} km,"
        state["last_position"] = position

    last_sync = state["last_trip_sync"]
    if not last_sync or now() - datetime.fromisoformat(last_sync) > TRIP_SYNC_EVERY:
        today = date.today()
        query = {"startDate": f"{today - timedelta(days=6):%Y%m%d}", "endDate": f"{today:%Y%m%d}", "zoneId": ZONE}
        status, payload = client.get(TRIPS["driving_data"].format(vin=vin), query)
        for trip in (((payload or {}).get("data") or {}).get("trips") or []) if isinstance(payload, dict) else []:
            # isla is ~1 value/s of the same string: keep its shape, drop the 1 MB of repeats
            trip["isla"] = {k: {"len": len(v), "distinct": sorted(set(map(str, v)))} for k, v in (trip.get("isla") or {}).items()}
        append("trips", {"fetched_at": fetched_at, "query": query, "http_status": status, "body": payload, "isla_compacted": True})
        state["last_trip_sync"] = now().isoformat()
        new.append("trips")

    charge = (data.get("batteries") or {}).get("charge") or {}
    odometer = ((data.get("driving") or {}).get("odometer") or {}).get("value")
    ignition = ((data.get("driving") or {}).get("ignition") or {}).get("status")
    location_age = ""
    if data.get("locations", {}).get("timestamp"):
        age = now() - datetime.fromisoformat(data["locations"]["timestamp"].replace("Z", "+00:00"))
        location_age = f" location {age.total_seconds() / 60:.0f} min old,"
    print(f"{datetime.now():%m-%d %H:%M}  SOC {charge.get('stateOfCharge')}% {charge.get('status')}, "
          f"odo {odometer}, ignition {ignition},{location_age}{moved} new: {', '.join(new) or 'nothing'}", flush=True)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:  # pythonw (Task Scheduler) has no console
        sys.stdout = sys.stderr = open(RAW / "logger.log", "a", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    parser.add_argument("--minutes", type=float, default=5, help="minutes between polls")
    args = parser.parse_args()

    _, env = load_env()
    client = Client(env["PLEOS_API_KEY_CLIENT_ID"], env["PLEOS_API_KEY_CLIENT_SECRET"])
    RAW.mkdir(parents=True, exist_ok=True)
    client.login()
    status, payload = client.get("/v1/vehicles/consent")
    vehicles = ((payload.get("data") or {}).get("vehicles")) if isinstance(payload, dict) else None
    if not vehicles:
        sys.exit(f"No vehicle on this key (HTTP {status})")
    vin = vehicles[0]["vin"]
    if not args.once:
        print(f"Logging to {RAW} every {args.minutes:g} min. Ctrl+C to stop.", flush=True)

    while True:
        state = load_state()
        try:
            poll(client, vin, state)
        except Exception as err:  # keep logging through network hiccups
            print(f"{datetime.now():%m-%d %H:%M}  poll failed: {err}", flush=True)
            append("errors", {"fetched_at": now().isoformat(), "exception": str(err)})
        STATE.write_text(json.dumps(state), encoding="utf-8")
        if args.once:
            return
        time.sleep(args.minutes * 60)


if __name__ == "__main__":
    main()
