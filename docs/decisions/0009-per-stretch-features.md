# 0009. Features per stretch between GPS readings, scaled to the odometer

**Status:** Accepted, November 2026

## Context

Drive-level features used one hourly temperature and wind at the drive's midpoint. A long day (Krems and
back) starts near freezing, warms up, crosses hills and changes direction against the wind; one value per
drive is wrong for all of that.

## Decision

`segments.py` cuts each `ok` drive into stretches between consecutive GPS readings (one polling interval,
about 1 km at 1-minute polling). Each stretch gets:

- the temperature and wind of its own hour and its own 0.1° cell;
- the headwind along its own bearing;
- the climb and descent between its two ends ([0008](0008-local-terrain-tiles.md)).

Stretches are stored in `drive_segments` without coordinates. The model's features are distance-weighted
over the stretches (drag with each stretch's speed and air density, heating per stretch hour, climb and
descent per 100 km). Straight lines between GPS points are shorter or longer than the road, so each stretch's
speed is scaled by the drive's **road factor**: odometer distance ÷ straight-line total. A drive without
complete stretch weather falls back to drive-level features.

## Consequences

- The model sees the conditions where and when energy was actually spent, and can learn the hill terms.
- More weather requests (one per cell and day touched), still far below Open-Meteo's free limits.
- Stretch speeds from a parked minute are floored at 5 km/h so heating per km does not explode.

## Alternatives considered

- **Map-matching GPS to roads** (exact road distance per stretch): heavier and needs a road network; the road
  factor gets the same totals.
- **Drive-level features only:** simpler, demonstrably wrong for long or hilly drives.
