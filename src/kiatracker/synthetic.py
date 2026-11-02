"""Fake raw data in the exact format the collector writes, so the public repo runs without a car or account.

The simulated car lives at a fictional home, makes one or two round trips a day, uses more energy when it
is cold, and charges at home overnight when below 50 %. Readings follow how the real car reports: every
poll while driving, once when the ignition goes off, and every 15 minutes while charging.
"""

import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kiatracker.raw import append_record

FAKE_HOME = (47.0, 18.0)  # a field in rural Hungary, not anyone's home
DESTINATIONS = [(0.08, 0.12), (-0.05, 0.2), (0.15, -0.1), (0.02, 0.04)]  # offsets in degrees
CAPACITY_KJ = 293040.0
CAPACITY_KWH = CAPACITY_KJ / 3600
POLL = timedelta(minutes=5)
CHARGE_KW = 7.4


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Car:
    def __init__(self, raw_dir: Path, start: datetime):
        self.raw_dir = raw_dir
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
            append_record(self.raw_dir, "snapshots", record, fetched)

    def drive(self, start: datetime, to: tuple[float, float], km: float, temp: float, rng) -> datetime:
        speed = rng.uniform(35, 70)
        minutes = km / speed * 60
        end = start + timedelta(minutes=minutes)
        kwh_per_km = (14.5 + 0.3 * max(0.0, 15 - temp) + rng.uniform(-1, 1)) / 100
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


def generate(raw_dir: Path, start: datetime, days: int, seed: int = 7) -> list[dict]:
    """Write fake raw files; return the true drives (start, end, distance_km) to test the pipeline with."""
    rng = random.Random(seed)
    car = Car(raw_dir, start)
    truth: list[dict] = []
    for day in range(days):
        midnight = start + timedelta(days=day)
        temp = 4 + 8 * math.sin(day / 6) + rng.uniform(-3, 3)
        t = midnight + timedelta(hours=7, minutes=rng.randint(0, 90))
        day_trips = []
        for _ in range(rng.choice([1, 1, 2])):
            offset = rng.choice(DESTINATIONS)
            place = (FAKE_HOME[0] + offset[0], FAKE_HOME[1] + offset[1])
            for target in (place, FAKE_HOME):
                km = round(rng.uniform(3, 35), 1)
                end = car.drive(t, target, km, temp, rng)
                truth.append({"start": t.isoformat(), "end": end.isoformat(), "distance_km": km})
                day_trips.append((t, end))
                t = end + timedelta(hours=rng.uniform(0.5, 8))
        if car.soc < 50:
            car.charge(t + timedelta(minutes=10), temp)
        fetched = midnight + timedelta(days=1)
        trips = [
            {
                "triggerStartTime": s.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "tripLength": int((e - s).total_seconds() * 1000),
                "isla": {},
            }
            for s, e in day_trips
        ]
        append_record(
            raw_dir,
            "trips",
            {
                "fetched_at": fetched.isoformat(),
                "query": {},
                "http_status": 200,
                "body": {"data": {"trips": trips}},
                "isla_compacted": True,
            },
            fetched,
        )
    return truth
