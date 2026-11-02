"""Typed readings parsed from raw API records (the silver layer). All timestamps are UTC car times."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class BatteryReading:
    ts: datetime
    soc: float | None
    plugin: str | None
    status: str | None
    charging: bool | None
    capacity_kwh: float | None
    target_soc_ac: int | None
    target_soc_dc: int | None
    remain_min: int | None


@dataclass(frozen=True)
class DrivingReading:
    ts: datetime
    ignition_on: bool | None
    sleep_mode: str | None
    odometer_km: float | None
    parked: bool | None


@dataclass(frozen=True)
class LocationReading:
    ts: datetime
    lat: float | None
    lon: float | None
    heading: float | None
    speed_kph: float | None


@dataclass(frozen=True)
class StatusReading:
    ts: datetime
    climate_on: bool | None
    climate_mode: str | None
    defrost: bool | None
    steering_heat: bool | None
    seat_heat_any: bool | None


@dataclass(frozen=True)
class RangeReading:
    ts: datetime
    range_km: float | None


@dataclass(frozen=True)
class ApiTrip:
    start: datetime
    end: datetime


@dataclass
class Readings:
    battery: list[BatteryReading] = field(default_factory=list)
    driving: list[DrivingReading] = field(default_factory=list)
    location: list[LocationReading] = field(default_factory=list)
    status: list[StatusReading] = field(default_factory=list)
    range: list[RangeReading] = field(default_factory=list)
    api_trips: list[ApiTrip] = field(default_factory=list)
