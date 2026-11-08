# Modelling

How consumption is measured, modelled, evaluated and used for range and route predictions. The decisions
behind it: [ADR 0006](decisions/0006-physics-informed-model.md),
[0007](decisions/0007-specs-prior-and-backtest.md), [0009](decisions/0009-per-stretch-features.md) and
[0010](decisions/0010-route-comparison.md). For a hands-on version, run
[`notebooks/model_walkthrough.ipynb`](../notebooks/model_walkthrough.ipynb).

## 1. The measurement

Energy of a drive = (SOC at start − SOC at end) / 100 × battery capacity (81.4 kWh). SOC comes in 0.5 % steps,
so a single drive's energy is uncertain by about ±0.4 kWh: ±4 kWh/100 km on a 10 km drive, ±0.4 on a 100 km
one. Hence: consumption only for drives of 5 km or more, distance-weighted fitting, and the reading-noise
correction for long trips below. Drives with an unseen period or impossible energy are excluded
([ADR 0004](decisions/0004-data-quality-guardrails.md)).

## 2. The model

```
kWh/100 km = c0                                          rolling resistance, drivetrain, electronics
           + c_aero  · mean[(v + h)² · ρ(T)/ρ15]         air drag on airspeed; ρ(T)/ρ15 = 288.15 / (273.15 + T)
           + c_heat  · mean[max(0, 18 − T) / v]          heating power × hours per km
           + c_climb · metres climbed per 100 km
           − c_regen · metres descended per 100 km
```

Means are distance-weighted over the drive's stretches, each with its own speed `v` (scaled by the road
factor), headwind `h` and temperature `T`. Squaring per stretch matters: out and back into a 30 km/h wind has
a mean headwind of zero but costs ((v+w)² + (v−w)²)/2 = v² + w².

**Fit:** distance-weighted least squares with all coefficients ≥ 0 and `c_regen ≤ c_climb`, solved exactly by
fitting every subset of free coefficients (2⁵ − 1 = 31 small least-squares problems) and keeping the best
feasible one.

**Prior:** the car's specifications give each coefficient
(`forecast/specs.py`; mass 1,950 kg, Cd 0.265, A 2.45 m², Crr 0.009, η 0.90, 0.4 kW auxiliaries, 0.15 kW/°C
heating, 60 % regeneration):

| | c0 | c_aero | c_heat | c_climb | c_regen |
|---|---|---|---|---|---|
| specs | ≈ 6.0 | ≈ 0.00095 | 15 | ≈ 0.0059 kWh/m | ≈ 0.0032 kWh/m |

The fit is pulled toward these values by `strength` pseudo-drives per coefficient (ridge regression toward a
prior, each penalty row scaled by the feature's mean magnitude so the strength means the same for every
coefficient). A coefficient whose feature is always zero keeps its prior.

## 3. Evaluation

- **Time-ordered backtest** (`forecast/evaluate.py`): drives sorted by time, split into 6 blocks; block k is
  predicted from blocks 0…k−1 (expanding window, 5 folds), never from the future.
- **References:** the mean of earlier drives; a straight line in temperature; the specs model with nothing
  learned.
- **Strength selection:** the backtest runs for each strength in (0, 1, 3, 10, 30, 100); the one with the
  lowest MAE is used for the final fit on all drives.
- **Which model is shown:** the fitted model only if its MAE beats both the mean and the specs model; else the
  specs model.
- **Intervals:** the 10th and 90th percentile of the out-of-sample errors. The walkthrough notebook checks
  calibration: percentiles from the first half of the backtest cover 81 % of the second half's drives on demo
  data (target 80 %).
- **Known truth:** the simulator (`synthetic.py`) drives with fixed coefficients (`TRUTH`); a test checks the
  fit recovers them within 15 %. On a simulated year (seasons, road trips, hills) the fit lands within a few
  per cent of the truth, and the backtest MAE is about 1.0 kWh/100 km, against 2.2 for the specs model, 2.9
  for the temperature line and 3.3 for the mean.

## 4. Range outlook (Range page, `kiatracker forecast`)

Range = usable energy ÷ predicted kWh/100 km, for the typical speed of the owner's drives and each day's
forecast temperature and wind. Without a route, wind averages over all directions: airspeed² = v² + w²/2.

## 5. Route comparison (Routes page, `kiatracker route`)

1. Geocode the places (Nominatim, or "lat, lon" typed directly).
2. OSRM: the fastest route, its alternatives, and one route through each line of via places.
3. Cut each route into ~1 km pieces from OSRM's per-edge distances and durations; apply the speed cap and pace.
4. For each piece: departure + time so far → the forecast hour for its 0.1° cell (one Open-Meteo request
   covers up to 50 cells); headwind along its bearing; climb and descent from the terrain tiles.
5. Price each piece with the model; sum by cause.
6. Monte Carlo, 1,000 draws, the same draws for every route:
   - forecast temperature + N(0, 1.5 °C);
   - wind speed × lognormal(0, 0.25), wind direction + N(0, 20°);
   - speed × N(1, 0.04);
   - model error: N(centre, σ) × km/100, where σ is the residual spread with the battery-reading noise of short
     training drives taken out: σ² = σ²_residual − (100 × 0.4 kWh / median training km)², keeping at least
     40 % of σ_residual.
7. Report: median kWh and the 10–90 % range, arrival charge, the chance of arriving above 10 %, the energy by
   cause, and for each route against the cheapest: the extra kWh, the main cause and what offsets it, and on
   how many simulated days the cheaper route really is cheaper.

## 6. Limits and next steps

- OSRM speeds are free-flow, without live traffic or the driver's habits (the pace lever covers part).
- The model has no term for cabin settings, pre-conditioning while plugged in, tyre pressure or payload; these
  end up in the residual spread.
- With tens of drives the coefficients are uncertain; the pull toward the specs fades by itself as the backtest
  stops rewarding it. A residual learner (gradient boosting on what the physics misses) is planned at ~150
  drives and must beat physics alone in the same backtest to be kept.
