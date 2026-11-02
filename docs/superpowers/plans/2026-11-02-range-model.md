# Range Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fit a physics-informed consumption model on the owner's drives and forecast range from current charge and weather, in the CLI and the dashboard.

**Architecture:** `kiatracker.forecast` (features → model → evaluate → outlook), numpy only; dashboard page on top.

**Tech Stack:** numpy, DuckDB, httpx (Open-Meteo forecast), Streamlit/Altair for the page.

**Spec:** `docs/superpowers/specs/2026-11-02-range-model-design.md`

## Global Constraints

- Heating base temperature `T_BASE = 18.0` °C; minimum drives to fit `MIN_DRIVES = 15`; interval quantiles 0.1 / 0.9.
- Feature columns: `drive_id, start_ts, distance_km, speed_kph, temp_c, wind_kph, headwind_kph, aero, heat, kwh_per_100km`.
- No coordinates in feature output, saved model or dashboard frames.
- Demo truth: `c0 = 10.0, c_aero = 0.0011, c_heat = 12.0`.

## Review Focus

1. Drive with no GPS points inside and identical start/end → headwind 0, no crash.
2. Fewer than 15 usable drives → clear "need N more drives" message in CLI and dashboard.
3. A fitted coefficient negative (e.g. no cold drives yet) → feature dropped and refit, never a negative cost.
4. SOC or capacity missing → range is None, not an exception.
5. Forecast weather missing or stale → outlook shows "now" only from the latest drive weather or says it needs `kiatracker forecast`.

---

### Task 1: Demo data follows the spec's physics
**Files:** `src/kiatracker/synthetic.py`, `tests/test_end_to_end.py`
- Daily wind direction; hourly temp/wind helper shared by weather records and consumption; consumption = truth formula at the drive's mid hour with (v + headwind)² from the drive's bearing; writes `forecast` records for the 3 days after the last simulated day.
- [ ] Existing end-to-end tests stay green; new test: forecast records exist.

### Task 2: Features
**Files:** `src/kiatracker/forecast/__init__.py`, `features.py`, `tests/forecast/test_features.py`
- `bearing_deg(a, b) -> float`, `headwind_kph(wind_kph, wind_from_deg, bearing) -> float`, `path_headwind(points, wind_kph, wind_from_deg) -> float`, `drive_features(con) -> list[dict]` (columns per Global Constraints).
- [ ] Tests: bearing N/E; headwind against/behind/cross; path weighting; round trip with no points → 0 (Focus 1); `drive_features` on demo DB has no coordinate keys.

### Task 3: Model
**Files:** `src/kiatracker/forecast/model.py`, `tests/forecast/test_model.py`
- `RangeModel` dataclass (`coef: dict[str, float]`, `residual_q10`, `residual_q90`, `n_drives`, `trained_at`); `fit(rows) -> RangeModel` (non-negative refit, raises `NotEnoughData(needed)`); `predict(speed_kph, temp_c, aero) -> float`; `interval(...) -> (lo, mid, hi)`; `explain() -> list[str]`; `save(path)` / `load(path)`.
- [ ] Tests: recovers demo truth within 15 %; negative coefficient dropped (Focus 3); fewer than 15 rows raises with needed count (Focus 2); save/load round trip.

### Task 4: Evaluation
**Files:** `src/kiatracker/forecast/evaluate.py`, `tests/forecast/test_evaluate.py`
- `backtest(rows, folds=5) -> dict` with `mae`, `rmse` per `model`, `mean`, `temperature_only`, and `predictions` (actual, predicted, start_ts); residuals feed the interval.
- [ ] Tests: model beats both baselines on demo; no fold trains on later drives.

### Task 5: Outlook and CLI
**Files:** `src/kiatracker/forecast/outlook.py`, `src/kiatracker/cli.py`, `tests/forecast/test_outlook.py`, `tests/test_cli.py`
- `range_km(soc, capacity_kwh, kwh_per_100km) -> float | None`; `fetch_forecast(cell, raw_dir, http, now)`; `daily_outlook(raw_dir, model, soc, capacity, speed) -> list[dict]` (`day, temp_c, wind_kph, range_lo, range_km, range_hi`); CLI `train` and `forecast`.
- [ ] Tests: range arithmetic and None inputs (Focus 4); fetch mocked; outlook days from forecast records; missing forecast → empty list (Focus 5); CLI train on demo prints MAE.

### Task 6: Dashboard Range page
**Files:** `src/kiatracker/dashboard/pages/range.py`, `app.py`, `queries.py`, tests
- Fits the model on the fly from the open database (cached by DB mtime); tiles, outlook chart with interval, what-if sliders, predicted-vs-actual scatter, coefficient explanations.
- [ ] Tests: renders on demo; empty DB and too-few-drives show the needed-count message.

### Task 7: Docs, screenshot, review, merge, push
