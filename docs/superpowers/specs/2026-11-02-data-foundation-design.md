# Data foundation: design

Date: 2026-11-02. Status: approved in advance by the owner ("start developing the first things"); review after the fact.

## 1. Purpose

A personal Kia EV3 tracker that records how the car is used and charged and, later, predicts real range from weather and route. It is also a public portfolio project for AI / data engineering roles, so the public repo must run end to end without any personal data.

This spec covers only the first sub-project, the **data foundation**: collect, store and model the car's data so that every later feature (dashboard, range model, route model, Raspberry Pi deployment) reads from one clean set of tables.

Later sub-projects, each with its own spec: dashboard, range forecast, route forecast, Raspberry Pi move, optional extras (LLM questions over the data, alerts, SolarEdge and wallbox data).

## 2. What we know about the data (from the probe and logger spikes)

Source: official Pleos Vehicle Data API (EU Data Act), private-user key, `Brand: kia`.

- Snapshot endpoints (`/batteries`, `/powertrains`, `/locations`, `/driving`, `/status`) return only the latest reading, each group with one UTC `timestamp` of when the car sent it. Polling every 5 minutes while driving produced a new reading of every group, location included, at each poll. State of charge comes in 0.5 % steps. Odometer has 0.1 km resolution.
- `batteryCapacity` is in kJ (293040 = 81.4 kWh). Tire pressure 255 means invalid. Altitude reads 0. Outside temperature is absent.
- Trip history (`/driving/data`, 7 days per request) gives only `triggerStartTime` and `tripLength` (ms) for the EV3; its arrays are a constant driver-assist flag (`isla`). `/speed`, `/powertrains/data` and `/status/data` are not supported for the EV3 according to Pleos' compatibility table. Trips arrive with a delay; at least ~9 days were available.
- No rate limit is documented. 5 endpoints every 5 minutes (~1,400 calls/day) has worked so far.

Consequence: distance, energy, route and charging must be derived from regular snapshot polling. The trip list adds precise start times and durations.

## 3. Requirements

1. **Collect**: one command polls all snapshot groups and stores each reading whose car timestamp is new; every 6 hours it also stores the trip list. Runs from Windows Task Scheduler now and a Linux timer / container on the Pi later; scheduling is never inside the code.
2. **Raw is the source of truth**: raw API responses are appended untouched (except compacting the useless `isla` arrays) to monthly JSONL files and never edited. The spike logger's files in `data/raw/` use the same format and are imported as-is.
3. **Rebuildable model**: one command rebuilds every derived table from raw data, deterministically. No incremental state to corrupt.
4. **Derived tables**: readings per group, drives, charging sessions, charge-to-charge windows, API trips with fragments merged, and weather per drive.
5. **Privacy**: credentials only in `.env`; `data/` gitignored; derived tables label places by zone (`home`, `other`) instead of coordinates where shown publicly; a secret scanner runs before commits.
6. **Fake data**: a generator writes realistic raw files in the same format, so the whole pipeline, tests and later the dashboard run with no account.
7. **Pi-ready**: works on Windows and Linux (ARM), configured by environment variables, with a Dockerfile.

Out of scope here: dashboard, forecasting models, SolarEdge and wallbox integration, the Pi itself.

## 4. Architecture

```
Pleos API ──collect──▶ data/raw/*.jsonl (bronze, append-only)
Open-Meteo ─weather──▶ data/raw/weather-*.jsonl
                              │
                           build (full rebuild)
                              ▼
               data/kiatracker.duckdb
               ├─ silver: readings_battery, readings_driving, readings_location, readings_status, api_trips
               └─ gold:   drives, charging_sessions, charge_windows, drive_weather
```

Python 3.13 package `kiatracker` in `src/`, managed with uv. Dependencies: `duckdb`, `httpx`; dev: `pytest`, `respx`, `ruff`.

| Module | Responsibility |
|---|---|
| `config.py` | Settings from environment / `.env` (credentials, data dir, home zone, battery fallback) |
| `pleos.py` | API client: token, auto re-login on expiry, typed errors, the endpoints |
| `raw.py` | Append and read raw JSONL records; isla compaction |
| `collect.py` | One poll: dedupe by car timestamp, periodic trip sync, collector state file |
| `weather.py` | Open-Meteo hourly weather for drives, cached in raw files |
| `build/silver.py` | Parse raw records into typed reading tables |
| `build/gold.py` | Derive drives, charging sessions, charge windows, merged trips, drive weather |
| `privacy.py` | Zone labelling (haversine to home), coordinate rounding |
| `synthetic.py` | Fake raw data generator |
| `cli.py` | `collect`, `build`, `weather`, `demo`, `stats` |

## 5. Derivation rules

- **Readings**: one row per raw record with HTTP 200, keyed by (group, car timestamp); duplicates from overlapping files are dropped.
- **Drives**: ordered driving readings; a drive starts at the first reading where ignition is on or the odometer rose since the previous reading, and ends at the last reading before ignition is off and the odometer is unchanged. Distance = odometer end − start. SOC start/end = nearest battery reading at or before start / at or after end. Energy kWh = ΔSOC/100 × capacity (capacity from `batteryCapacity` kJ / 3600). Consumption kWh/100 km only when distance ≥ 5 km (0.5 % SOC ≈ 0.4 kWh is too coarse below that). Start and end zones from location. API trips overlapping a drive refine its start time and duration.
- **API trips**: fragments with a gap ≤ 60 s are merged.
- **Charging sessions**: consecutive battery readings with `charging = true`; SOC start/end, kWh added (battery side), duration, average kW, zone.
- **Charge windows**: from the end of one charging session to the start of the next: km driven, SOC used, kWh, kWh/100 km, number of drives.
- **Drive weather**: Open-Meteo hourly temperature, wind speed, wind direction and gusts at the drive's midpoint time and position (archive API for > 5 days ago, forecast API with `past_days` otherwise); headwind is left to the range-model sub-project.

## 6. Error handling

- HTTP or network failure on one group: write an `errors` raw record, continue with the other groups; the poll still exits 0 so the scheduler keeps going.
- Token expiry (codes 40003 / 40004): re-login once and retry.
- 429: stop this poll, record it; next scheduled poll tries again.
- Build tolerates unknown fields, missing groups and invalid sentinels (255 → NULL).

## 7. Testing

pytest with HTTP mocked (respx). Unit tests for dedupe, isla compaction, each derivation rule on small hand-made reading sequences, and zone labelling. An end-to-end test generates fake raw data and runs `build`, checking drives and sessions match what the generator produced. CI (GitHub Actions) runs ruff, pytest and gitleaks.

## 8. Migration from the spike

The scheduled task `kiatracker-logger` keeps running the spike until `kiatracker collect` is verified on the real account; then the task's action is switched to the new command. Both write the same raw format into the same folder, and the collector reuses the spike's state so nothing is stored twice.
