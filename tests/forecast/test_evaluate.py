from kiatracker.forecast.evaluate import backtest, time_folds
from kiatracker.forecast.features import drive_features


def test_folds_never_train_on_the_future(demo):
    rows = drive_features(demo)
    folds = list(time_folds(rows, folds=5))
    assert len(folds) == 5
    for train, test in folds:
        assert max(r["start_ts"] for r in train) <= min(r["start_ts"] for r in test)


def test_model_beats_both_baselines_on_demo(demo):
    result = backtest(drive_features(demo))
    assert result["model"]["mae"] < result["temperature_only"]["mae"] < result["mean"]["mae"]
    assert len(result["predictions"]) == len(result["residuals"]) > 50
    p = result["predictions"][0]
    assert set(p) == {"start_ts", "actual", "predicted"}


def test_too_few_drives_gives_no_backtest():
    assert backtest([]) is None
