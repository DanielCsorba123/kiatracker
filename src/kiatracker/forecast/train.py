"""Train, evaluate and describe the range model from the database; shared by the CLI and the dashboard."""

from dataclasses import dataclass, replace
from statistics import median

import duckdb

from kiatracker.forecast.evaluate import backtest
from kiatracker.forecast.features import drive_features
from kiatracker.forecast.model import RangeModel, bootstrap, fit
from kiatracker.forecast.specs import EV3, prior_coefficients

MODEL_FILE = "models/range.json"
DEFAULT_SPEED = 50.0
PRIOR_COEF = prior_coefficients(EV3)
STRENGTHS = (0.0, 1.0, 3.0, 10.0, 30.0, 100.0)  # in average drives' worth of belief in the specs


@dataclass(frozen=True)
class Trained:
    model: RangeModel
    backtest: dict | None
    typical_speed_kph: float


def train(con: duckdb.DuckDBPyConnection) -> Trained:
    """Fit on every usable drive, pulled toward the car-spec physics by the strength that predicts later
    drives best in the backtest. Intervals come from that backtest's out-of-sample residuals.

    Raises NotEnoughData when there are too few drives.
    """
    rows = drive_features(con)
    results = {s: backtest(rows, prior=PRIOR_COEF, strength=s) for s in STRENGTHS}
    scored = {s: r for s, r in results.items() if r}
    strength = min(scored, key=lambda s: scored[s]["model"]["mae"]) if scored else STRENGTHS[-1]
    result = scored.get(strength)
    model = fit(rows, result["residuals"] if result else None, prior=PRIOR_COEF, strength=strength)
    model = replace(model, coef_draws=bootstrap(rows, PRIOR_COEF, strength))
    return Trained(model, result, median(r["speed_kph"] for r in rows) if rows else DEFAULT_SPEED)


def car_state(con: duckdb.DuckDBPyConnection) -> tuple[float | None, float | None]:
    """Latest charge % and battery capacity in kWh."""
    row = con.execute(
        "select soc, capacity_kwh from readings_battery where soc is not null order by ts desc limit 1"
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def weather_cell(
    con: duckdb.DuckDBPyConnection, home: tuple[float, float] | None
) -> tuple[float, float] | None:
    """The ~10 km grid cell to fetch the forecast for: home if configured, else the car's last position."""
    if home:
        return round(home[0], 1), round(home[1], 1)
    row = con.execute(
        "select lat, lon from readings_location where lat is not null order by ts desc limit 1"
    ).fetchone()
    return (round(row[0], 1), round(row[1], 1)) if row else None
