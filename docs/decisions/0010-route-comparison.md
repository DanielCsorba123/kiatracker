# 0010. Route comparison with OSRM, ~1 km pieces and a common-random-numbers Monte Carlo

**Status:** Accepted, November 2026

## Context

The motivating question: from Krems to Wiener Neustadt, is the flat but longer and windier way via Vienna
cheaper than the shorter, hillier way via St. Pölten, for tomorrow's weather? Answering it needs candidate
routes with geometry and speeds, the forecast along them, terrain, the fitted model, and an honest statement
of how sure the answer is.

## Decision

- **Routing:** OSRM (OpenStreetMap data, open source). The public demo server by default, no key;
  `KIATRACKER_OSRM_URL` points at a self-hosted one. Place names are geocoded with Nominatim, with an
  identifying User-Agent as its policy requires; "lat, lon" input skips it. Because the demo server often
  returns a single route, the user can add **via places**, each line giving one more candidate.
- **Pieces:** each route is cut into ~1 km pieces from OSRM's per-edge distances and durations. A piece is
  driven at a known time (departure + time so far), so it gets that hour's forecast for its cell, its own
  headwind and its climb.
- **Energy:** the range model prices each piece; the total is split by cause (rolling, time-based load, drag,
  wind, heating, air conditioning, climbing, regeneration).
- **Via points are exact:** OSRM routes through the point given, so a town name means its centre. Motorway
  alternatives are chosen with interchange names (Nominatim knows them, e.g. "Knoten Prater") or coordinates,
  and every route lists its main roads so the choice can be checked.
- **Uncertainty:** 1,000 simulated days per route: forecast temperature ±1.5 °C, wind speed ±25 % and
  direction ±20°, pace ±4 %, the model's coefficients (bootstrap refits, or ±20 % around the specs), plus
  the model's own error. Each error is shared along the route (a wrong
  forecast is wrong everywhere). The model's residual spread contains the battery-reading noise of short
  training drives, which a long trip does not suffer, so that part is subtracted using the model's median
  training distance.
- **Common random numbers:** every route is simulated on the same random days, so "route A uses less on
  97 % of simulated days" compares like with like.
- **Levers:** departure time, charge at departure, speed cap, pace.

## Consequences

- No account or key needed by anyone reproducing the project.
- OSRM's speeds are free-flow estimates without live traffic; the pace lever and the uncertainty cover part
  of that.
- The places typed are sent to Nominatim and OSRM, and ~10 km cells to Open-Meteo; recorded drives never are.

## Alternatives considered

- **OpenRouteService** (the first plan): good alternatives and elevation, but needs a key per user.
- **Google Directions / Waze:** best traffic data, but paid or not available as an API, and terms forbid
  storing results.
- **Self-hosted OSRM on the Pi:** private and unlimited; preprocessing a regional extract needs several GB of
  RAM. Planned once the public server becomes a limit.
- **Independent Monte Carlo per route:** would exaggerate the overlap between routes and make differences
  look less certain than they are.
