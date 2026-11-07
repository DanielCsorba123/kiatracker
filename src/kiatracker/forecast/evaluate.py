"""Time-ordered backtest: train only on earlier drives, predict the next block, compare with baselines.

References: the training mean and a straight line in temperature (deliberately dumb baselines), and the
car-spec physics with nothing fitted. The fitted model has to beat them to be worth its complexity; its
out-of-sample residuals also give the prediction interval.
"""

from collections.abc import Iterator

import numpy as np

from kiatracker.forecast.model import MIN_DRIVES, fit_coefficients, predict_rows


def time_folds(rows: list[dict], folds: int = 5) -> Iterator[tuple[list[dict], list[dict]]]:
    """Expanding window: block k is predicted from blocks 0..k-1."""
    ordered = sorted(rows, key=lambda r: r["start_ts"])
    blocks = np.array_split(np.arange(len(ordered)), folds + 1)
    for k in range(1, folds + 1):
        train = [ordered[i] for b in blocks[:k] for i in b]
        test = [ordered[i] for i in blocks[k]]
        if len(train) >= MIN_DRIVES and test:
            yield train, test


def _linear_in_temperature(train: list[dict], test: list[dict]) -> np.ndarray:
    x = np.column_stack([np.ones(len(train)), [r["temp_c"] for r in train]])
    beta, *_ = np.linalg.lstsq(x, [r["kwh_per_100km"] for r in train], rcond=None)
    return beta[0] + beta[1] * np.array([r["temp_c"] for r in test])


def _scores(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = actual - predicted
    return {"mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error**2)))}


def backtest(
    rows: list[dict], folds: int = 5, prior: dict[str, float] | None = None, strength: float = 0.0
) -> dict | None:
    actual, model, mean, temperature, specs, predictions = [], [], [], [], [], []
    for train, test in time_folds(rows, folds):
        coef = fit_coefficients(train, prior=prior, strength=strength)
        y = [r["kwh_per_100km"] for r in test]
        predicted = predict_rows(coef, test)
        actual += y
        model += list(predicted)
        mean += [float(np.mean([r["kwh_per_100km"] for r in train]))] * len(test)
        temperature += list(_linear_in_temperature(train, test))
        specs += list(predict_rows(prior, test)) if prior else [float("nan")] * len(test)
        predictions += [
            {"start_ts": r["start_ts"], "actual": a, "predicted": float(p)}
            for r, a, p in zip(test, y, predicted, strict=True)
        ]
    if not actual:
        return None
    a = np.array(actual)
    return {
        "model": _scores(a, np.array(model)),
        "mean": _scores(a, np.array(mean)),
        "temperature_only": _scores(a, np.array(temperature)),
        **({"specs": _scores(a, np.array(specs))} if prior else {}),
        "predictions": predictions,
        "residuals": list(a - np.array(model)),
    }
