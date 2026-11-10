"""Fake raw data in the exact format the collector writes, so the public repo runs without a car or account.

A simulated EV3 lives at a fictional home through the seasons: weekday commutes and errands, longer weekend
outings, a motorway road trip about once a month with fast-charging stops, and overnight charging at home. The
land around home is hilly (`fake_elevation`). Energy is charged step by step (one 5-minute poll at a time)
with that step's hour of weather, the headwind along the drive and the step's climb or descent, following the
range model's physics with known true coefficients (TRUTH). Fitting the model must recover them. Readings
follow how the real car reports: every poll while driving, once when the ignition goes off, and every 15 (AC)
or 5 (DC) minutes while charging.
"""

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kiatracker.geo import bearing_deg, headwind_kph
from kiatracker.privacy import haversine_km
from kiatracker.raw import append_record, append_records

FAKE_HOME = (47.0, 18.0)  # a field in rural Hungary, not anyone's home
WORK = (0.13, 0.17)  # offsets in degrees from home
OUTINGS = [(0.32, -0.22), (-0.28, 0.36), (0.2, 0.42), (-0.35, -0.3)]
ROAD_TRIPS = [(1.2, -1.6), (-0.4, 2.1), (1.5, 0.9)]  # 150-230 km away
CAPACITY_KJ = 293040.0
CAPACITY_KWH = 78.0  # usable: what 0-100 % spans (the car reports the gross 81.4 kWh as capacity)
POLL = timedelta(minutes=5)
AC_KW = 11.0
DC_KW = 120.0
FORECAST_DAYS = 7  # as many days as the real forecast fetches
# true physics: kWh/100 km = c0 + c_aero*(v+h)^2*density + (c_heat*cold + c_cool*hot + c_time) / v,
# plus c_climb kWh per metre climbed and c_regen kWh back per metre descended
TRUTH = {  # a little thirstier than EV Database's EV3, as a real car with winter tyres would be
    "c0": 6.5,
    "c_aero": 0.00098,
    "c_heat": 3.0,
    "c_cold": 0.13,  # per km and °C below 18: a cold battery, tyres and drivetrain
    "c_cool": 13.0,
    "c_time": 140.0,  # 1.4 kW: electronics, pumps and stop-and-go losses, per hour on the road
    "c_climb": 0.0062,
    "c_regen": 0.0030,
}
T_BASE = 18.0
T_COOL = 24.0
NOISE_KWH_100KM = 1.1  # traffic, driving style, tyre pressure, how full the car is
EXTRA_CHANCE = 0.1  # now and then a drive costs clearly more: a passenger, a jam, a roof box, no pre-heating
ROAD_FACTOR = 1.25  # roads are longer than the straight line (motorway stages)


@dataclass(frozen=True)
class DayWeather:
    temp: float
    wind: float
    wind_from: float

    def at(self, hour: int) -> tuple[float, float]:
        """Temperature and wind speed in a given UTC hour, rounded as the weather records store them."""
        temp = round(self.temp + 3.5 * math.sin((hour - 9) / 24 * 2 * math.pi), 1)
        return temp, round(self.wind * (0.8 + 0.4 * math.sin(hour / 5)), 1)

    def hourly(self, day: str) -> dict:
        hours = [self.at(h) for h in range(24)]
        return {
            "time": [f"{day}T{h:02d}:00" for h in range(24)],
            "temperature_2m": [t for t, _ in hours],
            "wind_speed_10m": [w for _, w in hours],
            "wind_direction_10m": [round(self.wind_from, 1)] * 24,
            "wind_gusts_10m": [round(self.wind * 1.6, 1)] * 24,
            "cloud_cover": [self.cloud] * 24,
            "precipitation_probability": [max(0.0, min(80.0, self.cloud - 35))] * 24,
        }

    @property
    def cloud(self) -> float:
        """Cloud cover %: windier and colder days are greyer; deterministic, so the demo stays repeatable."""
        swing = 15 * math.sin(math.radians(self.wind_from))
        return float(round(min(90.0, max(10.0, 30 + 2.2 * self.wind - 1.2 * self.temp + swing))))


