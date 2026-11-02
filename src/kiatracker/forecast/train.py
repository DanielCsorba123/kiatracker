"""Train, evaluate and describe the range model from the database; shared by the CLI and the dashboard."""

from dataclasses import dataclass
from statistics import median

import duckdb

from kiatracker.forecast.evaluate import backtest
from kiatracker.forecast.features import drive_features
from kiatracker.forecast.model import RangeModel, fit

MODEL_FILE = "models/range.json"
DEFAULT_SPEED = 50.0


@dataclass(frozen=True)
class Trained:
    model: RangeModel
    backtest: dict | None
    typical_speed_kph: float


def train(con: duckdb.DuckDBPyConnection) -> Trained:
    """Fit on every usable drive; intervals come from the backtest's out-of-sample residuals.

    Raises NotEnoughData when there are too few drives.
    """
    rows = drive_features(con)
    result = backtest(rows)
    model = fit(rows, result["residuals"] if result else None)
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
