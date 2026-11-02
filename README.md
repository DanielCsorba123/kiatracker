# kiatracker

A personal data platform for a Kia EV3: it collects the car's own data through the official EU Data Act API, models every drive and charge, and joins them with weather. The goal is to answer how much range wind, cold and route really cost, and later to forecast it.

> Status: data foundation done (collection, storage, derived tables, weather). Next: dashboard, then a weather-aware range model, then a route-aware one.

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
```

- **Raw files are the source of truth.** Every API response is stored as received; the database is rebuilt from them in seconds, so parsing fixes apply to all history.
- **The car's API is thin.** For the EV3 the API gives live status (charge, odometer, GPS, ignition, climate) but trip history only as start time and duration. Drives, energy and charging sessions are therefore derived from 5-minute polling, with API trips tightening the start and end times.
- **Consumption is only reported for drives of 5 km or more**, because state of charge moves in 0.5 % steps (about 0.4 kWh).
- **Privacy:** credentials live in `.env`, all data in the gitignored `data/` folder, and summaries label places `home` / `other` instead of coordinates. A fake-data generator lets everything run without a car.

## Try it without a car

```bash
uv sync
uv run kiatracker demo --days 30
```

This writes 30 days of realistic fake raw data to `data/demo/`, builds the database and prints a summary.

## Use it with your own Hyundai / Kia / Genesis (Europe)

1. Get a private Vehicle Data API key at [Pleos](https://document.pleos.ai/en/api-reference/vehicle-data-api/getting-started/for-private-users/request-my-vehicle-api-key) (the car must already be in your Kia/Bluelink account).
2. `cp .env.example .env` and fill in the client ID and secret.
3. Poll every 5 minutes with any scheduler, and rebuild when you want fresh tables:

```bash
uv run kiatracker collect   # one poll; schedule this
uv run kiatracker weather   # fetch weather for new drives, then rebuild
uv run kiatracker stats
```

On Windows, Task Scheduler runs `.venv\Scripts\pythonw.exe -m kiatracker collect` with **Start in** set to the project folder, since `.env` and `data/` are found relative to it (output goes to `data/logs/`). On a Raspberry Pi, build the Docker image and use the systemd timer in [deploy/](deploy/).

## Development

```bash
uv sync
uv run pytest
uv run ruff check && uv run ruff format --check
uvx pre-commit install   # gitleaks + ruff before every commit
```

`spikes/` holds the throwaway scripts used to explore the API.

## License

MIT