def fake_elevation(lat: float, lon: float) -> float:
    """Rolling hills around the fake home: about ±150 m over 15-25 km, never below 100 m."""
    x, y = (lat - FAKE_HOME[0]) * 111.0, (lon - FAKE_HOME[1]) * 76.0  # km north and east
    return 260 + 90 * math.sin(x / 6.0) * math.cos(y / 8.0) + 60 * math.sin((x + y) / 15.0)


class FakeTerrain:
    """Stands in for the SRTM tiles when building demo data."""

    def elevation(self, lat: float, lon: float) -> float:
        return fake_elevation(lat, lon)


def true_consumption(speed: float, headwind: float, temp: float) -> float:
    per_hour = TRUTH["c_heat"] * max(0.0, T_BASE - temp) + TRUTH["c_cool"] * max(0.0, temp - T_COOL)
    density = 288.15 / (273.15 + temp)  # cold air is denser, as in the model's features
    return (
        TRUTH["c0"]
        + TRUTH["c_aero"] * (speed + headwind) ** 2 * density
        + (per_hour + TRUTH["c_time"]) / speed
        + TRUTH["c_cold"] * max(0.0, T_BASE - temp)
    )


def around_home(rng: random.Random, km_low: float, km_high: float) -> tuple[float, float]:
    """A random place `km_low`-`km_high` km from home in any direction, as an offset in degrees."""
    bearing, km = rng.uniform(0, 2 * math.pi), rng.uniform(km_low, km_high)
    return km * math.cos(bearing) / 111.0, km * math.sin(bearing) / 76.0


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def at_offset(offset: tuple[float, float]) -> tuple[float, float]:
    return FAKE_HOME[0] + offset[0], FAKE_HOME[1] + offset[1]


class Car:
    def __init__(self, start: datetime):
        self.out: dict[str, list] = {"snapshots": [], "trips": [], "weather": [], "forecast": []}
        self.cells: dict[str, set] = {}  # UTC day -> 0.1 degree cells the car was in
        self.odo, self.soc, self.pos = 10000.0, 80.0, FAKE_HOME
        self.report(start, ignition_on=False, charging=False, temp=5.0)

    def report(self, ts: datetime, ignition_on: bool, charging: bool, temp: float, speed: float = 0.0):
        day = ts.astimezone(UTC).date().isoformat()
        self.cells.setdefault(day, set()).add((round(self.pos[0], 1), round(self.pos[1], 1)))
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
                "windshield": {"defrost": "on" if ignition_on and temp < 1 else "off"},
                "steeringWheelHeat": "on" if ignition_on and temp < 5 else "off",
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
        self, start: datetime, to: tuple[float, float], km: float, weather, rng, speed: float
    ) -> datetime:
        """Drive in a straight line to `to`, `km` by the odometer, charging energy one poll step at a time."""
        end = start + timedelta(hours=km / speed)
        noise = rng.gauss(0, NOISE_KWH_100KM) + (rng.uniform(1, 4) if rng.random() < EXTRA_CHANCE else 0.0)
        bearing = bearing_deg(self.pos, to) if self.pos != to else None
        origin, odo0 = self.pos, self.odo
        previous, done_before = start, 0.0
        t = start + POLL
        while True:
            step_end = min(t, end)
            done = (step_end - start) / (end - start)
            temp, wind, wind_from = weather(previous + (step_end - previous) / 2)
            head = headwind_kph(wind, wind_from, bearing) if bearing is not None else 0.0
            pos = (origin[0] + (to[0] - origin[0]) * done, origin[1] + (to[1] - origin[1]) * done)
            rise = fake_elevation(*pos) - fake_elevation(*self.pos)
            kwh = km * (done - done_before) * (true_consumption(speed, head, temp) + noise) / 100
            kwh += TRUTH["c_climb"] * max(rise, 0.0) - TRUTH["c_regen"] * max(-rise, 0.0)
            self.soc -= kwh / CAPACITY_KWH * 100
            self.odo, self.pos = odo0 + km * done, pos
            previous, done_before = step_end, done
            if done >= 1:
                self.report(end, ignition_on=False, charging=False, temp=temp)
                return end
            self.report(t, ignition_on=True, charging=False, temp=temp, speed=speed)
            t += POLL
            if end - t < timedelta(minutes=1):  # the car never sends two readings within the same second
                t = end

    def charge(self, start: datetime, temp: float, limit: float, kw: float = AC_KW) -> datetime:
        """AC at home (a report every 15 min), or DC on the road (every 5 min, slowing above 80 %)."""
        t, step = start, timedelta(minutes=15 if kw <= AC_KW else 5)
        while self.soc < limit:
            self.report(t, ignition_on=False, charging=True, temp=temp)
            power = kw if kw <= AC_KW or self.soc < 80 else kw * 0.35
            t += step
            self.soc = min(limit, self.soc + power * step.total_seconds() / 3600 / CAPACITY_KWH * 100)
        self.report(t, ignition_on=False, charging=False, temp=temp)
        return t


