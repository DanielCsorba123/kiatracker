"""Fake raw data in the exact format the collector writes, so the public repo runs without a car or account.

The simulated car lives at a fictional home, makes one or two round trips a day, uses more energy when it
is cold, and charges at home overnight when below 50 %. Readings follow how the real car reports: every
poll while driving, once when the ignition goes off, and every 15 minutes while charging.
"""

import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kiatracker.raw import append_records

FAKE_HOME = (47.0, 18.0)  # a field in rural Hungary, not anyone's home
DESTINATIONS = [(0.08, 0.12), (-0.05, 0.2), (0.15, -0.1), (0.02, 0.04)]  # offsets in degrees
CAPACITY_KJ = 293040.0
CAPACITY_KWH = CAPACITY_KJ / 3600
POLL = timedelta(minutes=5)
CHARGE_KW = 7.4
WEATHER_CELLS = 2  # cells each side of home: drive midpoints stay within 0.2 degrees


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Car:
    def __init__(self, start: datetime):
        self.out: dict[str, list] = {
            "snapshots": [],
            "trips": [],
            "weather": [],
        }  # written in one go at the end
        self.odo, self.soc, self.pos = 10000.0, 80.0, FAKE_HOME
        self.report(start, ignition_on=False, charging=False, temp=5.0)

    def report(self, ts: datetime, ignition_on: bool, charging: bool, temp: float, speed: float = 0.0):
        groups = {
            "batteries": {
                "charge": {
                    "plugin": "connected" if charging else "disconnected",
                    "status": "charging" if charging else "notCharging",
                    "charging": charging,
                    "stateOfCharge": round(self.soc * 2) / 2,
                    "batteryCapacity": CAPACITY_KJ,
                    "targetStateOfCharge": {"standard": 90, "quick": 90},
                    "remainTime": 60 if charging else 0,
                }
            },
            "powertrains": {
                "distanceToEmpties": [{"type": "EV", "value": str(round(self.soc * 5)), "unit": "km"}]
            },
            "locations": {
                "location": {
                    "latitude": f"{self.pos[0]:.6f}",
                    "longitude": f"{self.pos[1]:.6f}",
                    "altitude": 0.0,
                    "heading": 0.0,
                    "speed": {"value": speed, "unit": "kph"},
                    "type": 0,
                }
            },
            "driving": {
                "ignition": {"status": "on" if ignition_on else "off"},
                "sleepMode": "off",
                "odometer": {"value": round(self.odo, 1), "unit": "km"},
                "transmission": {"parkingPosition": not ignition_on},
            },
            "status": {
                "climateControl": {"mode": "auto", "status": "on" if ignition_on and temp < 12 else "off"},
                "windshield": {"defrost": "off"},
                "steeringWheelHeat": "off",
                "seats": [],
            },
        }
        fetched = ts + timedelta(minutes=1)
        for group, data in groups.items():
            record = {
                "fetched_at": fetched.isoformat(),
                "endpoint": group,
                "http_status": 200,
                "body": {"data": {**data, "timestamp": iso(ts)}},
            }
            self.out["snapshots"].append((fetched, record))

    def drive(
        self, start: datetime, to: tuple[float, float], km: float, temp: float, wind: float, rng
    ) -> datetime:
        speed = rng.uniform(35, 70)
        minutes = km / speed * 60
        end = start + timedelta(minutes=minutes)
        headwind = wind * rng.uniform(-0.5, 1.0)  # direction relative to the route, mostly against
        kwh_per_km = (14.5 + 0.3 * max(0.0, 15 - temp) + 0.12 * headwind + rng.uniform(-1, 1)) / 100
        origin, odo0, soc0 = self.pos, self.odo, self.soc
        t = start + POLL
        while True:
            done = min(1.0, (t - start) / (end - start))
            self.odo = odo0 + km * done
            self.soc = soc0 - km * done * kwh_per_km / CAPACITY_KWH * 100
            self.pos = (origin[0] + (to[0] - origin[0]) * done, origin[1] + (to[1] - origin[1]) * done)
            if done >= 1:
                self.report(end, ignition_on=False, charging=False, temp=temp)
                return end
            self.report(t, ignition_on=True, charging=False, temp=temp, speed=speed)
            t += POLL
            if end - t < timedelta(minutes=1):  # the car never sends two readings within the same second
                t = end

    def charge(self, start: datetime, temp: float) -> datetime:
        t = start
        while self.soc < 90:
            self.report(t, ignition_on=False, charging=True, temp=temp)
            t += timedelta(minutes=15)
            self.soc = min(90.0, self.soc + CHARGE_KW * 0.25 / CAPACITY_KWH * 100)
        self.report(t, ignition_on=False, charging=False, temp=temp)
        return t


