# Roadmap

## Done

| Area | What |
|---|---|
| Data foundation | Pleos client, deduplicating collector, raw JSONL, full rebuild into DuckDB, drives, charging, charge windows, API trip refinement |
| Data quality | `gap` / `implausible` flags; energy only from trustworthy drives |
| Weather | Open-Meteo per drive and per stretch (archive + forecast), home-cell forecast |
| Terrain | Local SRTM tiles; climb and descent per stretch and per route piece |
| Model | Physics-informed NNLS with drag, heating, climb and regeneration; car-spec prior with backtest-chosen pull; time-ordered backtest against three references; calibrated intervals |
| Dashboard | Windrose identity; Overview, Drives (business and analyst views), Charging, Costs (vs petrol, EU fuel prices), Range, Routes |
| Routes | OSRM routes and via places, ~1 km pieces with forecast weather and terrain, energy by cause, common-random-numbers Monte Carlo, levers |
| Operations | Docker image for x86 / arm64; collector and dashboard on a Raspberry Pi; adaptive polling (1 / 5 min); Tailscale Serve access |
| Learning | Model walkthrough notebook with decisions for the reader |

## Next

1. **Nightly backup** of the Pi's `data/` to the PC (or another disk): the only copy of the history lives on
   one SD card / SSD. `rsync` over Tailscale from a scheduled task on the PC.
2. **Plan vs actual loop:** when a compared route is driven, match the recorded drive to the plan and show
   predicted vs measured energy per route; over time this is the honest test of the route predictor.
3. **Residual learner** once ~150 clean drives exist: gradient boosting on what the physics model misses
   (time of day, trip length, climate settings, temperature soak). Enters the same backtest; kept only if it
   wins.
4. **Cabin-settings feature:** climate mode, set temperature, seat and steering-wheel heating are collected;
   test whether they explain heating residuals once there are enough cold drives.
5. **Speed curve and anomalies:** consumption against speed at today's temperature; drives far outside their
   interval flagged ("roof box? tyre pressure?").

## Later

- **Phase C, public showcase:** `kiatracker export-showcase` writes a reviewed, anonymised data set (dates
  without times, rounded distances, no places), and a showcase mode (fail-closed like demo mode) hosted on
  Streamlit Community Cloud. The route planner works there on routes the visitor types, with the owner's fitted
  model.
- **Phase D, visitors' data:** upload a CSV (`date, distance_km, kwh` or SOC) or a kiatracker raw export;
  processed in memory for that session only; a model fitted to their car.
- **Self-hosted OSRM** on the Pi or a VM, once the public demo server's limits or privacy matter.
- **Battery health trend** from long charging sessions (kWh per % SOC over months).
- **Other cars:** the specs prior is a dataclass; adding a car means its mass, drag area and capacity.

## Under discussion

- **A local LLM (e.g. Ollama):** not as the predictor (a language model is the wrong tool for a numeric
  regression on tens of rows: not reproducible, uncalibrated, no physical extrapolation), but possibly *around*
  the model: answering questions in plain language by calling the model and the database as tools, or writing
  trip summaries.

## Considered and not planned

- **Unofficial Kia Connect API:** fragile and password-based ([ADR 0001](decisions/0001-official-data-act-api.md)).