def neighbours(cell: tuple[float, float]) -> set[tuple[float, float]]:
    return {(round(cell[0] + i / 10, 1), round(cell[1] + j / 10, 1)) for i in (-1, 0, 1) for j in (-1, 0, 1)}


def write_weather(out: dict, midnight: datetime, weather: DayWeather, cells: set) -> None:
    """Open-Meteo-shaped hourly weather for the cells the car used, as the refresh would have cached it."""
    day = midnight.date().isoformat()
    for lat, lon in sorted(cells):
        record = {
            "fetched_at": midnight.isoformat(),
            "endpoint": "open-meteo",
            "key": {"lat": lat, "lon": lon, "date": day},
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
        wobble = 0.03 * math.sin(n / 2) + 0.05 * math.sin(n / 9)
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


def make_climate(start: datetime, days: int, rng: random.Random) -> list[DayWeather]:
    """Seasons by calendar date (about 0 °C mid-January, 22 °C mid-July), multi-day fronts, and a prevailing
    north-westerly that turns round now and then."""
    climate, front = [], 0.0
    for d in range(days):
        date = (start + timedelta(days=d)).date()
        season = 11 - 11 * math.cos(2 * math.pi * (date.timetuple().tm_yday - 15) / 365)
        front = 0.75 * front + rng.gauss(0, 2.2)
        windy = 1.25 if date.month in (11, 12, 1, 2, 3) else 1.0
        wind_from = rng.gauss(315, 40) % 360 if rng.random() < 0.6 else rng.uniform(0, 360)
        climate.append(DayWeather(season + front, rng.uniform(4, 28) * windy, wind_from))
    return climate


def plan_day(day: datetime, rng: random.Random, road_trip: bool) -> list[tuple]:
    """Legs for one day: (destination, km by road, speed, minutes parked afterwards, kind)."""

    def leg(offset, speed_range, stay, kind, km=None):
        place = at_offset(offset)
        return place, km, rng.uniform(*speed_range), stay, kind

    if road_trip:
        return [leg(rng.choice(ROAD_TRIPS), (105, 125), 0, "road trip")]
    if day.weekday() < 5:
        legs = [leg(WORK, (45, 95), rng.uniform(450, 540), "commute")]
        if rng.random() < 0.35:
            legs.append(leg(around_home(rng, 2, 9), (25, 60), rng.uniform(15, 60), "errand"))
        legs.append(leg((0, 0), (45, 95), 0, "commute"))
        return legs
    legs = []
    if rng.random() < 0.6:
        legs += [
            leg(
                rng.choice(OUTINGS) if rng.random() < 0.5 else around_home(rng, 15, 50),
                (50, 110),
                rng.uniform(90, 300),
                "outing",
            ),
            leg((0, 0), (50, 110), 0, "outing"),
        ]
    if rng.random() < 0.5:
        legs += [
            leg(around_home(rng, 2, 12), (25, 60), rng.uniform(20, 90), "errand"),
            leg((0, 0), (25, 60), 0, "errand"),
        ]
    return legs


def generate(raw_dir: Path, start: datetime, days: int, seed: int = 7) -> list[dict]:
    """Write fake raw files; return the true drives (start, end, distance_km) to test the pipeline with."""
    rng = random.Random(seed)
    # the forecast days get their own stream, so their number never reshuffles the simulated history
    climate = make_climate(start, days, rng) + make_climate(
        start + timedelta(days=days), FORECAST_DAYS, random.Random(seed + 1)
    )

    def weather(ts: datetime) -> tuple[float, float, float]:
        """Temperature, wind and direction at the hour nearest ts, exactly as the model will see them."""
        day = min(max((ts - start).days, 0), len(climate) - 1)
        hours = (ts - (start + timedelta(days=day))).total_seconds() / 3600
        temp, wind = climate[day].at(min(23, round(hours)))
        return temp, wind, climate[day].wind_from

    car = Car(start)
    truth: list[dict] = []
    trips_by_day: dict[int, list] = {}

    def drive(t, to, km, speed):
        end = car.drive(t, to, km, weather, rng, speed)
        truth.append({"start": t.isoformat(), "end": end.isoformat(), "distance_km": km})
        trips_by_day.setdefault((t - start).days, []).append((t, end))
        return end

    def road_km(a, b, factor=None):
        """Odometer km: the straight line times how winding the road is (and any detour) that day."""
        return round(haversine_km(a, b) * (factor or rng.uniform(1.12, 1.5)) + rng.uniform(0.3, 2), 1)

    def long_drive(t, to, speed):
        """Motorway in stages of ~100 km, with a fast charge whenever the battery gets low."""
        origin, total = car.pos, haversine_km(car.pos, to)
        stages = max(1, round(total * ROAD_FACTOR / 100))
        for n in range(1, stages + 1):
            target = (
                origin[0] + (to[0] - origin[0]) * n / stages,
                origin[1] + (to[1] - origin[1]) * n / stages,
            )
            t = drive(t, target, road_km(car.pos, target, ROAD_FACTOR), speed * rng.uniform(0.95, 1.03))
            if n < stages:
                t += timedelta(minutes=rng.uniform(8, 20))
                if car.soc < 60 and rng.random() < 0.8:  # top up during the break
                    t = car.charge(t, weather(t)[0], limit=rng.choice([75, 80, 85]), kw=DC_KW)
                    t += timedelta(minutes=rng.uniform(2, 10))
        return t

    busy_until = start
    away_until = -1  # last day of a road trip
    for day in range(days):
        midnight = start + timedelta(days=day)
        t = max(
            midnight + timedelta(hours=6, minutes=rng.randint(0, 100)), busy_until + timedelta(minutes=10)
        )
        trip_day = midnight.weekday() == 5 and (day // 7) % 4 == 2 and day + 1 < days
        if day <= away_until:  # coming back from the road trip
            if car.soc < 55:
                t = car.charge(t, weather(t)[0], limit=90, kw=AC_KW)  # destination charger overnight
                t += timedelta(minutes=rng.uniform(10, 40))
            t = long_drive(t + timedelta(hours=rng.uniform(2, 4)), FAKE_HOME, rng.uniform(105, 125))
        else:
            if trip_day and car.soc < 90:
                t = car.charge(t, weather(t)[0], limit=100, kw=AC_KW) + timedelta(minutes=rng.uniform(10, 40))
            for place, km, speed, stay, kind in plan_day(midnight, rng, trip_day):
                if kind == "road trip":
                    t = long_drive(t, place, speed)
                    away_until = day + 1
                    break
                stay = max(stay, rng.uniform(4, 25))  # a real car always stops between trips
                t = drive(t, place, km or road_km(car.pos, place), speed) + timedelta(minutes=stay)
        at_home = haversine_km(car.pos, FAKE_HOME) < 0.3
        if at_home and car.soc < rng.uniform(35, 65):  # plug in when it feels low, not at a fixed level
            evening = max(t, midnight + timedelta(hours=rng.uniform(18, 22)))
            busy_until = car.charge(evening, weather(evening)[0], limit=rng.choice([80, 80, 90, 100]))
        else:
            busy_until = t
        fetched = midnight + timedelta(days=1)
        trips = [
            {
                "triggerStartTime": s.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "tripLength": int((e - s).total_seconds() * 1000),
                "isla": {},
            }
            for s, e in trips_by_day.get(day, [])
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
    home_block = neighbours((round(FAKE_HOME[0], 1), round(FAKE_HOME[1], 1)))
    for day in range(days + 1):
        midnight = start + timedelta(days=day)
        used = car.cells.get(midnight.date().isoformat(), set())
        used |= car.cells.get((midnight - timedelta(days=1)).date().isoformat(), set())
        cells = set(home_block).union(*(neighbours(c) for c in used))
        write_weather(car.out, midnight, climate[day], cells)
    write_forecast(car.out, start + timedelta(days=days), climate[days:])
    for kind, records in car.out.items():
        append_records(raw_dir, kind, records)
    write_fuel_prices(raw_dir, start, days)
    return truth
