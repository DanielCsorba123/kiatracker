"""Fake raw data in the exact format the collector writes, so the public repo runs without a car or account.

The simulated car lives at a fictional home and makes one or two round trips a day. Its consumption follows
the range model's physics with known true coefficients (TRUTH), using the same hourly weather it writes and
the real bearing of each drive against the day's wind, so fitting the model must recover TRUTH. Readings
follow how the real car reports: every poll while driving, once when the ignition goes off, and every
15 minutes while charging.
"""

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kiatracker.geo import bearing_deg, headwind_kph
from kiatracker.raw import append_record, append_records

FAKE_HOME = (47.0, 18.0)  # a field in rural Hungary, not anyone's home
DESTINATIONS = [(0.08, 0.12), (-0.05, 0.2), (0.15, -0.1), (0.02, 0.04)]  # offsets in degrees
CAPACITY_KJ = 293040.0
CAPACITY_KWH = CAPACITY_KJ / 3600
POLL = timedelta(minutes=5)
CHARGE_KW = 7.4
WEATHER_CELLS = 2  # cells each side of home: drive midpoints stay within 0.2 degrees
FORECAST_DAYS = 3
TRUTH = {"c0": 10.0, "c_aero": 0.0011, "c_heat": 12.0}  # kWh/100 km = c0 + c_aero*(v+h)^2 + c_heat*heat
T_BASE = 18.0
NOISE_KWH_100KM = 0.6


@dataclass(frozen=True)
class DayWeather:
    temp: float
    wind: float
    wind_from: float

    def at(self, hour: int) -> tuple[float, float]:
        """Temperature and wind speed in a given UTC hour, rounded as the weather records store them."""
        temp = round(self.temp + 3 * math.sin((hour - 9) / 24 * 2 * math.pi), 1)
        return temp, round(self.wind * (0.8 + 0.4 * math.sin(hour / 5)), 1)

    def hourly(self, day: str) -> dict:
        hours = [self.at(h) for h in range(24)]
        return {
            "time": [f"{day}T{h:02d}:00" for h in range(24)],
            "temperature_2m": [t for t, _ in hours],
            "wind_speed_10m": [w for _, w in hours],
            "wind_direction_10m": [round(self.wind_from, 1)] * 24,
            "wind_gusts_10m": [round(self.wind * 1.6, 1)] * 24,
        }


