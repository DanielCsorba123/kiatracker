# Dashboard: design

Date: 2026-11-02. Status: approved in advance by the owner ("start making the dashboard … architected properly like a portfolio project, but I don't want our personal data to leak out"); review after the fact.

## 1. Purpose

A local web dashboard over the data foundation's DuckDB file that answers: how far and how efficiently do we drive, what do weather and short trips cost, how and when do we charge, and what does driving electric save. It doubles as the portfolio's visible face: a public demo that runs only on generated data.

## 2. Privacy model (the binding constraint)

1. **Two data sources, chosen at start-up, never mixed; fail closed.** *Demo* mode (the default) generates its own database from `kiatracker.synthetic` into a new private temporary folder. *Personal* mode reads `data/kiatracker.duckdb` and needs an explicit `KIATRACKER_PERSONAL=1`, which only `kiatracker dashboard` sets; it refuses to run unless the server listens on this computer only. `KIATRACKER_DEMO` (any value but 0/false/empty) always forces demo mode. There is no switch in the UI to reach personal data. (Revised after review: the first version defaulted to personal data.)
2. **No coordinates leave the query layer.** Query functions select zones (`home` / `other`), never latitude, longitude or VIN. A test asserts that no returned frame has a coordinate column. There is no map in this version.
3. **Local only by default.** `kiatracker dashboard` binds to `127.0.0.1`. Streamlit's usage statistics are switched off in the committed `.streamlit/config.toml`.
4. **Screenshots for the README come from demo mode only.**
5. Prices for the cost page are inputs with neutral defaults, not personal tariffs.

## 3. Architecture

```
kiatracker.dashboard
├─ queries.py   SQL over DuckDB → pandas DataFrames / dicts (no Streamlit import; unit-tested)
├─ charts.py    Altair chart builders: frame in, chart out (no Streamlit import; unit-tested)
├─ source.py    resolves personal vs demo database; builds the demo DB once per process
├─ app.py       Streamlit entry: navigation, sidebar date filter, data-source banner
└─ pages/       overview.py, drives.py, charging.py, costs.py (thin: call queries, render charts)
```

- Streamlit + Altair: Python end to end, runs on a Raspberry Pi, interactive tooltips by default, deploys to Streamlit Community Cloud for a public demo link.
- The dashboard is an optional extra (`kiatracker[dashboard]`: streamlit, altair, pandas) so the collector stays light on the Pi.
- Pages are thin; all logic sits in `queries` and `charts`, which are testable without a browser. The app as a whole is smoke-tested with Streamlit's `AppTest` against the demo database.

## 4. Pages

All periods use local time (Europe/Budapest). A sidebar date range (default: last 30 days) filters every page.

- **Overview** — stat tiles: distance, drives, average consumption (distance-weighted over drives ≥ 5 km), energy charged, latest charge % and estimated range. Charts: weekly distance (bars); weekly consumption (line). Separate charts, never a dual axis.
- **Drives** — consumption vs outside temperature (scatter, one series); average consumption per temperature band (bars) with the "weather cost" vs the mild-weather baseline; consumption vs wind speed (scatter); short-trip penalty (consumption by distance band); drives table.
- **Charging** — energy charged per week (bars); charge % at plug-in and at unplug (histograms, 10 % bins), share of sessions ending at ≥ 95 %; sessions table with zone, kWh, hours, average kW.
- **Costs** — inputs: electricity price per kWh, petrol price per litre, comparison car's L/100 km, charging loss %. Output tiles: electricity cost, equivalent petrol cost, savings; monthly bars of both. Pure arithmetic in `queries.costs()`.

## 5. Visual rules

Altair with the reference data-viz palette: categorical slot 1 blue `#2a78d6`, slot 2 orange `#eb6834`; status colours reserved. Thin marks, 2 px lines, tooltips on every mark, one y-axis per chart, a single series needs no legend, recessive grid. Values in tables are formatted with units.

## 6. Demo data

The synthetic generator also writes Open-Meteo-shaped weather records covering its area (0.1° grid around the fictional home) and makes consumption depend on temperature and wind, so the weather charts show a real relationship in the demo.

## 7. Testing

- `queries`: each function against a demo database built once per test session; privacy test on returned columns; empty-database behaviour (no drives) returns empty frames, not errors.
- `charts`: each builder returns a chart whose spec has a tooltip and a single y-axis.
- `source`: `KIATRACKER_DEMO=1` ignores a personal database path even when one exists.
- App: `AppTest` runs every page in demo mode with no exception.

Out of scope: maps, range forecasting, SolarEdge/wallbox data, authentication, deployment itself (documented, not done).
