# Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `kiatracker` Python package that collects Pleos snapshots into append-only raw files and rebuilds DuckDB tables of readings, drives, charging sessions, charge windows and drive weather from them.

**Architecture:** Raw JSONL (bronze) is the only state; `build` parses it into typed readings (silver) and derives gold tables with plain Python functions, then writes everything to one DuckDB file. API and weather access sit behind small clients so tests mock HTTP.

**Tech Stack:** Python 3.13, uv, httpx, duckdb; pytest, respx, ruff.

**Spec:** `docs/superpowers/specs/2026-11-02-data-foundation-design.md`

## Global Constraints

- Python 3.13; runtime deps only `httpx` and `duckdb`.
- Raw record format (shared with `spikes/pleos_logger.py`): one JSON object per line, `{"fetched_at": iso, "endpoint": name, "http_status": int, "body": payload}`; trips records add `"query"` and `"isla_compacted": true`; files `data/raw/<kind>-YYYY-MM.jsonl`, kinds `snapshots`, `trips`, `errors`, `weather`.
- Collector state file `data/raw/logger_state.json` with keys `last_timestamp` (group → car timestamp), `last_position`, `last_trip_sync` — the spike's file is reused.
- Snapshot groups: `batteries`, `powertrains`, `locations`, `driving`, `status`. Trip sync every 6 h, window = today−6 … today, `zoneId=Europe/Budapest`.
- Capacity kWh = `batteryCapacity` / 3600. Tire value 255 → NULL. Consumption only when distance ≥ 5 km. Trip fragments merged when gap ≤ 60 s.
- Settings from environment or `.env` / `.env.txt` in the working dir: `PLEOS_API_KEY_CLIENT_ID`, `PLEOS_API_KEY_CLIENT_SECRET`, `KIATRACKER_DATA_DIR` (default `data`), `KIATRACKER_HOME_LAT`, `KIATRACKER_HOME_LON`, `KIATRACKER_HOME_RADIUS_KM` (default 0.3).
- Never print VIN or coordinates.

## Review Focus

1. Truncated last line in a raw file (power cut mid-write) → `read_records` skips it; build still succeeds.
2. The same reading in both spike and collector files → one row in silver.
3. Readings with missing odometer / SOC → no crash; derived fields NULL.
4. Drive or charging session still in progress at build time → kept with `in_progress = true`, excluded from window consumption.
5. Token expiry mid-poll → one re-login, poll completes.

---

### Task 1: Scaffold and settings

**Files:** Create `pyproject.toml`, `src/kiatracker/__init__.py`, `src/kiatracker/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (frozen dataclass: `client_id: str | None`, `client_secret: str | None`, `data_dir: Path`, `home: tuple[float, float] | None`, `home_radius_km: float`), properties `raw_dir`, `db_path` (`data_dir/kiatracker.duckdb`); `load_settings(cwd: Path = Path.cwd(), environ: Mapping[str, str] = os.environ) -> Settings` (environment wins over the file).

- [ ] Tests: `test_reads_env_txt_when_no_env`, `test_environment_overrides_file`, `test_home_requires_both_coordinates` (only LAT set → `home is None`), `test_defaults` (`data_dir == cwd/"data"`, radius 0.3).
- [ ] Run, see them fail; implement; run, pass; `uv run ruff check`; commit.

### Task 2: Raw store

**Files:** Create `src/kiatracker/raw.py`, `tests/test_raw.py`

**Interfaces:**
- Produces: `append_record(raw_dir: Path, kind: str, record: dict, now: datetime) -> Path`; `read_records(raw_dir: Path, kind: str) -> Iterator[dict]` (files in name order, skips lines that are not valid JSON); `compact_isla(payload: dict) -> dict` (each `isla` array → `{"len": n, "distinct": sorted unique strings}`).
- [ ] Tests: monthly file name from `now`; round trip; corrupt last line skipped (Review Focus 1); `compact_isla` on a trips payload.
- [ ] Fail → implement → pass → commit.

### Task 3: Pleos client

**Files:** Create `src/kiatracker/pleos.py`, `tests/test_pleos.py`

**Interfaces:**
- Produces: `SNAPSHOT_PATHS: dict[str, str]` (group → path with `{vin}`), `TRIPS_PATH`; `class PleosError(Exception)` with `status`, `code`; `class RateLimited(PleosError)`; `class PleosClient(client_id, client_secret, brand="kia", http: httpx.Client | None = None)` with `login() -> None`, `get(path: str, params: dict | None = None) -> tuple[int, dict]`, `vehicles() -> list[dict]`. Base URL `https://api.pleos.ai`, headers `Brand`, `Authorization: Bearer`.
- [ ] Tests (respx): login sends `clientId`/`clientSecret` and `Brand: kia`; `get` re-logs in once on error code `40003` then succeeds (Review Focus 5); 429 raises `RateLimited`; failed login raises `PleosError`; non-JSON body returned as `{"non_json_body": text}`.
- [ ] Fail → implement → pass → commit.

