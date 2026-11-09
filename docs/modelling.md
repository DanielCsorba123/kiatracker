# Modelling

How consumption is measured, modelled, evaluated and used for range and route predictions. The decisions
behind it: [ADR 0006](decisions/0006-physics-informed-model.md),
[0007](decisions/0007-specs-prior-and-backtest.md), [0009](decisions/0009-per-stretch-features.md) and
[0010](decisions/0010-route-comparison.md). For a hands-on version, run
[`notebooks/model_walkthrough.ipynb`](../notebooks/model_walkthrough.ipynb).

## 1. The measurement

Energy of a drive = (SOC at start − SOC at end) / 100 × usable capacity (78.0 kWh: the car reports its gross
81.4 kWh, but 0–100 % on the dashboard spans the usable part). SOC comes in 0.5 % steps,
so a single drive's energy is uncertain by about ±0.4 kWh: ±4 kWh/100 km on a 10 km drive, ±0.4 on a 100 km
one. Hence: consumption only for drives of 5 km or more, distance-weighted fitting, and the reading-noise
correction for long trips below. Drives with an unseen period or impossible energy are excluded
([ADR 0004](decisions/0004-data-quality-guardrails.md)).

## 2. The model

```
kWh/100 km = c0                                          rolling resistance and drivetrain losses
           + c_aero  · mean[(v + h)² · ρ(T)/ρ15]         air drag on airspeed; ρ(T)/ρ15 = 288.15 / (273.15 + T)
           + c_heat  · mean[max(0, 18 − T) / v]          heating power × hours per km
           + c_cold  · mean[max(0, 18 − T)]              a cold battery, tyres and drivetrain, per km
           + c_cool  · mean[max(0, T − 24) / v]          air-conditioning power × hours per km
           + c_time  · mean[1 / v]                       electronics, pumps and stop-and-go losses per hour
           + c_climb · metres climbed per 100 km
           − c_regen · metres descended per 100 km
```

Heating, cooling and the time-based load are power drawn per hour, so per km they grow as the average speed
falls. The time-based term matters most in town: a low average speed means frequent stops, and each
acceleration loses energy that regeneration doesn't fully return. Without it, slow summer driving would look
nearly free (a 900 km range at 40 km/h), which no EV achieves.

Means are distance-weighted over the drive's stretches, each with its own speed `v` (scaled by the road
factor), headwind `h` and temperature `T`. Squaring per stretch matters: out and back into a 30 km/h wind has
a mean headwind of zero but costs ((v+w)² + (v−w)²)/2 = v² + w².

**Fit:** distance-weighted least squares with all coefficients ≥ 0 and `c_regen ≤ c_climb`, solved exactly by
fitting every subset of free coefficients (2⁸ − 1 = 255 small least-squares problems) and keeping the best
feasible one.

**Prior** (`forecast/specs.py`): drag, climbing and regeneration come from the data sheet (Cd 0.265, frontal
area 2.45 m², 1,950 kg, η 0.90, 60 % regeneration). The rolling base, time-based load, heating and cold
penalty are **calibrated to measured real-world consumption**: EV Database's figures for the EV3 Long Range
(city and highway at 110 km/h, mild 23 °C without A/C and cold −10 °C with heating; city assumed 30 km/h),
solved as four linear equations once drag is known. Air conditioning (0.12 kW/°C above 24 °C) isn't in the
benchmarks and stays a guess.

| | c0 | c_aero | c_heat | c_cold | c_cool | c_time | c_climb | c_regen |
|---|---|---|---|---|---|---|---|---|
| specs | ≈ 6.2 | ≈ 0.00095 | ≈ 2.6 | ≈ 0.12 | 12 | ≈ 137 | ≈ 0.0059 kWh/m | ≈ 0.0032 kWh/m |

| Benchmark (EV Database) | measured | model | range on 78 kWh |
|---|---|---|---|
| city, mild | 11.6 | 11.6 | 672 km |
| city, cold | 17.5 | 17.5 | 446 km |
| highway 110, mild | 18.6 | 18.6 | 419 km |
| highway 110, cold | 24.0 | 24.0 | 325 km |

The benchmarks show that most of the cold penalty is per km (about +5.4 to +5.9 kWh/100 km at −10 °C, town or
motorway), not heating power per hour: a cold battery, tyres and drivetrain are simply less efficient. Hence
the per-km cold term next to the per-hour heating term.

**Best-case cap:** the mild city figure (11.6 kWh/100 km, 672 km) is the best real-world case for the car,
so no prediction on flat ground goes below it, including the optimistic end of an interval. Climbing and
descending are added on top, so a downhill route can still use less.

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

Range = usable energy (78 kWh × charge %) ÷ predicted kWh/100 km, for the typical speed of the owner's drives and each day's
forecast temperature and wind. Without a route, wind averages over all directions: airspeed² = v² + w²/2.

## 5. Route comparison (Routes page, `kiatracker route`)

1. Geocode the places (Nominatim, or "lat, lon" typed directly).
2. OSRM: the fastest route (by typical road speeds, no live traffic), its alternatives, and one route through
   each line of via points. A via point is passed exactly: a town name is its centre, so motorway routes are
   chosen with interchanges ("Knoten Prater" for the A23 through Vienna) or coordinates. Each route lists its
   main roads, so what it really uses is visible.
3. Cut each route into ~1 km pieces from OSRM's per-edge distances and durations; apply the speed cap and pace.
4. For each piece: departure + time so far → the forecast hour for its 0.1° cell (one Open-Meteo request
   covers up to 50 cells); headwind along its bearing; climb and descent from the terrain tiles.
5. Price each piece with the model; sum by cause.
6. Monte Carlo, 1,000 draws, the same draws for every route:
   - the model's coefficients: one of 60 refits on resampled drives (a bootstrap) per draw, or ±20 % around
     the specs when no fit is used, so the odds include how unsure the model itself is;
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
