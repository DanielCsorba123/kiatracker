# kiatracker

A personal data platform for a Kia EV3: it collects the car's own data through the official EU Data Act API, models every drive and charge, and joins them with weather. The goal is to answer how much range wind, cold and route really cost, and later to forecast it.

> Status: data foundation, dashboard and weather-aware range model done. Next: route-aware range (elevation and wind along a planned route).

![Dashboard overview (demo data)](docs/images/overview.png)

## How it works

```
Pleos API ──collect (every 5 min)──▶ data/raw/*.jsonl   append-only, never edited
Open-Meteo ─weather─────────────────▶ data/raw/weather-*.jsonl
                                            │
                                     build (full rebuild)
                                            ▼
                              data/kiatracker.duckdb
                              ├─ readings_*  typed, deduplicated readings
                              ├─ api_trips   trip start and duration from the API
                              ├─ drives      distance, SOC used, kWh/100 km, zones
                              ├─ charging_sessions, charge_windows
                              └─ drive_weather  temperature, wind, gusts per drive
                                            │
                                            ▼
                     dashboard (Streamlit): queries.py → charts.py → pages
                     forecast: features → physics-informed model → backtest → range outlook
```

- **Raw files are the source of truth.** Every API response is stored as received; the database is rebuilt from them in seconds, so parsing fixes apply to all history.
- **The car's API is thin.** For the EV3 the API gives live status (charge, odometer, GPS, ignition, climate) but trip history only as start time and duration. Drives, energy and charging sessions are therefore derived from 5-minute polling, with API trips tightening the start and end times.
- **Consumption is only reported for drives of 5 km or more**, because state of charge moves in 0.5 % steps (about 0.4 kWh).
- **Privacy:** credentials live in `.env`, all data in the gitignored `data/` folder, and summaries label places `home` / `other` instead of coordinates. A fake-data generator lets everything run without a car.

## Try it without a car

```bash
uv sync --extra dashboard
uv run kiatracker dashboard --demo
```

This opens the dashboard at http://127.0.0.1:8501 on 60 days of simulated driving, charging and weather. For a terminal-only taste, `uv run kiatracker demo` builds 30 days of fake data into `data/demo/` and prints a summary.

## Dashboard

| | |
|---|---|
| ![Drives: consumption against temperature, wind and trip length](docs/images/drives.png) | ![Charging: energy per week and battery level at plug-in and unplug](docs/images/charging.png) |
| **Drives:** consumption against temperature, wind and trip length, with the cold-weather penalty spelled out. | **Charging:** energy per week, where in the battery's range charging starts and stops. |
| ![Costs: savings against a petrol car](docs/images/costs.png) | |
| **Costs:** what the electricity cost against the same distance in a petrol car, at prices you enter. | |

## Range model

![Range: forecast for the next days, what-if sliders, backtest](docs/images/range.png)

How far will the current charge really go in tomorrow's weather? The model is a **physics-informed regression**, not a black box, because a personal car produces tens of drives, not millions:

```
kWh/100 km = c0 + c_aero · (v + headwind)² + c_heat · max(0, 18 °C − T) / v
```

- **Air resistance** grows with the square of airspeed. Headwind is the hour's wind projected onto the direction of travel, taken from the car's GPS points along each drive. Without a known route, wind averages out to v² + w²/2: on a round trip it always costs range.
- **Heating** draws roughly constant power, so its energy per km scales with time per km. Slow, cold trips cost the most.
- **Fitting:** distance-weighted least squares. A coefficient that comes out negative (cold "saving" energy) is dropped and the rest refitted. It needs 15 drives to start.
- **Honest evaluation:** a time-ordered backtest that only ever trains on earlier drives, against two baselines. The 10th-90th percentile of the out-of-sample errors becomes the range interval.
- **Validated on known truth:** the simulator drives with known coefficients, and a test checks the fit recovers them within 15 %. On 60 demo days the backtest error is 1.1 kWh/100 km, against 1.8 for a temperature-only line and 2.1 for the mean.

```bash
uv run kiatracker train      # fit, backtest, explain
uv run kiatracker forecast   # fetch the 3-day forecast and print the range per day
```

## How the dashboard is built

- `queries.py` turns DuckDB into pandas frames and `charts.py` turns frames into Altair charts; neither imports Streamlit, so both are unit-tested. Pages are thin `render(con, period)` functions, smoke-tested headlessly with Streamlit's `AppTest`.
- **Privacy by construction, failing closed.** Queries return `home` / `other` zones, never coordinates or the VIN (a test enforces it). The app shows simulated data unless it was started by `kiatracker dashboard`, which opts in to personal data, binds to `127.0.0.1` and turns off Streamlit's usage statistics and error details; personal mode refuses to run on any other address, and `KIATRACKER_DEMO` always forces the demo. Every screenshot here is demo data.

## Use it with your own Hyundai / Kia / Genesis (Europe)

1. Get a private Vehicle Data API key at [Pleos](https://document.pleos.ai/en/api-reference/vehicle-data-api/getting-started/for-private-users/request-my-vehicle-api-key) (the car must already be in your Kia/Bluelink account).
2. `cp .env.example .env` and fill in the client ID and secret.
3. Poll every 5 minutes with any scheduler, and rebuild when you want fresh tables:

```bash
uv run kiatracker collect   # one poll; schedule this
uv run kiatracker weather   # fetch weather for new drives, then rebuild
uv run kiatracker stats
uv run kiatracker dashboard # your own data, on this computer only
```

On Windows, Task Scheduler runs `.venv\Scripts\pythonw.exe -m kiatracker collect` with **Start in** set to the project folder, since `.env` and `data/` are found relative to it (output goes to `data/logs/`). On a Raspberry Pi, build the Docker image and use the systemd timer in [deploy/](deploy/).

## Development

```bash
uv sync           # includes the dashboard extra and test tools
uv run pytest
uv run ruff check && uv run ruff format --check
uvx pre-commit install   # gitleaks + ruff before every commit
```

`spikes/` holds the throwaway scripts used to explore the API.

## License

MIT
