# Data model

Three layers ([ADR 0002](decisions/0002-raw-files-as-source-of-truth.md)): raw JSONL records as received
(bronze), typed readings (silver) and derived tables (gold), all rebuilt by `kiatracker build` into one DuckDB
file. All timestamps are UTC; the car's own timestamp (when it sent the reading) is used wherever there is one.

> The database is private: `readings_location` and the coordinate columns of `drives` hold exact positions.
> Nothing that leaves the database through the dashboard, features or logs carries them.

## Bronze: `data/raw/`

Monthly, append-only JSONL files; one JSON object per line.

| File | One record per | Fields |
|---|---|---|
| `snapshots-YYYY-MM.jsonl` | new reading of one snapshot group | `fetched_at`, `endpoint` (`batteries`, `powertrains`, `locations`, `driving`, `status`), `http_status`, `body` (the API response, including the car's `timestamp`) |
| `trips-YYYY-MM.jsonl` | trip-list sync (every 6 h) | `fetched_at`, `query` (date range), `http_status`, `body`, `isla_compacted` (a constant driver-assist array replaced by its length and distinct values) |
| `errors-YYYY-MM.jsonl` | failed call | `fetched_at`, `endpoint`, `http_status` or `exception`, `body` |
| `weather-YYYY-MM.jsonl` | Open-Meteo day for one cell | `fetched_at`, `endpoint`, `key` (`lat`, `lon` rounded to 0.1°, UTC `date`), `http_status`, `body.hourly` (temperature, wind speed, direction, gusts) |
| `forecast-YYYY-MM.jsonl` | home-cell forecast fetch | as above, 3-day hourly forecast |
| `fuel-YYYY-MM.jsonl` | weekly fuel price download | weeks of Austrian and Hungarian petrol and diesel prices |

`logger_state.json` holds the collector's state: the last car timestamp per group and the last trip sync.

## Silver: readings

| Table | Columns | Notes |
|---|---|---|
| `readings_battery` | `ts`, `soc` %, `plugin`, `status`, `charging`, `capacity_kwh`, `target_soc_ac`, `target_soc_dc`, `remain_min` | SOC in 0.5 % steps; capacity from the API's kJ (293,040 kJ = 81.4 kWh) |
| `readings_driving` | `ts`, `ignition_on`, `sleep_mode`, `odometer_km`, `parked` | odometer 0.1 km |
| `readings_location` | `ts`, `lat`, `lon`, `heading`, `speed_kph` | **private** |
| `readings_status` | `ts`, `climate_on`, `climate_mode`, `defrost`, `steering_heat`, `seat_heat_any` | no heater power or cabin temperature from the API |
| `readings_range` | `ts`, `range_km` | the car's own range estimate |
| `api_trips` | `start`, `end` | the API's trip list; fragments ≤ 60 s apart merged |

Readings are deduplicated by (group, car timestamp).

## Gold: derived tables

### `drives`

| Column | Meaning |
|---|---|
| `drive_id` | sequential |
| `start_ts`, `end_ts`, `mid_ts` | refined by API trips where they overlap |
| `odo_start`, `odo_end`, `distance_km` | odometer |
| `soc_start`, `soc_end` | nearest battery readings at or before start / at or after end |
| `energy_kwh` | ΔSOC × capacity; null unless `quality = 'ok'` |
| `kwh_per_100km` | only for drives of 5 km or more |
| `start_lat`, `start_lon`, `end_lat`, `end_lon`, `mid_lat`, `mid_lon` | **private** |
| `start_zone`, `end_zone` | `home` / `other` (null without a configured home) |
| `api_trips`, `location_points` | evidence behind the drive |
| `in_progress` | the car is still driving |
| `quality` | `ok`, `gap` (unseen period before the drive: energy unknown) or `implausible` (charge rose, or outside 6–45 kWh/100 km); see [ADR 0004](decisions/0004-data-quality-guardrails.md) |

### `drive_segments`

One row per stretch between consecutive GPS readings of an `ok` drive
([ADR 0009](decisions/0009-per-stretch-features.md)). No coordinates.

| Column | Meaning |
|---|---|
| `drive_id`, `seq` | the drive and the stretch's order in it |
| `start_ts`, `end_ts` | the two readings' times |
| `km`, `speed_kph` | straight-line distance and speed (scaled to the odometer in the features) |
| `bearing_deg` | direction of travel |
| `temp_c`, `wind_kph`, `wind_dir_deg` | that hour's weather in the stretch's 0.1° cell |
| `headwind_kph` | wind component against the direction of travel (negative = tailwind) |
| `climb_m`, `descent_m` | from SRTM terrain at the two ends |

### Other tables

| Table | Columns | Meaning |
|---|---|---|
| `charging_sessions` | `session_id`, `start_ts`, `end_ts`, `soc_start`, `soc_end`, `energy_kwh`, `hours`, `avg_kw`, `zone`, `in_progress` | a run of charging readings; energy on the battery side |
| `charge_windows` | `window_id`, `start_ts`, `end_ts`, `soc_used`, `energy_kwh`, `distance_km`, `drives`, `kwh_per_100km` | from one charge to the next: everything driven on one charge, a cross-check that needs no per-drive accuracy |
| `drive_weather` | `drive_id`, `temp_c`, `wind_kph`, `wind_dir_deg`, `gust_kph` | hourly weather at the drive's midpoint (the fallback when stretches lack weather) |
| `forecast_hourly` | `ts`, `temp_c`, `wind_kph`, `wind_dir_deg` | latest forecast for the home cell |
| `fuel_prices` | `week`, `at_petrol_eur`, `at_diesel_eur`, `hu_petrol_eur`, `hu_diesel_eur`, `huf_per_eur`, `hu_petrol_huf`, `hu_diesel_huf` | for the cost comparison against a petrol car |

## Feature rows (in memory)

`forecast.features.drive_features(con)` returns one dict per finished drive of 5 km or more with energy and
weather. No coordinates.

| Key | Meaning |
|---|---|
| `drive_id`, `start_ts`, `distance_km`, `speed_kph`, `wind_kph` | from the drive |
| `temp_c`, `headwind_kph` | distance-weighted over stretches (or the drive's midpoint weather) |
| `aero` | mean of (v + headwind)² × ρ(T)/ρ₁₅ over stretches |
| `heat` | mean of max(0, 18 − T) / v |
| `climb`, `regen` | metres up, minus metres down, per 100 km |
| `kwh_per_100km` | the target |

## Model file: `data/models/range.json`

```json
{
  "coef": {"c0": 6.1, "aero": 0.00086, "heat": 15.7, "climb": 0.0061, "regen": 0.0027},
  "residual_q10": -1.6,
  "residual_q90": 1.8,
  "n_drives": 15,
  "trained_at": "2026-11-08T10:25:00+00:00",
  "prior_strength": 100.0,
  "median_km": 13.7
}
```

Coefficients are in kWh/100 km per unit of the matching feature (`c0` in kWh/100 km); the residual quantiles
are out-of-sample errors from the backtest when it ran. Files saved before a field existed still load (missing
coefficients count as zero, `median_km` defaults to 15).

## Terrain: `data/dem/`

SRTM 1-arc-second tiles, `N47E018.hgt` style names, 3,601 × 3,601 big-endian int16 heights in metres
(−32,768 = void), downloaded gzipped from the AWS open terrain bucket. About 25 MB each.
