"""Throwaway probe: what does the Pleos Vehicle Data API return for our car?

Not part of the real project. Prints a redacted summary (VIN, GPS and
nickname hidden) and saves the raw responses, which do contain them, under
spikes/probe_output/ (gitignored).

Run from the project root:  python spikes/pleos_probe.py
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://api.pleos.ai"
BRAND = "kia"
ZONE = "Europe/Budapest"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "probe_output" / datetime.now().strftime("%Y%m%d-%H%M%S")

SNAPSHOTS = {
    "batteries": "/v1/vehicles/{vin}/batteries",
    "powertrains": "/v1/vehicles/{vin}/powertrains",
    "locations": "/v1/vehicles/{vin}/locations",
    "driving": "/v1/vehicles/{vin}/driving",
    "status": "/v1/vehicles/{vin}/status",
}
TRIPS = {
    "driving_data": "/v1/vehicles/{vin}/driving/data",
    "speed": "/v1/vehicles/{vin}/speed",
    "powertrains_data": "/v1/vehicles/{vin}/powertrains/data",
    "status_data": "/v1/vehicles/{vin}/status/data",
}
HIDDEN_KEYS = {"vin", "latitude", "longitude", "nickname"}
RETENTION_WEEKS = (1, 2, 4, 8, 13, 26)
MAX_LINES = 80

masks = {}  # real VIN -> masked VIN, so it never reaches the console


def load_env():
    for name in (".env", ".env.txt"):
        path = ROOT / name
        if path.exists():
            env = {}
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip().strip("\"'")
            return name, env
    sys.exit(f"No .env or .env.txt found in {ROOT}")


def call(method, path, token=None, body=None, query=None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Brand": BRAND, "Content-Type": "application/json", "User-Agent": "kiatracker-probe/0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, parse(response.read())
    except urllib.error.HTTPError as err:
        return err.code, parse(err.read())
    except urllib.error.URLError as err:
        return None, {"network_error": str(err.reason)}


def parse(raw):
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"non_json_body": text[:500]}


def redact(obj):
    if isinstance(obj, dict):
        return {k: "<hidden>" if k in HIDDEN_KEYS else redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        for real, masked in masks.items():
            obj = obj.replace(real, masked)
    return obj


def save(name, status, payload):
    name = name.replace("*", "x")  # Windows forbids * in file names
    (OUT / f"{name}.json").write_text(json.dumps({"http_status": status, "body": payload}, indent=2), encoding="utf-8")


def show(name, status, payload):
    print(f"\n=== {name}  (HTTP {status})")
    body = payload.get("data", payload) if isinstance(payload, dict) else payload
    lines = json.dumps(redact(body), indent=2).splitlines()
    print("\n".join(lines[:MAX_LINES]))
    if len(lines) > MAX_LINES:
        print(f"... ({len(lines) - MAX_LINES} more lines in the raw file)")


def print_age(payload):
    stamp = ((payload or {}).get("data") or {}).get("timestamp") if isinstance(payload, dict) else None
    if not stamp:
        return
    try:
        reported = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        print(f"--> car timestamp {stamp!r} (could not parse)")
        return
    age = datetime.now(timezone.utc) - reported
    print(f"--> car reported this {age.total_seconds() / 3600:.1f} h ago ({stamp})")


def arrays(obj, prefix=""):
    """Yield (path, list) for every list of plain values inside a trip."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from arrays(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list) and not any(isinstance(v, (dict, list)) for v in obj):
        yield prefix, obj


def summarize_trips(name, status, payload):
    trips = (((payload or {}).get("data") or {}).get("trips")) if isinstance(payload, dict) else None
    if status != 200 or trips is None:
        show(name, status, payload)
        return
    print(f"\n=== {name}  (HTTP {status}) -> {len(trips)} trips in the last 7 days")
    for trip in trips[:10]:
        length_ms = trip.get("tripLength") or 0
        print(f"  trip {trip.get('triggerStartTime')}  length {length_ms / 60000:.1f} min")
        for path, values in arrays({k: v for k, v in trip.items() if k not in ("triggerStartTime", "tripLength")}):
            interval = f", ~{length_ms / 1000 / len(values):.1f} s/sample" if values and length_ms else ""
            head, tail = redact(values[:3]), redact(values[-3:])
            print(f"    {path}: {len(values)} values{interval}  first {head}  last {tail}")
    if len(trips) > 10:
        print(f"  ... {len(trips) - 10} more trips in the raw file")


def yyyymmdd(day):
    return day.strftime("%Y%m%d")


def window(end):
    return {"startDate": yyyymmdd(end - timedelta(days=6)), "endDate": yyyymmdd(end), "zoneId": ZONE}


def probe_vehicle(token, vehicle):
    vin = vehicle["vin"]
    masks[vin] = f"VIN***{vin[-3:]}"
    print(f"\n##### Vehicle {masks[vin]}: {vehicle.get('sellname')} / {vehicle.get('name')} / type {vehicle.get('type')}")

    for name, path in SNAPSHOTS.items():
        status, payload = call("GET", path.format(vin=vin), token)
        save(f"{masks[vin]}_{name}", status, payload)
        show(name, status, payload)
        print_age(payload)

    today = date.today()
    for name, path in TRIPS.items():
        status, payload = call("GET", path.format(vin=vin), token, query=window(today))
        save(f"{masks[vin]}_{name}", status, payload)
        summarize_trips(name, status, payload)

    print("\n=== retention check: trips per 7-day window, going back in time (driving/data)")
    for weeks in RETENTION_WEEKS:
        end = today - timedelta(weeks=weeks)
        status, payload = call("GET", TRIPS["driving_data"].format(vin=vin), token, query=window(end))
        save(f"{masks[vin]}_retention_{weeks}w", status, payload)
        trips = (((payload or {}).get("data") or {}).get("trips")) if isinstance(payload, dict) else None
        result = f"{len(trips)} trips" if status == 200 and trips is not None else f"HTTP {status}: {redact(payload)}"
        print(f"  {weeks:>2} weeks back ({window(end)['startDate']}-{window(end)['endDate']}): {result}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    env_name, env = load_env()
    client_id = env.get("PLEOS_API_KEY_CLIENT_ID")
    client_secret = env.get("PLEOS_API_KEY_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(f"{env_name} needs PLEOS_API_KEY_CLIENT_ID and PLEOS_API_KEY_CLIENT_SECRET")
    print(f"Credentials from {env_name}; raw responses go to {OUT}")
    OUT.mkdir(parents=True)

    status, payload = call("POST", "/v1/auth/personal-token", body={"clientId": client_id, "clientSecret": client_secret})
    token = ((payload.get("data") or {}).get("accessToken")) if isinstance(payload, dict) else None
    if not token:
        save("auth", status, payload)
        show("auth", status, payload)
        sys.exit("Could not get an access token.")
    print("\n=== auth: OK, got an access token")

    status, payload = call("GET", "/v1/vehicles/consent", token)
    save("consent", status, payload)
    vehicles = (((payload.get("data") or {}).get("vehicles")) if isinstance(payload, dict) else None) or []
    for vehicle in vehicles:
        masks[vehicle["vin"]] = f"VIN***{vehicle['vin'][-3:]}"
    show("consent", status, payload)
    if not vehicles:
        print("\nNo vehicles on this key. The key only sees cars that were in the Kia account when it was issued,"
              "\nso after re-adding the car in the Kia app, revoke and reissue the key in the Pleos workspace.")
        return
    for vehicle in vehicles:
        probe_vehicle(token, vehicle)


if __name__ == "__main__":
    main()
