# 0004. Flag drives whose energy is unknown or impossible instead of guessing

**Status:** Accepted, November 2026

## Context

On 7 November 2026 the collector (then on a PC) was off overnight while the car charged to 100 %. The next
morning's 358 km round trip appeared as one "drive" from the last reading the evening before (59.5 %) to the
first reading after the trip (19.5 %): the energy looked like 40 % of the battery for 358 km, an impossible
9 kWh/100 km. Unseen charging between two readings makes the energy of anything in between unknowable.

## Decision

Every drive gets a `quality`:

- `gap`: the first reading of the drive is parked and more than an hour (`UNSEEN_AFTER`) after the previous
  one, so a charge may have happened unseen.
- `implausible`: energy is negative (charge rose during the drive) or consumption is outside 6–45 kWh/100 km.
- `ok`: otherwise.

For `gap` and `implausible` drives, distance is kept (the odometer is reliable) but energy and consumption
are set to null. They are excluded from the model and shown with their flag in the dashboard.

## Consequences

- One bad drive can no longer pull the model or the weekly averages.
- Real but unusual drives outside 6–45 kWh/100 km would be lost; the bounds are wide enough that none have
  been seen.
- The fix for gaps is operational: an always-on collector ([0011](0011-raspberry-pi-docker-tailscale.md)).

## Alternatives considered

- **Infer the unseen charge** (assume a full charge to 100 % before the drive): plausible for this case, but
  silently wrong whenever the guess is wrong. Recorded data should not be invented.
- **Outlier removal by residual:** would remove drives because the model dislikes them, which hides model
  error; quality rules are about the measurement, not the model.
