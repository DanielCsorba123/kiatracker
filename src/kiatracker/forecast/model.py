"""Physics-informed consumption model:
kWh/100 km = c0 + aero·(v + headwind)² + heat·max(0, 18 − T)/v + climb·(m up) − regen·(m down),
with climb and descent in metres per 100 km.

Five interpretable coefficients fitted by distance-weighted least squares, so it works with tens of drives,
extrapolates sensibly to weather it hasn't seen, and explains itself. Every coefficient is kept non-negative:
a negative one (cold "saving" energy, or a negative base load) is physically impossible.
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import chain, combinations
from pathlib import Path

import numpy as np

from kiatracker.forecast.features import T_BASE, physics

FEATURES = ("aero", "heat", "climb", "regen")
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
    prior_strength: float = 0.0  # how strongly the fit was pulled toward the car-spec physics
    median_km: float = 15.0  # typical training drive: tells measurement noise from model error

    def predict(
        self, speed_kph: float, temp_c: float, airspeed_sq: float, climb: float = 0.0, descent: float = 0.0
    ) -> float:
        """kWh/100 km; climb and descent in metres per 100 km (flat by default)."""
        x = physics(speed_kph, temp_c, airspeed_sq) | {"climb": climb, "regen": -descent}
        return self.coef["c0"] + sum(self.coef.get(f, 0.0) * x[f] for f in FEATURES)

    def interval(
        self, speed_kph: float, temp_c: float, airspeed_sq: float, climb: float = 0.0, descent: float = 0.0
    ) -> tuple[float, float, float]:
        mid = self.predict(speed_kph, temp_c, airspeed_sq, climb, descent)
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
            f"Hills: each 100 m climbed costs {self.coef.get('climb', 0.0) * 100:.2f} kWh; each 100 m "
            f"downhill gives back {self.coef.get('regen', 0.0) * 100:.2f} kWh through regenerative braking.",
        ]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RangeModel":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def fit_coefficients(
    rows: list[dict],
    features: tuple[str, ...] = FEATURES,
    prior: dict[str, float] | None = None,
    strength: float = 0.0,
) -> dict[str, float]:
    """Distance-weighted least squares with every coefficient, the intercept included, kept non-negative,
    optionally pulled toward `prior` (ridge regression toward the car-spec physics).

    The pull adds one pseudo-observation per coefficient, worth `strength` average drives, saying
    "this coefficient is the prior". Few drives: the prior dominates; many drives: the data does.
    Non-negativity is exact: fit each subset of free coefficients (the rest held at zero), keep the best.
    """
    names = ("c0", *features)
    y = np.array([r["kwh_per_100km"] for r in rows], dtype=float)
    w = np.sqrt(np.array([r["distance_km"] for r in rows], dtype=float))  # longer drives are measured better
    columns = {"c0": np.ones(len(rows))} | {
        f: np.array([r.get(f, 0.0) for r in rows], dtype=float) for f in features
    }
    # augmented system: data rows, then one penalty row per coefficient
    a_rows = [np.column_stack([columns[n] for n in names]) * w[:, None]]
    b_rows = [y * w]
    if prior is not None and strength > 0:
        pull = np.sqrt(strength * np.mean(w**2))
        for i, n in ((i, n) for i, n in enumerate(names) if n in prior):  # no prior: left free
            scale = max(float(np.mean(np.abs(columns[n]))), 1e-9)  # coefficient units -> kWh/100 km
            row = np.zeros(len(names))
            row[i] = pull * scale
            a_rows.append(row[None, :])
            b_rows.append(np.array([pull * scale * prior[n]]))
    a, b = np.vstack(a_rows), np.concatenate(b_rows)
    best, best_error = dict.fromkeys(names, 0.0), float(np.sum(b**2))
    for free in chain.from_iterable(combinations(range(len(names)), k) for k in range(1, len(names) + 1)):
        beta, *_ = np.linalg.lstsq(a[:, free], b, rcond=None)
        if np.any(beta < 0):
            continue
        error = float(np.sum((b - a[:, free] @ beta) ** 2))
        if error < best_error:
            best = dict.fromkeys(names, 0.0) | {names[i]: float(v) for i, v in zip(free, beta, strict=True)}
            best_error = error
    if prior is not None:
        # no evidence at all (e.g. no terrain data: every climb is 0): keep the specs, not a silent zero
        best |= {f: prior[f] for f in features if f in prior and not np.any(columns[f])}
    return best


def predict_rows(coef: dict[str, float], rows: list[dict]) -> np.ndarray:
    return np.array([coef["c0"] + sum(coef.get(f, 0.0) * r.get(f, 0.0) for f in FEATURES) for r in rows])


def fit(
    rows: list[dict],
    residuals: list[float] | None = None,
    prior: dict[str, float] | None = None,
    strength: float = 0.0,
) -> RangeModel:
    """Fit on all rows. Pass out-of-sample residuals (from a backtest) for honest intervals."""
    if len(rows) < MIN_DRIVES:
        raise NotEnoughData(MIN_DRIVES - len(rows))
    coef = fit_coefficients(rows, prior=prior, strength=strength)
    if residuals is None or len(residuals) < 5:
        residuals = list(np.array([r["kwh_per_100km"] for r in rows]) - predict_rows(coef, rows))
    q10, q90 = np.quantile(residuals, QUANTILES)
    return RangeModel(
        coef,
        float(q10),
        float(q90),
        len(rows),
        datetime.now(UTC).isoformat(timespec="seconds"),
        strength,
        float(np.median([r["distance_km"] for r in rows])),
    )
