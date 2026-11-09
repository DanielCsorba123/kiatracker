"""The car's specifications and measured real-world consumption: a model that works before any drive.

It is a reference (scored in the backtest like the baselines) and a prior: the fitted model is pulled toward
these values while data is scarce, and the data takes over as it grows.

Two kinds of coefficients:
- physics from the data sheet: air drag (drag coefficient, frontal area), climbing and regeneration (mass);
- calibrated to independent real-world measurements: the rolling base, the time-based load, heating and the
  cold penalty, solved so that the model reproduces EV Database's city and highway consumption in mild and
  cold weather. EV Database's mild city figure is also the best case any prediction is allowed to reach.
"""

from dataclasses import dataclass

import numpy as np

G = 9.81
AIR_DENSITY = 1.225  # kg/m³ at 15 °C, sea level
J_PER_KWH = 3.6e6
KM = 1000.0
T_BASE = 18.0  # °C below which heating and the cold penalty start (as in features.py)


@dataclass(frozen=True)
class Benchmark:
    """A measured real-world consumption at the battery, kWh per 100 km."""

    label: str
    speed_kph: float
    temp_c: float
    kwh_per_100km: float


@dataclass(frozen=True)
class CarSpecs:
    name: str
    mass_kg: float  # with driver
    drag_coefficient: float
    frontal_area_m2: float
    drivetrain_efficiency: float  # battery to wheels
    nominal_kwh: float  # what the car reports as battery capacity
    usable_kwh: float  # what 0-100 % on the dashboard spans
    cooling_kw_per_degree: float  # above 24 °C (air conditioning); not in the benchmarks, a guess
    benchmarks: tuple[Benchmark, ...]
    benchmark_source: str
    regen_efficiency: float = 0.6  # share of the height energy a descent puts back in the battery

    @property
    def best_kwh_per_100km(self) -> float:
        """The lowest consumption ever predicted on the flat: the best measured real-world case."""
        return min(b.kwh_per_100km for b in self.benchmarks)

    @property
    def best_range_km(self) -> float:
        return self.usable_kwh / self.best_kwh_per_100km * 100


# Kia EV3 Long Range (81.4 kWh gross, 78.0 kWh usable). Drag coefficient from Kia's published figure (about
# 0.26-0.27); frontal area estimated from the body (about 1.85 m wide, 1.56 m tall, ~85 % fill). Real-world
# consumption from EV Database: "mild" is 23 °C without air conditioning, "cold" is -10 °C with heating,
# highway is a constant 110 km/h; city speed isn't stated, 30 km/h average is assumed. City mild (11.6) is
# the best case: 670 km on a full battery, far above what most real driving achieves.
EV3 = CarSpecs(
    name="Kia EV3 Long Range",
    mass_kg=1950,
    drag_coefficient=0.265,
    frontal_area_m2=2.45,
    drivetrain_efficiency=0.90,
    nominal_kwh=81.4,
    usable_kwh=78.0,
    cooling_kw_per_degree=0.12,
    benchmarks=(
        Benchmark("city, mild", 30, 23, 11.6),
        Benchmark("city, cold", 30, -10, 17.5),
        Benchmark("highway, mild", 110, 23, 18.6),
        Benchmark("highway, cold", 110, -10, 24.0),
    ),
    benchmark_source="https://ev-database.org/car/2212/Kia-EV3-Long-Range",
)


def usable_kwh(reported_kwh: float | None, car: CarSpecs = EV3) -> float:
    """Energy behind 0-100 % on the dashboard, from the capacity the car reports (its gross size)."""
    return (reported_kwh or car.nominal_kwh) * car.usable_kwh / car.nominal_kwh


def density_ratio(temp_c: float) -> float:
    return 288.15 / (273.15 + temp_c)


def physics_coefficients(car: CarSpecs) -> dict[str, float]:
    """Drag, climbing and regeneration straight from the data sheet."""
    per_100km = 100 * KM / car.drivetrain_efficiency / J_PER_KWH  # newtons -> kWh per 100 km at the battery
    # drag force = 1/2 rho Cd A v², with v in m/s = (km/h) / 3.6
    aero = 0.5 * AIR_DENSITY * car.drag_coefficient * car.frontal_area_m2 / 3.6**2 * per_100km
    lift = car.mass_kg * G / J_PER_KWH  # kWh to raise the car one metre
    return {
        "aero": aero,
        "climb": lift / car.drivetrain_efficiency,  # kWh per metre climbed, at the battery
        "regen": lift * car.regen_efficiency,  # kWh per metre descended, back into the battery
    }


def prior_coefficients(car: CarSpecs) -> dict[str, float]:
    """The model's coefficients (kWh/100 km form): physics plus the four terms that reproduce the benchmarks.

    With drag known, each benchmark gives one linear equation in the rolling base c0, the time-based load
    (kW·100, per hour), heating (kW·100 per °C, per hour) and the cold penalty (kWh/100 km per °C, per km):
        consumption − drag = c0 + time/v + heat·cold°/v + cold·cold°,   cold° = max(0, 18 − T)
    """
    physics = physics_coefficients(car)
    rows, targets = [], []
    for b in car.benchmarks:
        cold = max(0.0, T_BASE - b.temp_c)
        rows.append([1.0, 1.0 / b.speed_kph, cold / b.speed_kph, cold])
        targets.append(b.kwh_per_100km - physics["aero"] * b.speed_kph**2 * density_ratio(b.temp_c))
    c0, time, heat, cold = np.linalg.lstsq(np.array(rows), np.array(targets), rcond=None)[0]
    return {
        "c0": float(c0),
        "aero": physics["aero"],
        "heat": max(float(heat), 0.0),
        "cold": max(float(cold), 0.0),
        "cool": car.cooling_kw_per_degree * 100,
        "time": max(float(time), 0.0),
        "climb": physics["climb"],
        "regen": physics["regen"],
    }
