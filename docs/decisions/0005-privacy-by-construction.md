# 0005. Privacy by construction: fail-closed demo, no coordinates past the build

**Status:** Accepted, November 2026

## Context

The data is a precise log of where one person lives, works and goes, plus the car's VIN. The repository is
public as a portfolio project and the dashboard may later be hosted publicly. A single mistake (a screenshot,
a debug print, a misconfigured server) would publish a home address.

## Decision

Rules enforced in code and tests, not by care:

- **Secrets and data never in git:** credentials only in `.env`; `data/` and `*.local.ipynb` are gitignored;
  gitleaks and ruff run before every commit and in CI.
- **Coordinates stay inside the private database:** `readings_location` and the drive start / end columns
  keep them (the database never leaves the owner's machine), and they are used to derive zones, headwinds and
  climbs. No dashboard query result, feature row, derived stretch table, log line or collector summary
  contains them. Places are shown as `home` / `other`. A test checks that query results have no latitude,
  longitude or VIN.
- **Fail closed:** the dashboard shows generated demo data unless personal mode is switched on explicitly
  (`KIATRACKER_PERSONAL=1`, set only by `kiatracker dashboard`). Personal mode refuses to run unless the
  server listens on `127.0.0.1`, or runs in the container whose port is published on `127.0.0.1` only.
  `KIATRACKER_DEMO` always wins.
- **Third parties see as little as possible:** weather is fetched for ~10 km cells (0.1°), never exact
  points; terrain is read from tiles stored locally ([0008](0008-local-terrain-tiles.md)); routing sends only
  the places the user types, never recorded drives.
- **Demo everywhere public:** README screenshots, the committed notebook outputs and tests use the simulator
  or a fake home (a field in rural Hungary); test coordinates avoid the owner's terrain tile.

## Consequences

- Some features are harder: the map on the Routes page shows only planned routes, never driven ones.
- The Routes map's tiles come from OpenFreeMap ([0013](0013-maplibre-openfreemap.md)): the browser asks for
  the tiles in view, as with any web map; no route geometry is sent to the tile server.
- Weather is slightly less precise than point lookups (one cell is ~10 km across), which matters little for
  temperature and wind.
- Remote access had to be solved without opening a port: [0011](0011-raspberry-pi-docker-tailscale.md).

## Alternatives considered

- **Coordinates rounded to ~1 km in tables:** still enough to find a home in a village; rejected.
- **Authentication in the dashboard:** adds a password to manage and a login page to get wrong; private
  network access (Tailscale) is simpler and stronger for a single user.
