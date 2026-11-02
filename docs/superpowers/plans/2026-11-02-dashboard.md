# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Streamlit dashboard (overview, drives, charging, costs) over the DuckDB database, with a demo mode that can never read personal data.

**Architecture:** `queries` (SQL → pandas) and `charts` (pandas → Altair) hold all logic and are unit-tested; Streamlit pages are thin. `source` decides personal vs demo database.

**Tech Stack:** Streamlit, Altair, pandas, DuckDB; pytest with `streamlit.testing.v1.AppTest`.

**Spec:** `docs/superpowers/specs/2026-11-02-dashboard-design.md`

## Global Constraints

- Optional extra `dashboard = ["streamlit>=1.40", "altair>=5", "pandas>=2.2"]`; the dev group installs the same.
- No query returns a column named `lat`, `lon`, `*_lat`, `*_lon`, `latitude`, `longitude` or `vin`.
- Local time zone `Europe/Budapest`; database timestamps are naive UTC.
- `KIATRACKER_DEMO=1` forces demo mode.
- Colours: `BLUE = "#2a78d6"`, `ORANGE = "#eb6834"`; consumption only from drives with `kwh_per_100km` not null.

## Review Focus

1. Personal database exists but `KIATRACKER_DEMO=1` → demo data is shown.
2. Empty database (no drives, no sessions) → every page renders with an empty-state message.
3. Date range that contains no drives → tiles show "–", charts are skipped, no exception.
4. All drives below 5 km → average consumption is None, not a division error.
5. Database file missing in personal mode → clear message pointing to `kiatracker build`.

---

### Task 1: Demo weather and wind-dependent consumption

**Files:** Modify `src/kiatracker/synthetic.py`; Test `tests/test_end_to_end.py`
- Generator writes `weather` raw records (`endpoint: open-meteo`, `key {lat, lon, date}`, hourly temperature/wind/direction/gusts) for every 0.1° cell within ±0.3° of `FAKE_HOME` for each simulated day; consumption adds a wind term.
- [ ] Test `test_demo_drives_have_weather`: after build, `drive_weather` rows == finished drives with a mid position.
- [ ] Fail → implement → pass → commit.

### Task 2: Data source

**Files:** Create `src/kiatracker/dashboard/__init__.py`, `src/kiatracker/dashboard/source.py`; Test `tests/dashboard/test_source.py`
- `DataSource` (frozen dataclass: `db_path: Path`, `demo: bool`); `resolve_source(personal_db: Path, demo_requested: bool, environ=os.environ) -> DataSource`; `build_demo_database(target_dir: Path, days: int = 60, seed: int = 7) -> Path`.
- [ ] Tests: env forces demo even if personal DB exists (Review Focus 1); default is personal; demo DB builds and has drives.
- [ ] Fail → implement → pass → commit.

### Task 3: Queries

**Files:** Create `src/kiatracker/dashboard/queries.py`; Test `tests/dashboard/test_queries.py`, `tests/dashboard/conftest.py` (session demo DB fixture + empty DB fixture)
- `connect(db_path) -> duckdb.DuckDBPyConnection` (read-only); `Period(start: date, end: date)` (local dates, inclusive).
- `kpis(con, period) -> dict` keys `distance_km, drives, kwh_per_100km, energy_charged_kwh, latest_soc, latest_range_km`.
- `weekly(con, period) -> DataFrame[week, distance_km, kwh_per_100km]`.
- `drives(con, period) -> DataFrame[start_local, distance_km, minutes, kwh_per_100km, energy_kwh, temp_c, wind_kph, start_zone, end_zone]`.
- `consumption_by_band(con, period, column: 'temp_c'|'wind_kph'|'distance_km', edges: list[float]) -> DataFrame[band, kwh_per_100km, drives]`.
- `charging_sessions(con, period) -> DataFrame[start_local, zone, soc_start, soc_end, energy_kwh, hours, avg_kw]`.
- `weekly_charging(con, period) -> DataFrame[week, energy_kwh, sessions]`.
- `costs(con, period, electricity_per_kwh, petrol_per_litre, petrol_l_per_100km, charging_loss_pct) -> DataFrame[month, distance_km, electricity_cost, petrol_cost, savings]`.
- [ ] Tests: values on demo DB are positive and consistent (sum of weekly distance == kpis distance); privacy column test; empty DB returns empty frames and None KPIs (Review Focus 2, 3); all-short drives → None consumption (Review Focus 4); costs arithmetic on a tiny hand-built DB.
- [ ] Fail → implement → pass → commit.

### Task 4: Charts

**Files:** Create `src/kiatracker/dashboard/charts.py`; Test `tests/dashboard/test_charts.py`
- `bar(df, x, y, title, y_title, color=BLUE)`, `line(df, x, y, title, y_title)`, `scatter(df, x, y, title, x_title, y_title, tooltip)`, `histogram(df, column, title, step)`; all return `alt.Chart` with tooltips.
- [ ] Tests: each spec (`to_dict()`) has a tooltip encoding and one y encoding; colour is BLUE.
- [ ] Fail → implement → pass → commit.

### Task 5: App and pages

**Files:** Create `src/kiatracker/dashboard/app.py`, `src/kiatracker/dashboard/pages/{overview,drives,charging,costs}.py`, `.streamlit/config.toml`; Test `tests/dashboard/test_app.py`
- App reads source from `resolve_source`, shows a "Demo data" banner in demo mode, sidebar date range, `st.navigation` with the four pages; missing personal DB → message (Review Focus 5).
- [ ] Test: `AppTest` runs each page in demo mode without exceptions and shows its title; personal mode with missing DB shows the build hint.
- [ ] Fail → implement → pass → commit.

### Task 6: CLI, docs, screenshots

**Files:** Modify `src/kiatracker/cli.py`, `README.md`, `pyproject.toml`; Create `docs/images/*.png`
- `kiatracker dashboard [--demo]` runs `python -m streamlit run <app> --server.address 127.0.0.1` with the source passed via environment.
- [ ] Test: CLI builds the streamlit command with `127.0.0.1` and `KIATRACKER_DEMO=1` for `--demo` (command construction function, no process started).
- [ ] Run the demo dashboard, screenshot each page, add to README.
- [ ] Commit.