### Task 4: Collector

**Files:** Create `src/kiatracker/collect.py`, `tests/test_collect.py`

**Interfaces:**
- Consumes: Task 2, Task 3.
- Produces: `PollResult` (dataclass: `new: list[str]`, `errors: list[str]`, `summary: str`); `poll(client: PleosClient, vin: str, raw_dir: Path, now: datetime | None = None) -> PollResult`. Summary line like the spike's, without coordinates.
- [ ] Tests with a fake client object: first poll stores 5 snapshot records + 1 trips record; second poll with same timestamps stores nothing; changed `batteries` timestamp stores only that group; a 500 on one group writes an `errors` record and still stores the others; trip sync skipped within 6 h; existing spike state file is honoured.
- [ ] Fail → implement → pass → commit.

### Task 5: Silver readings

**Files:** Create `src/kiatracker/model.py`, `src/kiatracker/silver.py`, `tests/test_silver.py`

**Interfaces:**
- Produces dataclasses in `model.py` (all with `ts: datetime` UTC): `BatteryReading(ts, soc, plugin, status, charging, capacity_kwh, target_soc_ac, target_soc_dc, remain_min)`, `DrivingReading(ts, ignition_on, sleep_mode, odometer_km, parked)`, `LocationReading(ts, lat, lon, heading, speed_kph)`, `StatusReading(ts, climate_on, climate_mode, defrost, steering_heat, seat_heat_any)`, `RangeReading(ts, range_km)`, `ApiTrip(start, end)`; `Readings` container with one list per type plus `api_trips`.
- `load_readings(raw_dir: Path) -> Readings`: HTTP-200 records only, dedupe per group by car timestamp (Review Focus 2), sorted by ts; `merge_trip_fragments(trips: list[ApiTrip], max_gap_s: float = 60) -> list[ApiTrip]`.
- [ ] Tests: parses the real record shapes from the spike (sanitised fixture); duplicate records across two files → one reading; `"value": "-"` range → None; missing odometer → None (Review Focus 3); fragments 2 s apart merged, 61 s apart kept.
- [ ] Fail → implement → pass → commit.

### Task 6: Gold derivations and zones

**Files:** Create `src/kiatracker/privacy.py`, `src/kiatracker/gold.py`, `tests/test_gold.py`, `tests/test_privacy.py`

**Interfaces:**
- Produces: `haversine_km(a, b) -> float`, `zone_of(lat, lon, home, radius_km) -> str | None` (`"home"`, `"other"`, or None without coordinates/home).
- Dataclasses `Drive(drive_id, start_ts, end_ts, odo_start, odo_end, distance_km, soc_start, soc_end, energy_kwh, kwh_per_100km, start_lat, start_lon, end_lat, end_lon, mid_ts, mid_lat, mid_lon, start_zone, end_zone, api_trips, location_points, in_progress)`, `ChargingSession(session_id, start_ts, end_ts, soc_start, soc_end, energy_kwh, hours, avg_kw, zone, in_progress)`, `ChargeWindow(window_id, start_ts, end_ts, soc_used, energy_kwh, distance_km, drives, kwh_per_100km)`.
- `derive_drives(r: Readings, capacity_kwh: float, home, radius_km) -> list[Drive]`, `derive_charging_sessions(r, capacity_kwh, home, radius_km) -> list[ChargingSession]`, `derive_charge_windows(sessions, drives, capacity_kwh) -> list[ChargeWindow]`.
- Drive rule: a reading is "moving" if ignition is on or its odometer rose > 0.05 km since the previous reading. A drive is a run of moving readings; its start reading is the reading before the run (or the first one), its end reading the first non-moving reading after it (or, if the run ended on an ignition-off odometer jump, that reading). No end reading → `in_progress`. API trips starting inside (start reading ts, end reading ts] set `start_ts`/`end_ts` and `api_trips`. SOC/location = latest reading at or before the start/end reading ts.
- Session rule: run of `charging` readings; `soc_start` = SOC of the reading before the run if it is lower, else of the first; end = first non-charging reading after the run; no end → `in_progress`.
- Window rule: between consecutive finished sessions; drives whose start lies in the window; in-progress drives are excluded (Review Focus 4).
- [ ] Tests: drive from a hand-made 5-minute sequence (distance, soc, energy, consumption, zones); short drive missed by polling (two parked readings, odometer +3 km) still counted; drive < 5 km has NULL consumption; drive still running → `in_progress`; API trip refines start; charging session values and avg kW; session in progress; window totals; zone home / other / None.
- [ ] Fail → implement → pass → commit.

