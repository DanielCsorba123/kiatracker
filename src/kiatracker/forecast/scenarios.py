"""What-if range: which model to trust, and range across a grid of temperature and wind."""

import duckdb
import pandas as pd

from kiatracker.forecast.model import NotEnoughData, RangeModel
from kiatracker.forecast.outlook import range_interval
from kiatracker.forecast.train import PRIOR_COEF, train

# Until the car's own model predicts better, scenarios use physics from the EV3's specifications.
# The dashboard says which one it shows.
PRIOR = RangeModel(
    coef=PRIOR_COEF,
    residual_q10=-1.5,
    residual_q90=1.5,
    n_drives=0,
    trained_at="car specs",
)


def choose_model(con: duckdb.DuckDBPyConnection) -> tuple[RangeModel, str]:
    """The trained model if its backtest beats both the average and the car-spec physics, else the specs."""
    try:
        trained = train(con)
    except NotEnoughData:
        return PRIOR, "prior"
    scores = trained.backtest
    if scores and scores["model"]["mae"] < min(
        scores["mean"]["mae"], scores.get("specs", {}).get("mae", 1e9)
    ):
        return trained.model, "trained"
    return PRIOR, "prior"


def range_grid(
    model: RangeModel,
    capacity_kwh: float,
    speed_kph: float,
    temps: list[float],
    winds: list[float],
    soc: float = 100,
) -> pd.DataFrame:
    """Expected range on `soc` % for every temperature and wind speed, at one average speed."""
    rows = [
        {"temp_c": t, "wind_kph": w, "range_km": range_interval(model, soc, capacity_kwh, speed_kph, t, w)[1]}
        for t in temps
        for w in winds
    ]
    return pd.DataFrame(rows, columns=["temp_c", "wind_kph", "range_km"])
