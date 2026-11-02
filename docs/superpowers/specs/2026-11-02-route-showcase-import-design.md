# Route predictor, public showcase and data import: plan

Date: 2026-11-02. Status: planning, for the owner's review. Builds on the data foundation, dashboard and range model.

## Goals (from the owner)

1. **Route predictor.** Pick a destination and get the energy and charge on arrival, from the model fitted to the owner's past drives and the current forecast wind, temperature and the route's elevation.
2. **More ML/AI.** Consumption against speed, and further models as data grows; this is an AI/data engineering portfolio project.
3. **Public showcase.** Anyone with the link sees the owner's real driving statistics and the models trained on them, but nothing that can be traced back: no places, no routine, no car identity.
4. **Others' data.** Visitors can bring their own data, and Kia/Hyundai/Genesis owners in Europe can run the whole thing on their own car.

## 1. Route predictor

**Route and elevation.** [OpenRouteService](https://openrouteservice.org) directions with `elevation=true` returns the route geometry with heights, step durations, and a geocoder for the destination search. It is free with an API key: about 2,000 routes per day. Google's Routes and Elevation APIs would work too, but need a billing account and add nothing here. Fallback without a key: OSRM for the route plus the [Open-Meteo Elevation API](https://open-meteo.com/en/docs/elevation-api) for heights.

**Segments.** The route is resampled into ~500 m pieces. Each piece gets:
- length and bearing,
- climb and descent in metres,
- expected speed, from ORS step durations,
- the time the car will pass it, from the departure time plus cumulative duration,
- forecast wind speed, wind direction and temperature for that hour and 0.1° cell (Open-Meteo forecast, one request per cell).

**Energy per piece.** The fitted model gives kWh/100 km from the piece's speed, its own headwind (v + h)² and the temperature, then a climb term is added:

```
kWh = length · model(v, headwind, T) / 100 + c_up · ascent_m − c_down · descent_m
```

Physics prior: lifting the EV3 (~1.9 t with driver) by 1 m takes m·g·h ≈ 0.0052 kWh; regenerative braking recovers roughly 60 % of descents. `c_up` starts at the prior and is fitted from past drives once their elevations are known (phase B), with 0 ≤ c_down ≤ c_up.

**Output.**
- Arrival charge % with the model's interval, and kWh used.
- A breakdown of where the energy goes: base, air resistance, of which wind, heating, climbing net of regen.
- "Same trip in still air" and "same trip at 15 °C" for comparison.
- A round-trip check and the charge level needed to arrive with 20 %.
- A map of the route, coloured by energy per km (personal mode; the showcase draws it only for the visitor's own route).

**Page.** A new *Route* page has a destination search, a departure time (default: now) and a speed preference (±10 %). The start is the home location from `.env`, or a typed address.

## 2. More models and data (phase B, as data arrives)

| Addition | What it shows | Needs |
|---|---|---|
| Elevation of past drives | Learns `c_up` / `c_down` from the owner's own drives instead of the prior | GPS points → Open-Meteo Elevation API (free, 100 points per request), cached as raw records |
| Speed curve | kWh/100 km against speed, model curve over measured drives, at today's temperature | Existing data |
| Residual learner | Gradient boosting on what the physics model misses (time of day, trip length, climate use); kept only if the time-ordered backtest shows it beats physics alone | ~150+ drives; scikit-learn |
| Anomalies | Drives far outside their prediction interval ("tyre pressure low? roof box?") | Existing model |
| Battery health trend | kWh per % SOC over months, from long charging sessions | Months of charging data |

Every model enters through the same backtest, and the dashboard shows its score against the simpler ones. That comparison is part of what the portfolio demonstrates.

## 3. Public showcase without traceable data

The public app never reads the live database. The owner runs `kiatracker export-showcase`, which writes a small, reviewed, anonymised data set; the public instance reads only that (`KIATRACKER_SHOWCASE=1`, fail-closed like demo mode).

| Kept | Removed or coarsened |
|---|---|
| Date of each drive and charge (no time of day) | Coordinates, zones (home / other), routes, VIN, odometer |
| Distance rounded to 1 km, kWh/100 km to 0.1, temperature and wind to whole numbers | Exact timestamps and drive order within a day |
| Charging: date, kWh, start and end % (whole numbers) | Charging location |
| Model coefficients, backtest scores, predicted-vs-actual | Raw API records |

Residual risk: a distance that repeats every working day still hints at a commute length, though not where. The export command prints exactly what will be published and a summary of distinct distances; the owner approves before anything is committed. The export lives in `showcase/` in the public repo, so every published byte is visible in git history and reviewable.

Hosting: **Streamlit Community Cloud** (free) deploys the app from the public GitHub repo with `KIATRACKER_SHOWCASE=1`. In the showcase, the route predictor works on routes the *visitor* enters, using the owner's fitted model, so the planner is public too without revealing anything about the owner.

## 4. Others' data

- **Own Kia / Hyundai / Genesis in Europe:** already possible. Clone the repo, add a Pleos key, run the collector. The README will get a step-by-step guide.
- **Upload in the public app:**
  - a CSV with `date, distance_km, kwh` (or `soc_start, soc_end`, plus battery size), optional `temp_c`, `avg_speed_kph`;
  - or a `kiatracker` raw export (zip).

  Processing happens in memory for that browser session only; nothing is stored or logged. The visitor gets the same pages and a model fitted to their data. Without temperatures, they pick a city and daily weather is fetched for the dates.
- Later: importers for common EV logger exports (e.g. TeslaMate CSV).

## Phases

| Phase | Delivers | Owner needs to |
|---|---|---|
| A | Route predictor with elevation prior and forecast weather; Route page | Create a free OpenRouteService key, put it in `.env` as `ORS_API_KEY` |
| B | Elevation of past drives, fitted climb terms, speed curve, anomalies; residual learner once data allows | Keep the collector running |
| C | `export-showcase`, showcase mode, Streamlit Cloud deployment | Decide when to make the repo public; approve the first export |
| D | CSV / export upload for visitors | — |

## Decisions for the owner

1. OpenRouteService as the route provider (free key) rather than Google: recommended.
2. The showcase keeps dates (not times) and rounded distances; anything stricter (week-level, distance bands) is easy to switch on.
3. The repo needs to be public for Streamlit Community Cloud's free tier, and to be visible on a CV at all.