### Task 7: Database build and stats

**Files:** Create `src/kiatracker/db.py`, `tests/test_db.py`

**Interfaces:**
- Consumes: Tasks 5, 6, 8 (`load_weather` result).
- Produces: `build_database(settings: Settings) -> dict[str, int]` (table → row count): writes to a temp file then replaces `db_path`; tables `readings_battery`, `readings_driving`, `readings_location`, `readings_status`, `readings_range`, `api_trips`, `drives`, `charging_sessions`, `charge_windows`, `drive_weather`. Capacity = latest reading's `capacity_kwh`, fallback 81.4. `stats(settings) -> str` text summary without coordinates.
- [ ] Tests: build on a small fixture raw dir creates all tables with expected counts; rebuilding twice gives identical counts; `stats` output contains no fixture coordinate strings.
- [ ] Fail → implement → pass → commit.

### Task 8: Weather

**Files:** Create `src/kiatracker/weather.py`, `tests/test_weather.py`

**Interfaces:**
- Produces: `fetch_weather(drives: list[Drive], raw_dir: Path, http: httpx.Client, today: date) -> int` (number of new fetches): one request per (lat, lon rounded to 0.1, UTC date) not yet in `weather` raw records; archive API (`https://archive-api.open-meteo.com/v1/archive`) if the date is > 5 days before `today`, else forecast API (`https://api.open-meteo.com/v1/forecast`); params `hourly=temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m`, `wind_speed_unit=kmh`, `timezone=UTC`, `start_date`=`end_date`=date. Record `{"fetched_at", "endpoint": "open-meteo", "key": {"lat", "lon", "date"}, "http_status", "body"}`.
- `load_weather(raw_dir) -> dict[tuple[float, float, str], dict]`; `weather_for_drive(drive, weather) -> DriveWeather | None` (`DriveWeather(drive_id, temp_c, wind_kph, wind_dir_deg, gust_kph)` from the hour nearest `mid_ts`).
- [ ] Tests (respx): archive vs forecast choice; cached key not refetched; nearest-hour pick.
- [ ] Fail → implement → pass → commit.

### Task 9: Fake data and end-to-end test

**Files:** Create `src/kiatracker/synthetic.py`, `tests/test_end_to_end.py`

**Interfaces:**
- Produces: `generate(raw_dir: Path, start: datetime, days: int, seed: int = 7) -> list[dict]` (the ground-truth drives: start, end, distance_km): fictional home near 47.5, 19.0, 1–3 drives a day, 5-minute readings in the exact raw format, home charging overnight when SOC < 50 %, trips records.
- [ ] Test: generate 14 days, `build_database`, derived finished drives match ground truth count and distances within 0.2 km; charging sessions ≥ 1, all at `home`.
- [ ] Fail → implement → pass → commit.

### Task 10: CLI, packaging for the Pi, CI, README

**Files:** Create `src/kiatracker/cli.py`, `src/kiatracker/__main__.py`, `Dockerfile`, `deploy/kiatracker-collect.service`, `deploy/kiatracker-collect.timer`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.env.example`, `README.md`, `tests/test_cli.py`

**Interfaces:**
- Produces: console script `kiatracker` with `collect`, `build`, `weather`, `demo [--days N]` (fake data into `<data_dir>/demo`, then build), `stats`; `--data-dir` override; under `pythonw` output goes to `<data_dir>/logs/collect.log`.
- [ ] Test: `demo` then `stats` in a temp dir exits 0 and prints drive count.
- [ ] Verify on the real account: `uv run kiatracker collect`, `build`, `weather`, `stats`.
- [ ] Switch scheduled task `kiatracker-logger` to `.venv\Scripts\pythonw.exe -m kiatracker collect`; confirm next run result 0.
- [ ] Commit.
