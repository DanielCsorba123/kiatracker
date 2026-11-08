# 0001. Official Pleos (EU Data Act) API as the only car data source

**Status:** Accepted, November 2026

## Context

There are three ways to get data out of a 2024+ Kia EV3 in Europe:

1. **Pleos Vehicle Data API**, which Hyundai Motor Group opened for private owners under the EU Data Act. Free
   private-user key, documented, OAuth client credentials.
2. **Unofficial Kia Connect / Bluelink libraries** (reverse-engineered app API). Richer in places, but they
   break when the app changes, use the owner's account password, and some calls wake the car.
3. **OBD-II dongle** reading the CAN bus. The most detailed (cell temperatures, power), but needs hardware in the
   car, and the EV3's battery data is not on standard PIDs.

Probing the Pleos API on the real car (`spikes/`) showed what it gives for the EV3: live snapshots of battery,
powertrain range, GPS position, ignition/odometer and climate status, each stamped with when the car sent it;
trip history only as start time and duration; no speed series, no power, no outside temperature.

## Decision

Use only the Pleos API. Store every response as received ([0002](0002-raw-files-as-source-of-truth.md)) and
derive everything else ([0003](0003-derive-drives-from-polling.md)).

## Consequences

- Legal, stable and documented; works for any Hyundai / Kia / Genesis owner in Europe, which makes the project
  reproducible by others.
- The thin trip data forces derived drives and an indirect energy measure (state-of-charge steps of 0.5 %,
  about 0.4 kWh), which limits per-drive accuracy for short drives.
- No rate limit is documented. Around 1,400 to 3,000 calls a day has worked so far.

## Alternatives considered

- **Unofficial app API:** rejected for fragility, password handling and the risk of draining the 12 V battery
  by waking the car.
- **OBD dongle:** kept as a possible later addition for power and cabin-heater data; not needed for the core
  questions.
