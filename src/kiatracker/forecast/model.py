"""Physics-informed consumption model: kWh/100 km = c0 + aero·(v + headwind)² + heat·max(0, 18 − T)/v.

Three interpretable coefficients fitted by distance-weighted least squares, so it works with tens of drives,
extrapolates sensibly to weather it hasn't seen, and explains itself. A coefficient that comes out negative
(a physically impossible "cold saves energy") is dropped and the rest refitted.
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from kiatracker.forecast.features import T_BASE, physics

FEATURES = ("aero", "heat")
MIN_DRIVES = 15
QUANTILES = (0.1, 0.9)


class NotEnoughData(Exception):
    def __init__(self, needed: int):
        super().__init__(f"need {needed} more drives of 5 km or more with weather")
        self.needed = needed


@dataclass(frozen=True)
class RangeModel:
    coef: dict[str, float]  # c0 plus one per feature
    residual_q10: float  # actual − predicted, kWh/100 km, from out-of-sample predictions when available
    residual_q90: float
    n_drives: int
    trained_at: str

    def predict(self, speed_kph: float, temp_c: float, airspeed_sq: float) -> float:
        x = physics(speed_kph, temp_c, airspeed_sq)
        return self.coef["c0"] + sum(self.coef[f] * x[f] for f in FEATURES)

    def interval(self, speed_kph: float, temp_c: float, airspeed_sq: float) -> tuple[float, float, float]:
        mid = self.predict(speed_kph, temp_c, airspeed_sq)
        return mid + self.residual_q10, mid, mid + self.residual_q90

    def explain(self, speed_kph: float = 50) -> list[str]:
        v = speed_kph
        return [
            f"Base: {self.coef['c0']:.1f} kWh/100 km for rolling resistance, drivetrain and electronics.",
            f"Air resistance: at {v:.0f} km/h, a 20 km/h headwind adds "
            f"{self.coef['aero'] * ((v + 20) ** 2 - v**2):.1f} kWh/100 km; the same tailwind saves only "
            f"{self.coef['aero'] * (v**2 - (v - 20) ** 2):.1f}, since drag grows with airspeed squared.",
            f"Cold: at {v:.0f} km/h, each °C below {T_BASE:.0f} °C adds {self.coef['heat'] / v:.2f} "
            f"kWh/100 km (heating draws power by the hour, so slow cold trips cost the most).",
        ]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RangeModel":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def fit_coefficients(rows: list[dict], features: tuple[str, ...] = FEATURES) -> dict[str, float]:
    """Distance-weighted least squares with an intercept; negative feature costs are dropped and refitted."""
    active = list(features)
    y = np.array([r["kwh_per_100km"] for r in rows])
    w = np.sqrt(np.array([r["distance_km"] for r in rows]))  # longer drives are measured more precisely
    while True:
        x = np.column_stack([np.ones(len(rows))] + [[r[f] for r in rows] for f in active])
        beta, *_ = np.linalg.lstsq(x * w[:, None], y * w, rcond=None)
        negative = [f for f, b in zip(active, beta[1:], strict=True) if b < 0]
        if not negative:
            coef = {"c0": float(beta[0]), **dict.fromkeys(features, 0.0)}
            coef.update({f: float(b) for f, b in zip(active, beta[1:], strict=True)})
            return coef
        active.remove(min(negative, key=lambda f: beta[1 + active.index(f)]))


def predict_rows(coef: dict[str, float], rows: list[dict]) -> np.ndarray:
    return np.array([coef["c0"] + sum(coef[f] * r[f] for f in FEATURES) for r in rows])


def fit(rows: list[dict], residuals: list[float] | None = None) -> RangeModel:
    """Fit on all rows. Pass out-of-sample residuals (from a backtest) for honest intervals."""
    if len(rows) < MIN_DRIVES:
        raise NotEnoughData(MIN_DRIVES - len(rows))
    coef = fit_coefficients(rows)
    if residuals is None or len(residuals) < 5:
        residuals = list(np.array([r["kwh_per_100km"] for r in rows]) - predict_rows(coef, rows))
    q10, q90 = np.quantile(residuals, QUANTILES)
    return RangeModel(
        coef, float(q10), float(q90), len(rows), datetime.now(UTC).isoformat(timespec="seconds")
    )