def write_weather(out: dict, midnight: datetime, temp: float, wind: float) -> None:
    """Open-Meteo-shaped hourly weather for every 0.1 degree cell around the fake home, as the weather
    command would have cached it."""
    day = midnight.date().isoformat()
    hourly = {
        "time": [f"{day}T{h:02d}:00" for h in range(24)],
        "temperature_2m": [round(temp + 3 * math.sin((h - 9) / 24 * 2 * math.pi), 1) for h in range(24)],
        "wind_speed_10m": [round(wind * (0.8 + 0.4 * math.sin(h / 5)), 1) for h in range(24)],
        "wind_direction_10m": [270.0] * 24,
        "wind_gusts_10m": [round(wind * 1.6, 1)] * 24,
    }
    for i in range(-WEATHER_CELLS, WEATHER_CELLS + 1):
        for j in range(-WEATHER_CELLS, WEATHER_CELLS + 1):
            key = {
                "lat": round(FAKE_HOME[0] + i / 10, 1),
                "lon": round(FAKE_HOME[1] + j / 10, 1),
                "date": day,
            }
            record = {
                "fetched_at": midnight.isoformat(),
                "endpoint": "open-meteo",
                "key": key,
                "http_status": 200,
                "body": {"hourly": hourly},
            }
            out["weather"].append((midnight, record))


def generate(raw_dir: Path, start: datetime, days: int, seed: int = 7) -> list[dict]:
    """Write fake raw files; return the true drives (start, end, distance_km) to test the pipeline with."""
    rng = random.Random(seed)
    car = Car(start)
    truth: list[dict] = []
    busy_until = start  # the car can't leave before the last charge or drive has finished
    for day in range(days):
        midnight = start + timedelta(days=day)
        temp = 4 + 8 * math.sin(day / 6) + rng.uniform(-3, 3)
        wind = rng.uniform(5, 35)
        write_weather(car.out, midnight, temp, wind)
        t = max(midnight + timedelta(hours=7, minutes=rng.randint(0, 90)), busy_until + timedelta(minutes=10))
        day_trips = []
        for _ in range(rng.choice([1, 1, 2])):
            offset = rng.choice(DESTINATIONS)
            place = (FAKE_HOME[0] + offset[0], FAKE_HOME[1] + offset[1])
            for target in (place, FAKE_HOME):
                km = round(rng.uniform(3, 35), 1)
                end = car.drive(t, target, km, temp, wind, rng)
                truth.append({"start": t.isoformat(), "end": end.isoformat(), "distance_km": km})
                day_trips.append((t, end))
                t = end + timedelta(hours=rng.uniform(0.5, 8))
        if car.soc < 50:
            busy_until = car.charge(t + timedelta(minutes=10), temp)
        else:
            busy_until = t
        fetched = midnight + timedelta(days=1)
        trips = [
            {
                "triggerStartTime": s.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "tripLength": int((e - s).total_seconds() * 1000),
                "isla": {},
            }
            for s, e in day_trips
        ]
        car.out["trips"].append(
            (
                fetched,
                {
                    "fetched_at": fetched.isoformat(),
                    "query": {},
                    "http_status": 200,
                    "body": {"data": {"trips": trips}},
                    "isla_compacted": True,
                },
            )
        )
    write_weather(car.out, start + timedelta(days=days), temp, wind)  # drives running past midnight
    for kind, records in car.out.items():
        append_records(raw_dir, kind, records)
    return truth
