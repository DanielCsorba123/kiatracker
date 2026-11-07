"""Physics from the car's specifications: a model that works before any drive has been measured.

It is a reference (scored in the backtest like the baselines) and a prior: the fitted model is pulled toward
these values while data is scarce, and the data takes over as it grows.
"""

from dataclasses import dataclass

G = 9.81
AIR_DENSITY = 1.225  # kg/m³ at 15 °C, sea level
J_PER_KWH = 3.6e6
KM = 1000.0


@dataclass(frozen=True)
class CarSpecs:
    mass_kg: float  # with driver
    drag_coefficient: float
    frontal_area_m2: float
    rolling_resistance: float
    drivetrain_efficiency: float  # battery to wheels
    auxiliary_kw: float  # electronics, pumps, lights
    heating_kw_per_degree: float  # below 18 °C; a guess the data must correct
    typical_speed_kph: float = 60.0  # for folding the auxiliary load into the base term


# Kia EV3 Long Range. Drag coefficient from Kia's published figure (about 0.26-0.27); frontal area
# estimated from the body (about 1.85 m wide, 1.56 m tall, ~85 % fill); tyre and drivetrain values
# typical for the class.
EV3 = CarSpecs(
    mass_kg=1950,
    drag_coefficient=0.265,
    frontal_area_m2=2.45,
    rolling_resistance=0.009,
    drivetrain_efficiency=0.90,
    auxiliary_kw=0.4,
    heating_kw_per_degree=0.15,
)


def prior_coefficients(car: CarSpecs) -> dict[str, float]:
    """The model's coefficients (kWh/100 km form) implied by the specs."""
    per_100km = 100 * KM / car.drivetrain_efficiency / J_PER_KWH  # newtons -> kWh per 100 km at the battery
    rolling = car.rolling_resistance * car.mass_kg * G * per_100km
    auxiliary = car.auxiliary_kw * 100 / car.typical_speed_kph
    # drag force = 1/2 rho Cd A v², with v in m/s = (km/h) / 3.6
    aero = 0.5 * AIR_DENSITY * car.drag_coefficient * car.frontal_area_m2 / 3.6**2 * per_100km
    heat = car.heating_kw_per_degree * 100  # kW per °C x (100 km / v) hours
    return {"c0": rolling + auxiliary, "aero": aero, "heat": heat}
