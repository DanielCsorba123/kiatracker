"""Builders for raw records in the exact shape the Pleos API and the collector produce."""

from datetime import UTC, datetime

from kiatracker.raw import append_record


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_record(group: str, ts: datetime, data: dict, status: int = 200) -> dict:
    return {
        "fetched_at": ts.isoformat(),
        "endpoint": group,
        "http_status": status,
        "body": {"data": {**data, "timestamp": iso(ts)}, "meta": {"code": status}},
    }


def battery(ts, soc, charging=False, plugin="disconnected", capacity_kj=293040.0):
    return snapshot_record(
        "batteries",
        ts,
        {
            "charge": {
                "plugin": plugin,
                "status": "charging" if charging else "notCharging",
                "charging": charging,
                "stateOfCharge": soc,
                "batteryCapacity": capacity_kj,
                "targetStateOfCharge": {"standard": 100, "quick": 90},
                "remainTime": 120 if charging else 0,
            }
        },
    )


def driving(ts, odometer, ignition_on=False):
    return snapshot_record(
        "driving",
        ts,
        {
            "ignition": {"status": "on" if ignition_on else "off"},
            "sleepMode": "off",
            "odometer": None if odometer is None else {"value": odometer, "unit": "km"},
            "transmission": {"parkingPosition": not ignition_on},
        },
    )


def location(ts, lat, lon, speed=0.0):
    return snapshot_record(
        "locations",
        ts,
        {
            "location": {
                "latitude": lat,
                "longitude": lon,
                "altitude": 0.0,
                "heading": 90.0,
                "speed": {"value": speed, "unit": "kph"},
                "type": 0,
            }
        },
    )


def status(ts, climate_on=False, seat_heat=False):
    seat = {"heat": "on" if seat_heat else "off", "ventilation": "off"}
    return snapshot_record(
        "status",
        ts,
        {
            "climateControl": {
                "mode": "auto" if climate_on else "off",
                "status": "on" if climate_on else "off",
            },
            "windshield": {"defrost": "off"},
            "steeringWheelHeat": "off",
            "seats": [{"left": seat, "right": {"heat": "off", "ventilation": "off"}}],
            "tire": [{"left": 255.0, "right": 255.0, "unit": "psi"}],
        },
    )


def range_km(ts, value):
    return snapshot_record(
        "powertrains", ts, {"distanceToEmpties": [{"type": "EV", "value": value, "unit": "km"}]}
    )


def trips_record(fetched: datetime, trips: list[tuple[datetime, float]]) -> dict:
    """trips: (start, minutes)."""
    return {
        "fetched_at": fetched.isoformat(),
        "query": {},
        "http_status": 200,
        "isla_compacted": True,
        "body": {
            "data": {
                "trips": [
                    {
                        "triggerStartTime": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "tripLength": int(minutes * 60000),
                        "isla": {},
                    }
                    for start, minutes in trips
                ]
            }
        },
    }


def write(raw_dir, kind, records, now=None):
    for record in records:
        append_record(raw_dir, kind, record, now or datetime.fromisoformat(record["fetched_at"]))
