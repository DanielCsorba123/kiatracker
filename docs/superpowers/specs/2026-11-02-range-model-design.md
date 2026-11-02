# Weather-aware range model: design

Date: 2026-11-02. Status: started on the owner's go-ahead ("Range model next"); review after the fact.

## 1. Purpose

Predict how far the car will really get from its current charge given the weather, and explain why: how much cold, wind and speed cost. It must work with the little real data there is (days to weeks of drives) and get better as data accumulates. Route-aware forecasting (a specific A→B with elevation) is the next sub-project and reuses this model.

## 2. Model: physics-informed linear regression

Target: consumption in kWh/100 km of finished drives of at least 5 km that have weather.

Features (per drive):

| Feature | Physics | Unit |
|---|---|---|
| 1 | rolling resistance, drivetrain, electronics | – |
| `aero = (v + h)²` | air drag grows with the square of airspeed; v = average speed, h = mean headwind along the path | (km/h)² |
| `heat = max(0, 18 − T) / v` | cabin and battery heating is roughly constant power, so energy per km scales with time per km | °C·h/km |

`kWh/100 km = c0 + c_aero · aero + c_heat · heat`, fitted by least squares with coefficients constrained to be non-negative (refit without a feature whose coefficient comes out negative). Coefficients are reported in plain units ("at 50 km/h each °C below 18 costs …").

Why not gradient boosting: with tens to hundreds of drives a flexible model overfits; this one has three parameters, extrapolates sensibly to unseen weather, and is explainable. The evaluation shows whether it beats simple baselines; a learned residual model can be added once there are enough drives to justify it.

**Headwind along the path.** Meteorological wind direction is where the wind comes *from*. For each segment between consecutive GPS readings inside the drive, headwind = wind speed · cos(wind-from − travel bearing); the drive's value is the distance-weighted mean. Without inner points, the start→end bearing is used; a drive that ends where it started gets 0.

**Unknown route (forecasting).** Averaged over all directions, `(v + w·cos φ)²` = v² + w²/2, so forecasts use `aero = v² + w²/2`: on a round trip wind always costs energy.

## 3. Uncertainty and evaluation

- Time-ordered evaluation: drives sorted by time, expanding window, predict the next fold. Metrics: MAE and RMSE of kWh/100 km for the model and two baselines (mean of training drives; temperature-only linear fit).
- Prediction interval: 10th–90th percentile of out-of-sample residuals (split conformal), applied to consumption, then converted to range.
- Minimum data: 15 qualifying drives to fit; below that, commands and the dashboard say how many more are needed.

## 4. Range forecast

`range_km = soc/100 · capacity_kwh / consumption · 100`, for: now (the current hour's weather), and each of the next three days (daytime 08–20 h average temperature and wind from the Open-Meteo forecast). Speed = the median average speed of the owner's drives (user-adjustable in the dashboard). Range interval from the consumption interval.

Forecast weather comes from Open-Meteo's forecast API for the 0.1° cell of the home location (or, if unset, of the car's latest position), stored as `forecast` raw records. The cell is the same coarse precision already sent for drive weather.

## 5. Components

```
kiatracker.forecast
├─ features.py   drive feature rows from the database (bearing, headwind, speed, temperature)
├─ model.py      RangeModel: fit / predict / interval / explain; save and load as JSON
├─ evaluate.py   time-ordered backtest against baselines
└─ outlook.py    forecast weather fetch + range for now and the next days
```

`numpy` becomes a core dependency (model fitting runs from the CLI on the Pi). CLI: `kiatracker train` (fit, evaluate, save `data/models/range.json`, print metrics and coefficients), `kiatracker forecast` (fetch forecast, print range now and per day). Dashboard: a **Range** page with the outlook, what-if sliders (temperature, wind, speed), predicted vs actual, and the explained coefficients.

Privacy: features use coordinates internally to compute bearings but return only derived numbers; feature frames and the saved model contain no coordinates (tested).

## 6. Demo data

The simulator's consumption follows the same physics with known true coefficients (c0 = 10, c_aero = 0.0011, c_heat = 12) plus noise, using the hourly weather it writes and the real bearing of each simulated drive against a daily wind direction. A test checks that fitting recovers the coefficients, which validates features and fitting end to end. It also writes forecast records so the demo dashboard shows an outlook.

## 7. Testing

Bearing and headwind maths on known geometry; feature rows from a small hand-built database; coefficient recovery on simulated data; non-negativity refit; evaluation folds never train on the future; range arithmetic; forecast fetch mocked; Range page renders on demo, on an empty database, and with too few drives.
