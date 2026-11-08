# 0003. Derive drives and charging from polling; adaptive 1 / 5 minute interval

**Status:** Accepted, November 2026 (interval made adaptive on 8 November 2026)

## Context

For the EV3 the API's trip history contains only a start time and a duration per trip: no distance, energy or
route. Snapshots, by contrast, carry the odometer (0.1 km), state of charge (0.5 %), ignition, charging status
and GPS position, each with the car's own timestamp. While driving, the car sends a fresh reading of every
group at least every few minutes.

## Decision

- Poll all snapshot groups and store a reading only when its car timestamp is new (deduplication in
  `collect.py`, with state in `data/raw/logger_state.json`). Sync the trip list every 6 hours.
- Derive drives from the driving readings (ignition on, or the odometer moved), split by API trips when the
  polling merged two trips, and refine start and end times with the API trips. Energy is the state-of-charge
  difference times battery capacity. Charging sessions are runs of `charging = true` readings.
- **Adaptive interval:** every minute while the ignition is on, every 5 minutes otherwise
  (`schedule.Job.next_every`). Refresh (weather, forecast, fuel prices, rebuild, retrain) runs hourly.

## Consequences

- One-minute polling while driving gives a GPS point every ~1 km on country roads, which is what per-stretch
  weather and terrain need ([0009](0009-per-stretch-features.md)), and catches short stops that 5-minute
  polling merged.
- Parked, the car's readings rarely change, so 5 minutes costs little and keeps call volume moderate.
- Consumption is only reported for drives of 5 km or more: below that, a single 0.5 % step is a large share
  of the energy.
- A gap in collection (computer off, Pi down) hides drives; see [0004](0004-data-quality-guardrails.md).

## Alternatives considered

- **Fixed 5 minutes:** too coarse for stretch features and short stops.
- **Fixed 1 minute:** five times the calls while parked, for readings that do not change.
- **Trusting the trip list alone:** it has no distance or energy for this car.