def true_consumption(speed: float, headwind: float, temp: float) -> float:
    heat = max(0.0, T_BASE - temp) / speed
    return TRUTH["c0"] + TRUTH["c_aero"] * (speed + headwind) ** 2 + TRUTH["c_heat"] * heat


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Car:
    def __init__(self, start: datetime):
        self.out: dict[str, list] = {
            "snapshots": [],
            "trips": [],
            "weather": [],
            "forecast": [],
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

    def drive(self, start: datetime, to: tuple[float, float], km: float, weather, rng) -> datetime:
        speed = rng.uniform(35, 70)
        end = start + timedelta(minutes=km / speed * 60)
        temp, wind, wind_from = weather(start + (end - start) / 2)  # the hour the model will look up
        headwind = headwind_kph(wind, wind_from, bearing_deg(self.pos, to)) if self.pos != to else 0.0
        kwh_per_km = (true_consumption(speed, headwind, temp) + rng.gauss(0, NOISE_KWH_100KM)) / 100
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

    def charge(self, start: datetime, temp: float, limit: float) -> datetime:
        t = start
        while self.soc < limit:
            self.report(t, ignition_on=False, charging=True, temp=temp)
            t += timedelta(minutes=15)
            self.soc = min(limit, self.soc + CHARGE_KW * 0.25 / CAPACITY_KWH * 100)
        self.report(t, ignition_on=False, charging=False, temp=temp)
        return t


def cells() -> list[dict]:
    return [
        {"lat": round(FAKE_HOME[0] + i / 10, 1), "lon": round(FAKE_HOME[1] + j / 10, 1)}
        for i in range(-WEATHER_CELLS, WEATHER_CELLS + 1)
        for j in range(-WEATHER_CELLS, WEATHER_CELLS + 1)
    ]


def write_weather(out: dict, midnight: datetime, weather: DayWeather) -> None:
    """Open-Meteo-shaped hourly weather for every 0.1 degree cell around the fake home, as the weather
    command would have cached it."""
    day = midnight.date().isoformat()
    for cell in cells():
        record = {
            "fetched_at": midnight.isoformat(),
            "endpoint": "open-meteo",
            "key": {**cell, "date": day},
            "http_status": 200,
            "body": {"hourly": weather.hourly(day)},
        }
        out["weather"].append((midnight, record))


def write_forecast(out: dict, first_midnight: datetime, days: list[DayWeather]) -> None:
    """One forecast record for the home cell covering the days after the simulation."""
    hourly: dict[str, list] = {}
    for n, weather in enumerate(days):
        for key, values in weather.hourly((first_midnight + timedelta(days=n)).date().isoformat()).items():
            hourly.setdefault(key, []).extend(values)
    record = {
        "fetched_at": first_midnight.isoformat(),
        "endpoint": "open-meteo-forecast",
        "key": {"lat": round(FAKE_HOME[0], 1), "lon": round(FAKE_HOME[1], 1)},
        "http_status": 200,
        "body": {"hourly": hourly},
    }
    out["forecast"].append((first_midnight, record))


def write_fuel_prices(raw_dir: Path, start: datetime, days: int) -> None:
    """Weekly pump prices in the shape of the EU Oil Bulletin record, near late-2026 levels (demo values)."""
    weeks = []
    monday = start - timedelta(days=start.weekday())
    for n in range(days // 7 + 2):
        wobble = 0.03 * math.sin(n / 2)
        huf_per_eur = 367.0
        hu_petrol, hu_diesel = 1.75 + wobble, 1.93 + wobble
        weeks.append(
            {
                "week": (monday + timedelta(weeks=n)).date().isoformat(),
                "at_petrol_eur": 1.77 + wobble,
                "at_diesel_eur": 2.13 + wobble,
                "hu_petrol_eur": hu_petrol,
                "hu_diesel_eur": hu_diesel,
                "huf_per_eur": huf_per_eur,
                "hu_petrol_huf": hu_petrol * huf_per_eur,
                "hu_diesel_huf": hu_diesel * huf_per_eur,
            }
        )
    fetched = start + timedelta(days=days)
    append_record(
        raw_dir, "fuel", {"fetched_at": fetched.isoformat(), "source": "demo", "weeks": weeks}, fetched
    )


def generate(raw_dir: Path, start: datetime, days: int, seed: int = 7) -> list[dict]:
    """Write fake raw files; return the true drives (start, end, distance_km) to test the pipeline with."""
    rng = random.Random(seed)
    climate = [
        DayWeather(4 + 8 * math.sin(d / 6) + rng.uniform(-3, 3), rng.uniform(5, 35), rng.uniform(0, 360))
        for d in range(days + FORECAST_DAYS)
    ]

    def weather(ts: datetime) -> tuple[float, float, float]:
        """Temperature, wind and direction at the hour nearest ts, exactly as the model will see them."""
        day = min((ts - start).days, len(climate) - 1)
        hours = (ts - (start + timedelta(days=day))).total_seconds() / 3600
        temp, wind = climate[day].at(min(23, round(hours)))
        return temp, wind, climate[day].wind_from

    car = Car(start)
    truth: list[dict] = []
    busy_until = start  # the car can't leave before the last charge or drive has finished
    for day in range(days):
        midnight = start + timedelta(days=day)
        write_weather(car.out, midnight, climate[day])
        t = max(midnight + timedelta(hours=7, minutes=rng.randint(0, 90)), busy_until + timedelta(minutes=10))
        day_trips = []
        for _ in range(rng.choice([1, 1, 2])):
            offset = rng.choice(DESTINATIONS)
            place = (FAKE_HOME[0] + offset[0], FAKE_HOME[1] + offset[1])
            for target in (place, FAKE_HOME):
                km = round(rng.uniform(3, 35), 1)
                end = car.drive(t, target, km, weather, rng)
                truth.append({"start": t.isoformat(), "end": end.isoformat(), "distance_km": km})
                day_trips.append((t, end))
                t = end + timedelta(hours=rng.uniform(0.5, 8))
        if car.soc < rng.uniform(25, 60):  # plug in when it feels low, not at a fixed level
            limit = rng.choice([80, 80, 90, 100])
            busy_until = car.charge(t + timedelta(minutes=10), weather(t)[0], limit=limit)
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
    write_weather(car.out, start + timedelta(days=days), climate[days])  # drives running past midnight
    write_forecast(car.out, start + timedelta(days=days), climate[days:])
    for kind, records in car.out.items():
        append_records(raw_dir, kind, records)
    write_fuel_prices(raw_dir, start, days)
    return truth
